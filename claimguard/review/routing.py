"""Escalation routing (DEC-004).

"Route low-confidence or high-severity cases for explicit human approval."

Our checks are deterministic, so confidence is null and never "low". Here
low-confidence means the engine abstained (UNABLE_TO_ASSESS) or never ran
(NOT_IMPLEMENTED); high-severity is the rule's severity on a FAIL or
UNABLE_TO_ASSESS. An LLM score is uncalibrated and is never read.

    ESCALATE  any high-severity FAIL / UNABLE_TO_ASSESS, or any NOT_IMPLEMENTED
    REVIEW    only medium- or low-severity FAIL / UNABLE_TO_ASSESS
    CLEAR     every result PASS or NOT_APPLICABLE ("pre-check clean", not approval)

Routing is its own output, one row per claim. It is never a field on a result
row: evaluate.py rejects any key beyond schemas/result.schema.json. Approval is
read from review events (schemas/review_event.schema.json) and never changes a
finding; a dismissed FAIL stays FAIL (docs/10).

    python -m claimguard.review.routing --input outputs/dev_predictions.jsonl --output outputs/dev_routing.jsonl
"""
import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from claimguard._pack import STATUSES, load_jsonl

ROUTING_POLICY_VERSION = "1.0.0"
"""Bump when the table above changes, and record it in the audit trail."""

ESCALATE, REVIEW, CLEAR = "ESCALATE", "REVIEW", "CLEAR"
FLAGGED = ("FAIL", "UNABLE_TO_ASSESS", "NOT_IMPLEMENTED")
RULE_IDS = tuple(f"R{i:03}" for i in range(1, 16))
APPROVAL = "dismiss_with_reason"
"""The one review action that lets a flagged finding proceed. confirm_issue,
request_information and mark_corrected_for_recheck all keep the claim blocked;
a correction is a new claim version and a re-run, routed again."""


def route_claim(results: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Route one claim from its results, exactly one per rule R001-R015.

    Raises ValueError for a set that is incomplete, duplicated, mixes claims or
    has an unknown status: a claim missing a result must never route CLEAR.
    """
    claim_ids = sorted({r["claim_id"] for r in results})
    if len(claim_ids) != 1:
        raise ValueError(f"expected results for exactly one claim, got {claim_ids}")
    claim_id = claim_ids[0]
    if sorted(r["rule_id"] for r in results) != list(RULE_IDS):
        raise ValueError(f"{claim_id}: expected one result per rule R001-R015")
    for r in results:
        if r["status"] not in STATUSES:
            raise ValueError(f"{claim_id} {r['rule_id']}: unknown status {r['status']!r}")

    flagged = sorted((r for r in results if r["status"] in FLAGGED), key=lambda r: r["rule_id"])
    if any(r["status"] == "NOT_IMPLEMENTED" or r["severity"] == "high" for r in flagged):
        route = ESCALATE
    elif flagged:
        route = REVIEW
    else:
        route = CLEAR
    return {
        "claim_id": claim_id,
        "route": route,
        "reasons": [{"rule_id": r["rule_id"], "status": r["status"], "severity": r["severity"]} for r in flagged],
        "routing_policy_version": ROUTING_POLICY_VERSION,
    }


def route_run(results: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Route every claim in a run, in the order claims first appear."""
    by_claim: Dict[str, List[Mapping[str, Any]]] = {}
    for r in results:
        by_claim.setdefault(r["claim_id"], []).append(r)
    return [route_claim(rows) for rows in by_claim.values()]


def outstanding(routing: Mapping[str, Any], events: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Flagged findings still lacking explicit approval. Empty means approved.

    events must be in recorded order (e.g. read from the audit log). Per
    finding, the latest event counts, among those that are for this claim and
    rule, carry a non-blank actor and reason, and whose original_status equals
    the finding's current status (a decision on an earlier result is stale).
    Anything else does not count, so a malformed event can never approve.
    """
    latest: Dict[Tuple[Any, Any], Any] = {}
    for e in events:
        if e.get("claim_id") != routing["claim_id"]:
            continue
        if not str(e.get("actor") or "").strip() or not str(e.get("reason") or "").strip():
            continue
        latest[(e.get("rule_id"), e.get("original_status"))] = e.get("action")

    pending = []
    for reason in routing["reasons"]:
        action = latest.get((reason["rule_id"], reason["status"]))
        if reason["status"] == "NOT_IMPLEMENTED":
            why = "check not implemented; cannot be dismissed"
        elif action is None:
            why = "no review decision recorded"
        elif action != APPROVAL:
            why = f"latest decision is {action}"
        else:
            continue
        pending.append({**reason, "why": why})
    return pending


def main() -> None:
    p = argparse.ArgumentParser(description="Route each claim in a results file (DEC-004).")
    p.add_argument("--input", required=True, help="claim-rule results, JSONL")
    p.add_argument("--output", default="outputs/routing.jsonl")
    a = p.parse_args()
    rows = route_run(load_jsonl(a.input))
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    counts = Counter(r["route"] for r in rows)
    print(json.dumps({k: counts[k] for k in (ESCALATE, REVIEW, CLEAR)}), "->", out)


if __name__ == "__main__":
    main()
