"""Per-rule confusion matrices on top of the official scorer.

src/evaluate.py's score() reports one confusion matrix across all 15 rules;
docs/07 asks teams to "examine per-rule results and confusion counts". This
module calls score() unchanged, so a run the official scorer rejects is
rejected here too, then splits the confusion counts by rule and lists every
mismatched claim-rule pair for the Error analysis section of
templates/Evaluation_Report.md.

    python -m claimguard.evaluation.confusion \
        --gold data/development/expected_results.jsonl \
        --pred outputs/dev_predictions.jsonl \
        --claims data/development/claims.jsonl \
        --output outputs/dev_confusion.json --markdown outputs/dev_confusion.md

Use the development split to iterate. Score validation only on a frozen
commit (docs/07), and never tune on it.
"""
import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from claimguard._pack import load_jsonl, score

EXPECTED = ("PASS", "FAIL", "UNABLE_TO_ASSESS", "NOT_APPLICABLE")
"""Gold rows. The gold never contains NOT_IMPLEMENTED."""
PREDICTED = EXPECTED + ("NOT_IMPLEMENTED",)
"""Prediction columns. NOT_IMPLEMENTED counts as incorrect (docs/07)."""


def confusion_by_rule(
    gold: Sequence[Mapping[str, Any]],
    pred: Sequence[Mapping[str, Any]],
    claims: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    """score()'s report, unchanged, plus confusion_by_rule and mismatches.

    confusion_by_rule: for each rule, every EXPECTED x PREDICTED cell in fixed
    order, zeros included, in the same {expected, predicted, count} shape as
    score()'s overall "confusion", so two runs diff line by line.

    mismatches: every pair whose predicted status differs from the gold, by
    rule, then in claims-file order.

    Raises ValueError exactly where score() does (missing, extra or duplicate
    pairs, fabricated evidence, invalid fields), and if a gold status falls
    outside EXPECTED.
    """
    report = score(gold, pred, claims)
    g = {(r["claim_id"], r["rule_id"]): r["status"] for r in gold}
    p = {(r["claim_id"], r["rule_id"]): r["status"] for r in pred}

    outside = sorted({s for s in g.values() if s not in EXPECTED})
    if outside:
        raise ValueError(f"Gold contains statuses outside {EXPECTED}: {outside}")

    cells = Counter((k[1], g[k], p[k]) for k in g)  # key: (rule_id, expected, predicted)
    rules = sorted({rule_id for _, rule_id in g})
    by_rule = {
        rule_id: [{"expected": e, "predicted": q, "count": cells[(rule_id, e, q)]} for e in EXPECTED for q in PREDICTED]
        for rule_id in rules
    }

    order = {claim_id: i for i, claim_id in enumerate(claims)}
    mismatches = [
        {"claim_id": claim_id, "rule_id": rule_id, "expected": g[(claim_id, rule_id)], "predicted": p[(claim_id, rule_id)]}
        for claim_id, rule_id in sorted(g, key=lambda k: (k[1], order[k[0]]))
        if g[(claim_id, rule_id)] != p[(claim_id, rule_id)]
    ]
    return {**report, "confusion_by_rule": by_rule, "mismatches": mismatches}


def markdown(report: Mapping[str, Any]) -> str:
    """One table per rule, for the Metrics section of the evaluation report."""
    head = "| expected \\ predicted | " + " | ".join(PREDICTED) + " |"
    rule_line = "|---|" + "---:|" * len(PREDICTED)
    out: List[str] = ["# Per-rule confusion matrices", "", f"_{report['note']}_", ""]
    for rule_id, cells in report["confusion_by_rule"].items():
        m = report["by_rule"][rule_id]
        count = {(c["expected"], c["predicted"]): c["count"] for c in cells}
        out += [f"## {rule_id}", "",
                f"status accuracy {m['status_accuracy']:.3f} | tp {m['tp']} fp {m['fp']} fn {m['fn']} tn {m['tn']} | "
                f"false abstentions {m['false_abstentions']} | missed abstentions {m['missed_abstentions']}", "",
                head, rule_line]
        out += ["| " + e + " | " + " | ".join(str(count[(e, q)]) for q in PREDICTED) + " |" for e in EXPECTED]
        out.append("")
    return "\n".join(out)


def _write(path: str, text: str) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description="Per-rule confusion matrices on top of src/evaluate.py.")
    p.add_argument("--gold", required=True)
    p.add_argument("--pred", required=True)
    p.add_argument("--claims", required=True)
    p.add_argument("--output", default="outputs/confusion.json")
    p.add_argument("--markdown", help="also write the tables as Markdown to this path")
    a = p.parse_args()
    try:
        rows = load_jsonl(a.claims)
        claims = {c["claim_id"]: c for c in rows}
        if len(rows) != len(claims):
            raise ValueError("Duplicate claim IDs")
        report = confusion_by_rule(load_jsonl(a.gold), load_jsonl(a.pred), claims)
    except (ValueError, KeyError, TypeError, IndexError) as e:
        p.exit(2, f"Evaluation rejected: {e}\n")
    _write(a.output, json.dumps(report, indent=2) + "\n")
    if a.markdown:
        _write(a.markdown, markdown(report))
    for rule_id, m in report["by_rule"].items():
        print(f"{rule_id}  accuracy {m['status_accuracy']:.3f}  not_implemented {m['not_implemented']}")
    print(f"{len(report['mismatches'])} mismatched pairs. Report: {a.output}" + (f", {a.markdown}" if a.markdown else ""))


if __name__ == "__main__":
    main()
