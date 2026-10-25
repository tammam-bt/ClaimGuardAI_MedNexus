"""Append review decisions downloaded from the interface to the audit chain.

    python -m claimguard.ui.decisions --decisions review_decisions_d8c76c1c.jsonl \\
        --log outputs/audit.jsonl --directory actors.json \\
        --results outputs/dev_predictions.jsonl --claims data/development/claims.jsonl \\
        [--corrections outputs/corrections]

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
  - with --corrections (the folder python -m claimguard.review.correct
    writes), "this version" is the claim's latest version and "current
    status" its rechecked result, exactly as the review gate judges it. A
    decision on an older version is refused: a correction replaces it.

A decision already in the chain is skipped, so appending the same file twice
adds nothing. --directory is required: a JSON file naming each actor's role
(actors.example.json shows the format), loaded by
claimguard.guards.rbac.load_directory. The interface's names are
self-declared (doc 10: no authentication), so this file is the one place a
role comes from, and an actor who is not in it cannot record anything.
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

from claimguard._pack import load_jsonl
from claimguard.audit import chain
from claimguard.guards.rbac import PermissionDenied, authorize_event, load_directory
from claimguard.ingest.jsonl import claims_by_id
from claimguard.review.correct import latest_results
from claimguard.review.correction import version_hash

FIELDS = frozenset(chain.EVENT_FIELDS["review_decision"] | {"event"})
SCHEMA_KEYS = FIELDS - {"event", "input_hash"}  # schemas/review_event.schema.json
FLAGGED = ("FAIL", "UNABLE_TO_ASSESS", "NOT_IMPLEMENTED")


def _iso(value):
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _current(claims, results, corrections):
    """({claim_id: input_hash}, {(claim_id, rule_id): status}) of the version
    a reviewer decides on: the claim as received, or its latest corrected
    version. Raises ValueError if a stored version does not follow."""
    hashes = {cid: version_hash(c) for cid, c in claims.items()}
    status = {(r["claim_id"], r["rule_id"]): r["status"] for r in results}
    if corrections:
        for cid, claim in claims.items():
            if hashes[cid] is None:
                continue
            version, stored = latest_results(claim, corrections)
            if stored is not None:
                hashes[cid] = version.input_hash
                status.update({(cid, r["rule_id"]): r["status"] for r in stored})
    return hashes, status


def check(events, directory, claims, results, corrections=None):
    """Problems with the decisions, one string per problem; empty means all pass.
    claims ({claim_id: claim}) and results are the run's: without them a
    decision on another version or a stale status could not be caught.
    corrections is the folder of corrected versions, if any."""
    hashes, status = _current(claims, results, corrections)
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
        if hashes[e["claim_id"]] is None:
            problems.append(f"{where}: {e['claim_id']} was rejected at ingestion; "
                            "correct the record and re-run before deciding")
            continue
        if e["input_hash"] != hashes[e["claim_id"]]:
            problems.append(f"{where}: taken on another version of {e['claim_id']} (input_hash differs)")
        current = status.get((e["claim_id"], e["rule_id"]))
        if current not in FLAGGED:
            problems.append(f"{where}: {e['claim_id']} {e['rule_id']} is not a finding in this run")
        elif current != e["original_status"]:
            problems.append(f"{where}: taken on status {e['original_status']}, but the result is now {current}")
    return problems


def append_decisions(decisions_path, log, *, claims_path, results_path, directory, anchor=None, corrections=None):
    """Check, then append. Returns a summary; raises ValueError listing every
    problem, having written nothing. directory is {actor: role}: required,
    since without one there is no role to check."""
    events = load_jsonl(decisions_path)
    claims = claims_by_id(claims_path)
    results = load_jsonl(results_path)
    problems = check(events, directory, claims, results, corrections)
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
    p.add_argument("--directory", required=True, help="JSON {actor: role}, e.g. actors.example.json")
    p.add_argument("--claims", required=True, help="the claims file the run read")
    p.add_argument("--results", required=True, help="the run's results")
    p.add_argument("--corrections", help="folder written by python -m claimguard.review.correct: "
                                         "decide on each claim's latest version")
    a = p.parse_args(argv)
    try:
        directory = load_directory(a.directory)
        summary = append_decisions(a.decisions, a.log, anchor=a.anchor, directory=directory,
                                   claims_path=a.claims, results_path=a.results, corrections=a.corrections)
    except (ValueError, chain.AuditError) as e:
        print(e)
        if isinstance(e, chain.MissingAnchor):
            print(chain.RESTORE_HINT)
        return 1
    print(json.dumps(summary, indent=2))
    if summary["events_in_chain"]:
        print(chain.record_hint(summary["events_in_chain"], summary["head"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
