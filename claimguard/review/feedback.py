"""What reviewers decided, summarized from the audit chain (D5).

    python -m claimguard.review.feedback --log outputs/audit.jsonl [--output outputs/feedback.json]

The challenge asks for "manual overrides and feedback logging". Every review
decision is already in the hash chain; this turns them into feedback:

  by_action, by_actor   every recorded decision
  by_rule               per rule, the latest decision on each finding (a
                        finding is one claim version, rule and status), and
                        how many of those were dismissed
  review_candidates     rules whose findings reviewers dismiss at least
                        `threshold` of the time over at least `min_findings`
                        findings: a sign the rule may flag what reviewers
                        consider fine. They are reported for a rulebook
                        clarification with the mentor (docs/DECISIONS.md),
                        never changed automatically: a rule only changes with
                        a recorded decision and its tests.

This is the first step of the optional "active learning feedback loop from
human overrides": the overrides are measured and surfaced, and a human
decides what to learn from them. The log is verified first; a log that does
not verify is refused.
"""
import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict

from claimguard._pack import load_jsonl
from claimguard.audit import chain

DISMISS = "dismiss_with_reason"


def summarize(log, anchor=None, *, min_findings: int = 5, threshold: float = 0.5) -> Dict[str, Any]:
    """The feedback summary. Raises ValueError if the log does not verify."""
    chain.verify(log, anchor or chain.default_anchor(log))
    decisions = [row["event"] for row in (load_jsonl(log) if Path(log).exists() else [])
                 if row["event"].get("event") == "review_decision"]
    latest = {}
    for e in decisions:  # recorded order: the latest decision on a finding wins
        latest[(e["claim_id"], e.get("input_hash"), e["rule_id"], e["original_status"])] = e
    by_rule: Dict[str, Dict[str, Any]] = {}
    for e in latest.values():
        r = by_rule.setdefault(e["rule_id"], {"findings": 0, "dismissed": 0, "actions": Counter()})
        r["findings"] += 1
        r["dismissed"] += e["action"] == DISMISS
        r["actions"][e["action"]] += 1
    for r in by_rule.values():
        r["dismissal_rate"] = r["dismissed"] / r["findings"]
        r["actions"] = dict(sorted(r["actions"].items()))
    candidates = [
        {"rule_id": rule, "findings": r["findings"], "dismissal_rate": r["dismissal_rate"],
         "suggestion": "Reviewers often dismiss this rule's findings: compare the dismissal reasons with the "
                       "rulebook and raise a clarification with the mentor before changing anything."}
        for rule, r in sorted(by_rule.items()) if r["findings"] >= min_findings and r["dismissal_rate"] >= threshold
    ]
    return {
        "decisions_recorded": len(decisions),
        "findings_decided": len(latest),
        "by_action": dict(sorted(Counter(e["action"] for e in decisions).items())),
        "by_actor": dict(sorted(Counter(e["actor"] for e in decisions).items())),
        "by_rule": dict(sorted(by_rule.items())),
        "review_candidates": candidates,
        "thresholds": {"min_findings": min_findings, "dismissal_rate": threshold},
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--log", default="outputs/audit.jsonl")
    p.add_argument("--anchor", help="chain-head anchor (default: beside the log)")
    p.add_argument("--min-findings", type=int, default=5)
    p.add_argument("--threshold", type=float, default=0.5, help="dismissal rate that makes a rule a candidate")
    p.add_argument("--output", help="also write the summary as JSON")
    a = p.parse_args(argv)
    try:
        s = summarize(a.log, a.anchor, min_findings=a.min_findings, threshold=a.threshold)
    except ValueError as e:
        print(f"Feedback refused: {e}")
        return 2
    if a.output:
        Path(a.output).parent.mkdir(parents=True, exist_ok=True)
        Path(a.output).write_text(json.dumps(s, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not s["decisions_recorded"]:
        print("No review decision is recorded in this log yet.")
        return 0
    print(f"{s['decisions_recorded']} decisions on {s['findings_decided']} findings: "
          + ", ".join(f"{n} {action}" for action, n in s["by_action"].items()))
    for rule, r in s["by_rule"].items():
        print(f"  {rule}: {r['findings']} findings, {r['dismissed']} dismissed ({r['dismissal_rate']:.0%})")
    for c in s["review_candidates"]:
        print(f"Review candidate {c['rule_id']}: {c['suggestion']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
