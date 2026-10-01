"""Append review decisions downloaded from the interface to the audit chain.

    python -m claimguard.ui.decisions --decisions review_decisions_d8c76c1c.jsonl \\
        --log outputs/audit.jsonl \\
        --results outputs/dev_predictions.jsonl --claims data/development/claims.jsonl

Every decision is checked before anything is written, and one bad decision
writes nothing:

  - it has exactly the review_decision fields claimguard.audit.chain records;
  - it passes claimguard.guards.rbac.authorize_event: the review-event schema's
    keys, a known actor whose role may take the action, and a reason;
  - created_at is an ISO date-time;
  - the claim is in this run (--claims), the decision was taken on this
    version of it (input_hash), on a finding the run flagged (--results), and
    on that finding's current status (original_status). A decision taken on
    an older result is refused rather than recorded as if it were current.
    Both files are required, so these checks always run.

A decision already in the chain is skipped, so appending the same file twice
adds nothing. --directory is a JSON file naming each actor's role
({"Reviewer 01": "reviewer"}). Without it every actor is a reviewer, which is
what the interface's self-declared names are (doc 10: no authentication).
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

from claimguard._pack import load_jsonl
from claimguard.audit import chain
from claimguard.guards.rbac import PermissionDenied, authorize_event
from claimguard.review.correction import original

FIELDS = frozenset(chain.EVENT_FIELDS["review_decision"] | {"event"})
SCHEMA_KEYS = FIELDS - {"event", "input_hash"}  # schemas/review_event.schema.json
FLAGGED = ("FAIL", "UNABLE_TO_ASSESS", "NOT_IMPLEMENTED")


def _iso(value):
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def check(events, directory, claims, results):
    """Problems with the decisions, one string per problem; empty means all pass.
    claims ({claim_id: claim}) and results are the run's: without them a
    decision on another version or a stale status could not be caught."""
    hashes = {cid: original(c).input_hash for cid, c in claims.items()}
    status = {(r["claim_id"], r["rule_id"]): r["status"] for r in results}
    problems = []
    for n, e in enumerate(events, start=1):
        where = f"decision {n}"
        if not isinstance(e, dict) or set(e) != FIELDS or e.get("event") != "review_decision":
            problems.append(f"{where}: not a review_decision event with exactly the fields {sorted(FIELDS)}")
            continue
        try:
            authorize_event(directory, {k: e[k] for k in SCHEMA_KEYS})
        except PermissionDenied as err:
            problems.append(f"{where}: {err}")
            continue
        if not _iso(e["created_at"]):
            problems.append(f"{where}: created_at is not an ISO date-time")
        if e["claim_id"] not in hashes:
            problems.append(f"{where}: claim {e['claim_id']} is not in the claims file")
            continue
        if e["input_hash"] != hashes[e["claim_id"]]:
            problems.append(f"{where}: taken on another version of {e['claim_id']} (input_hash differs)")
        current = status.get((e["claim_id"], e["rule_id"]))
        if current not in FLAGGED:
            problems.append(f"{where}: {e['claim_id']} {e['rule_id']} is not a finding in this run")
        elif current != e["original_status"]:
            problems.append(f"{where}: taken on status {e['original_status']}, but the result is now {current}")
    return problems


def append_decisions(decisions_path, log, *, claims_path, results_path, anchor=None, directory=None):
    """Check, then append. Returns a summary; raises ValueError listing every
    problem, having written nothing."""
    events = load_jsonl(decisions_path)
    if directory is None:
        directory = {e["actor"]: "reviewer" for e in events if isinstance(e, dict) and isinstance(e.get("actor"), str)}
    claims = {c["claim_id"]: c for c in load_jsonl(claims_path)}
    results = load_jsonl(results_path)
    problems = check(events, directory, claims, results)
    if problems:
        raise ValueError("no decision appended:\n  " + "\n  ".join(problems))
    anchor = anchor or chain.default_anchor(log)
    recorded = [row["event"] for row in load_jsonl(log)] if Path(log).exists() else []
    new = [e for e in events if e not in recorded]
    head, count = chain.append(log, new, anchor) if new else chain.verify(log, anchor)
    return {"read": len(events), "appended": len(new), "already_in_chain": len(events) - len(new),
            "events_in_chain": count, "head": head}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--decisions", required=True, help="the file downloaded from the interface")
    p.add_argument("--log", required=True, help="the run's audit log")
    p.add_argument("--anchor", help="chain-head anchor (default: beside the log)")
    p.add_argument("--directory", help="JSON {actor: role}; default: every actor is a reviewer")
    p.add_argument("--claims", required=True, help="the claims file the run read")
    p.add_argument("--results", required=True, help="the run's results")
    a = p.parse_args(argv)
    directory = json.loads(Path(a.directory).read_text(encoding="utf-8")) if a.directory else None
    try:
        summary = append_decisions(a.decisions, a.log, anchor=a.anchor, directory=directory,
                                   claims_path=a.claims, results_path=a.results)
    except (ValueError, chain.AuditError) as e:
        print(e)
        return 1
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
