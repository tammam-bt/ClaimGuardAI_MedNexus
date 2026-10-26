"""The autonomy gate: which claims may proceed, enforced (D2).

    python -m claimguard.review.gate --results outputs/dev_predictions.jsonl \\
        --claims data/development/claims.jsonl --log outputs/audit.jsonl \\
        --directory actors.json [--corrections outputs/corrections] [--output outputs/gate.jsonl]

The review page shows each claim's state, but enforces nothing: decisions
are drafts in one browser until they are appended. This command is the
enforcement. It trusts only the verified audit chain and the actor directory,
and exits non-zero while any claim is blocked, so whatever comes next (a
submission script, a hand-off) can refuse to proceed.

A claim is judged on its latest version: the claim as received, or with
--corrections the newest version python -m claimguard.review.correct wrote.
It is READY when that version's 15 results flag nothing (a clean pre-check,
never payer approval), or when every flagged finding has an explicit
dismissal with a reason by an actor the directory allows, taken on that
version of the claim and on the finding's current status
(claimguard.review.routing.outstanding with input_hash and directory).

Otherwise it is BLOCKED, in the page's own words (outcome() below is the twin
of Core.outcome in claimguard/ui/static/core.js, kept equal by a Node test):

  to_review            no decision yet
  in_review            some findings decided, others not
  correction_needed    a finding was confirmed
  waiting_information  information was requested
  awaiting_recheck     marked corrected; record the correction to recheck it
  rechecked            a corrected version still flags findings and none of
                       them has a decision yet. Decide them on that version:
                       rebuild the page with --corrections, and append with
                       python -m claimguard.ui.decisions --corrections
and, for claims the page never shows:
  rejected             ingestion rejected the claim: there is no version to
                       decide on (DEC-013)
  not_checked          the claim is in the claims file but has no results
  invalid_versions     a stored correction does not follow from the claim as
                       received

Exit code 0 when every claim is ready, 1 while any claim is blocked, 2 when
the audit chain, the directory or the run's files cannot be trusted: then
nothing is judged.
"""
import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from claimguard._pack import load_jsonl
from claimguard.audit import chain
from claimguard.guards.rbac import PermissionDenied, authorize, load_directory
from claimguard.ingest.jsonl import claims_by_id
from claimguard.review.correct import latest_results
from claimguard.review.correction import version_hash
from claimguard.review.routing import outstanding, route_claim

GATE_VERSION = "1.0.0"
READY = "ready"


class GateError(ValueError):
    """The gate cannot judge: an input cannot be trusted."""


def _counts(e: Mapping[str, Any], directory: Optional[Mapping[str, str]]) -> bool:
    if not str(e.get("actor") or "").strip() or not str(e.get("reason") or "").strip():
        return False
    if directory is None:
        return True
    try:
        authorize(directory, e.get("actor"), e.get("action"))
    except PermissionDenied:
        return False
    return True


def outcome(route: Mapping[str, Any], events: Sequence[Mapping[str, Any]], input_hash: Optional[str], *,
            has_versions: bool = False, directory: Optional[Mapping[str, str]] = None) -> str:
    """The claim's state, as Core.outcome computes it in the page. directory
    adds the one check the page cannot make: the actor's role."""
    if not route["reasons"]:
        return READY
    valid = [e for e in events if e.get("claim_id") == route["claim_id"] and e.get("input_hash") == input_hash
             and _counts(e, directory)]
    latest: Dict[Any, Mapping[str, Any]] = {}
    for e in valid:
        latest[(e.get("rule_id"), e.get("original_status"))] = e
    actions = [latest[(r["rule_id"], r["status"])]["action"] for r in route["reasons"]
               if (r["rule_id"], r["status"]) in latest]
    for action, state in (("mark_corrected_for_recheck", "awaiting_recheck"),
                          ("request_information", "waiting_information"), ("confirm_issue", "correction_needed")):
        if action in actions:
            return state
    if not outstanding(route, valid, input_hash=input_hash, directory=directory):
        return READY
    if actions:
        return "in_review"
    return "rechecked" if has_versions else "to_review"


def _decisions(log, anchor, expect=None) -> List[Mapping[str, Any]]:
    try:
        chain.verify(log, anchor or chain.default_anchor(log), expect)
    except chain.AuditError as e:
        error = GateError(f"the audit log cannot be trusted: {e}")
        error.missing_anchor = isinstance(e, chain.MissingAnchor)
        raise error from None
    if not Path(log).exists():
        return []
    return [row["event"] for row in load_jsonl(log) if row["event"].get("event") == "review_decision"]


def judge(results_path, claims_path, log, directory: Mapping[str, str], *, anchor=None,
          corrections=None, expect=None) -> List[Dict[str, Any]]:
    """One row per claim of the claims file, in its order. expect is a
    (count, head) recorded outside this machine. Raises GateError."""
    events = _decisions(log, anchor, expect)
    try:
        results = load_jsonl(results_path)
    except (OSError, ValueError) as e:
        raise GateError(f"the results cannot be read: {type(e).__name__}") from None
    claims = claims_by_id(claims_path)
    by_claim: Dict[str, List[Mapping[str, Any]]] = {}
    for r in results:
        by_claim.setdefault(r["claim_id"], []).append(r)
    unknown = sorted(set(by_claim) - set(claims))
    if unknown:
        raise GateError(f"{len(unknown)} result claim(s) are not in the claims file")

    rows = []
    for claim_id, claim in claims.items():
        row = {"claim_id": claim_id, "version": None, "input_hash": None, "route": None,
               "state": None, "ready": False, "pending": [], "gate_version": GATE_VERSION}
        rows.append(row)
        input_hash = version_hash(claim)
        if input_hash is None:
            row["state"] = "rejected"
            continue
        if claim_id not in by_claim:
            row["state"] = "not_checked"
            continue
        version, claim_results = 1, by_claim[claim_id]
        if corrections:
            try:
                latest, stored = latest_results(claim, corrections)
            except ValueError:
                row["state"] = "invalid_versions"
                continue
            if stored is not None:
                version, input_hash, claim_results = latest.version, latest.input_hash, stored
        route = route_claim(claim_results)
        state = outcome(route, events, input_hash, has_versions=version > 1, directory=directory)
        row.update(version=version, input_hash=input_hash, route=route["route"], state=state, ready=state == READY,
                   pending=[] if state == READY else
                   outstanding(route, events, input_hash=input_hash, directory=directory))
    return rows


def write_rows(path, rows) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def verdict(rows) -> str:
    """One line: how many claims are ready, and why the others are blocked."""
    blocked = Counter(r["state"] for r in rows if not r["ready"])
    ready = len(rows) - sum(blocked.values())
    detail = ", ".join(f"{n} {state}" for state, n in sorted(blocked.items()))
    return f"{len(rows)} claims: {ready} ready, {sum(blocked.values())} blocked" + (f" ({detail})" if detail else "") + "."


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--results", required=True, help="the run's results")
    p.add_argument("--claims", required=True, help="the claims file the run read")
    p.add_argument("--log", required=True, help="the run's audit log, holding the review decisions")
    p.add_argument("--anchor", help="chain-head anchor (default: beside the log)")
    p.add_argument("--directory", required=True, help="JSON {actor: role}, e.g. actors.example.json")
    p.add_argument("--corrections", help="folder written by python -m claimguard.review.correct")
    p.add_argument("--output", help="also write one JSON row per claim to this file")
    chain.add_expect_arguments(p)
    a = p.parse_args(argv)
    expect = chain.expected(p, a)
    try:
        rows = judge(a.results, a.claims, a.log, load_directory(a.directory), anchor=a.anchor,
                     corrections=a.corrections, expect=expect)
        head, count = chain.verify(a.log, a.anchor or chain.default_anchor(a.log))
    except (GateError, ValueError) as e:
        print(f"Gate cannot judge: {e}")
        if getattr(e, "missing_anchor", False):
            print(chain.RESTORE_HINT)
        return 2
    if a.output:
        write_rows(a.output, rows)
    print(verdict(rows))
    if count:
        print(chain.record_hint(count, head))
    return 1 if any(not r["ready"] for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
