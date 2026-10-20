"""Phase 2 headline metrics on top of the official scorer.

The challenge book (Phase 2, Detection Quality) asks for "high Macro F1 score
across rule categories" and "preserving valid claims (low false-positive
rate)", and the evaluation report for "detection metrics, F1 score, false
positive rate, latency, and limitations". src/evaluate.py reports issue F1
per rule and overall, but no macro F1, no claim-level rate and no latency.
This module calls score() unchanged, so a run the official scorer rejects is
rejected here too, and derives:

  macro_f1_by_rule      mean of the scorer's per-rule issue F1. A rule with no
                        expected and no predicted FAIL has an undefined F1: it
                        is listed, never counted as 0 or 1 (docs/07: "Undefined
                        precision/recall is reported as null").
  macro_f1_by_category  tp, fp and fn pooled within each group of
                        categories.json, F1 per group, then the mean.
  claims                claim-level counts (docs/07 "Claim exact match"):
                          false_alarm    claims with no expected FAIL that get
                                         a predicted FAIL
                          clean_flagged  claims whose expected results are all
                                         PASS or NOT_APPLICABLE that get any
                                         FAIL, UNABLE_TO_ASSESS or
                                         NOT_IMPLEMENTED, i.e. a reviewer would
                                         be asked to look at a valid claim
                          exact_match    claims with all 15 statuses correct
  latency               with --manifest, the run's wall time from the run
                        manifest, refused unless the manifest's results hash
                        is the hash of --pred; with --explanations, the model
                        call latencies.

    python -m claimguard.evaluation.summary --split validation \
        --gold data/validation/expected_results.jsonl \
        --pred outputs/val_predictions.jsonl \
        --claims data/validation/claims.jsonl \
        --manifest outputs/val_predictions.jsonl.manifest.json \
        --explanations outputs/val_predictions.jsonl.explanations.jsonl \
        --output outputs/val_summary.json --markdown outputs/val_summary.md
"""
import argparse
import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from claimguard._pack import load_jsonl, score

CATEGORIES_PATH = Path(__file__).with_name("categories.json")
RULE_IDS = tuple(f"R{i:03}" for i in range(1, 16))
CLEAN = ("PASS", "NOT_APPLICABLE")


def load_categories(path=CATEGORIES_PATH) -> Dict[str, List[str]]:
    """{category: [rule IDs]}. Every rule must be in exactly one category."""
    cats = json.loads(Path(path).read_text(encoding="utf-8"))["categories"]
    listed = sorted(r for rules in cats.values() for r in rules)
    if listed != sorted(RULE_IDS):
        raise ValueError(f"{path}: every rule R001-R015 must be in exactly one category")
    return cats


def _f1(tp: int, fp: int, fn: int) -> Optional[float]:
    """The scorer's issue F1, None when there is no expected or predicted FAIL."""
    return 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None


def macro(values: Mapping[str, Optional[float]]) -> Dict[str, Any]:
    """Mean of the defined values; the undefined ones are named, not averaged."""
    defined = [v for v in values.values() if v is not None]
    return {"macro_f1": statistics.mean(defined) if defined else None,
            "defined": len(defined),
            "undefined": sorted(k for k, v in values.items() if v is None)}


def _rate(ids: Sequence[str], of: int) -> Dict[str, Any]:
    return {"count": len(ids), "of": of, "rate": len(ids) / of if of else None}


def summarize(
    gold: Sequence[Mapping[str, Any]],
    pred: Sequence[Mapping[str, Any]],
    claims: Mapping[str, Mapping[str, Any]],
    categories: Optional[Mapping[str, Sequence[str]]] = None,
    split: Optional[str] = None,
) -> Dict[str, Any]:
    """The headline metrics. Raises ValueError exactly where score() does."""
    report = score(gold, pred, claims)
    cats = categories if categories is not None else load_categories()
    by_rule = report["by_rule"]

    per_rule = {rule_id: by_rule[rule_id]["issue_f1"] for rule_id in sorted(by_rule)}
    per_category = {}
    for name, rules in cats.items():
        tp, fp, fn = (sum(by_rule[r][k] for r in rules) for k in ("tp", "fp", "fn"))
        per_category[name] = {"rules": list(rules), "tp": tp, "fp": fp, "fn": fn, "issue_f1": _f1(tp, fp, fn)}

    g: Dict[str, Dict[str, str]] = defaultdict(dict)
    p: Dict[str, Dict[str, str]] = defaultdict(dict)
    for r in gold:
        g[r["claim_id"]][r["rule_id"]] = r["status"]
    for r in pred:
        p[r["claim_id"]][r["rule_id"]] = r["status"]
    order = list(claims)
    no_fail = [c for c in order if "FAIL" not in g[c].values()]
    clean = [c for c in order if all(s in CLEAN for s in g[c].values())]
    false_alarm = [c for c in no_fail if "FAIL" in p[c].values()]
    clean_flagged = [c for c in clean if any(s not in CLEAN for s in p[c].values())]
    exact = [c for c in order if g[c] == p[c]]

    return {
        "split": split,
        "official_overall": report["overall"],
        "macro_f1_by_rule": macro(per_rule),
        "macro_f1_by_category": {**macro({n: c["issue_f1"] for n, c in per_category.items()}),
                                 "categories_version": None if categories is not None else
                                 json.loads(CATEGORIES_PATH.read_text(encoding="utf-8"))["version"]},
        "per_rule_f1": per_rule,
        "per_category": per_category,
        "claims": {
            "total": len(order),
            "false_alarm": {**_rate(false_alarm, len(no_fail)), "claim_ids": false_alarm},
            "clean_flagged": {**_rate(clean_flagged, len(clean)), "claim_ids": clean_flagged},
            "exact_match": _rate(exact, len(order)),
        },
        "latency": None,
    }


def latency(manifest: Mapping[str, Any], results_path, explanations: Optional[Iterable[Mapping[str, Any]]] = None):
    """Wall time of the run that wrote results_path, from its manifest, and
    the model-call latencies. A manifest of another run is refused."""
    digest = hashlib.sha256(Path(results_path).read_bytes()).hexdigest()
    if manifest.get("outputs", {}).get("results_sha256") != digest:
        raise ValueError("The manifest does not describe this results file (results_sha256 differs)")
    n, ms = len(manifest["claims"]), manifest["duration_ms"]
    out: Dict[str, Any] = {"run": {"claims": n, "duration_ms": ms, "ms_per_claim": round(ms / n, 2) if n else None},
                           "explanations": None}
    if explanations is not None:
        calls = [e["latency_ms"] for e in explanations if e.get("latency_ms") is not None]
        out["explanations"] = {"count": len(calls), "median_ms": statistics.median(calls) if calls else None,
                               "max_ms": max(calls) if calls else None}
    return out


def _num(v: Optional[float]) -> str:
    return "undefined" if v is None else f"{v:.3f}"


def markdown(s: Mapping[str, Any]) -> str:
    """The summary as Markdown, for the Metrics section of the evaluation report."""
    o, c = s["official_overall"], s["claims"]
    mr, mc = s["macro_f1_by_rule"], s["macro_f1_by_category"]
    out = [f"# Headline metrics{': ' + s['split'] if s['split'] else ''}", "",
           "| Metric | Value |", "|---|---|",
           f"| Claims · claim-rule pairs | {c['total']} · {o['count']} |",
           f"| Status accuracy | {_num(o['status_accuracy'])} |",
           f"| Issue precision · recall · F1 | {_num(o['issue_precision'])} · {_num(o['issue_recall'])} · {_num(o['issue_f1'])} |",
           f"| Macro F1 over rules | {_num(mr['macro_f1'])} ({mr['defined']} of 15 defined; undefined: {', '.join(mr['undefined']) or 'none'}) |",
           f"| Macro F1 over categories | {_num(mc['macro_f1'])} ({mc['defined']} defined; undefined: {', '.join(mc['undefined']) or 'none'}) |",
           f"| False-alarm rate (pairs) | {_num(o['false_alarm_rate'])} ({o['fp']} false FAIL pairs) |",
           f"| False-alarm claims (no expected FAIL, predicted FAIL) | {c['false_alarm']['count']} of {c['false_alarm']['of']} |",
           f"| Clean claims sent to a reviewer (expected all PASS or NOT_APPLICABLE) | {c['clean_flagged']['count']} of {c['clean_flagged']['of']} |",
           f"| Claim exact match | {c['exact_match']['count']} of {c['exact_match']['of']} |",
           f"| Abstentions: false · missed | {o['false_abstentions']} · {o['missed_abstentions']} |",
           f"| NOT_IMPLEMENTED | {o['not_implemented']} |"]
    lat = s.get("latency")
    if lat:
        r = lat["run"]
        out.append(f"| Run time | {r['duration_ms']} ms for {r['claims']} claims ({r['ms_per_claim']} ms a claim) |")
        e = lat.get("explanations")
        if e:
            out.append(f"| Explanation calls | {e['count']}; median {e['median_ms']} ms, max {e['max_ms']} ms |")
    out += ["", "## Per category", "", "| Category | Rules | tp | fp | fn | Issue F1 |", "|---|---|---:|---:|---:|---:|"]
    out += [f"| {n} | {', '.join(v['rules'])} | {v['tp']} | {v['fp']} | {v['fn']} | {_num(v['issue_f1'])} |"
            for n, v in s["per_category"].items()]
    out += ["", "## Per rule", "", "| Rule | Issue F1 |", "|---|---:|"]
    out += [f"| {r} | {_num(v)} |" for r, v in s["per_rule_f1"].items()]
    out.append("")
    return "\n".join(out)


def _write(path: str, text: str) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description="Macro F1, claim-level rates and latency on top of src/evaluate.py.")
    p.add_argument("--gold", required=True)
    p.add_argument("--pred", required=True)
    p.add_argument("--claims", required=True)
    p.add_argument("--split", help="name printed in the report, e.g. validation")
    p.add_argument("--categories", help=f"rule grouping (default: {CATEGORIES_PATH.name} beside this module)")
    p.add_argument("--manifest", help="the run manifest of --pred, for latency")
    p.add_argument("--explanations", help="the run's explanations file, for model-call latency (needs --manifest)")
    p.add_argument("--output", default="outputs/summary.json")
    p.add_argument("--markdown", help="also write the summary as Markdown to this path")
    a = p.parse_args()
    try:
        rows = load_jsonl(a.claims)
        claims = {c["claim_id"]: c for c in rows}
        if len(rows) != len(claims):
            raise ValueError("Duplicate claim IDs")
        cats = load_categories(a.categories) if a.categories else None
        s = summarize(load_jsonl(a.gold), load_jsonl(a.pred), claims, cats, a.split)
        if a.manifest:
            manifest = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
            s["latency"] = latency(manifest, a.pred, load_jsonl(a.explanations) if a.explanations else None)
    except (ValueError, KeyError, TypeError, IndexError) as e:
        p.exit(2, f"Evaluation rejected: {e}\n")
    _write(a.output, json.dumps(s, indent=2) + "\n")
    if a.markdown:
        _write(a.markdown, markdown(s))
    mr, mc, c = s["macro_f1_by_rule"], s["macro_f1_by_category"], s["claims"]
    print(f"macro F1 over rules {_num(mr['macro_f1'])} ({mr['defined']} defined), over categories {_num(mc['macro_f1'])}; "
          f"false-alarm claims {c['false_alarm']['count']} of {c['false_alarm']['of']}; "
          f"clean claims flagged {c['clean_flagged']['count']} of {c['clean_flagged']['of']}. Report: {a.output}")


if __name__ == "__main__":
    main()
