"""Correct a claim, recheck it as a new version, and record the version.

    python -m claimguard.review.correct --claims data/development/claims.jsonl \\
        --claim-id CG-B39790AC3604 --changes fix.json \\
        --actor "Reviewer 01" --reason "Authorization added from the source record." \\
        --log outputs/audit.jsonl --output outputs/corrections

fix.json is a list of JSON Patch operations (replace, add into an array,
remove from an array), as claimguard.review.correction accepts them:

    [{"op": "replace", "path": "/lines/0/authorization_id", "value": "AUTH-CG-B39790AC3604-1"}]

The claim as received is version 1 and is never edited. The correction makes
version 2, all 15 rules run on it (correction.recheck), and the command:

  - writes <output>/<claim_id>.v2.json: the version record (hashes, actor,
    reason, changes), the corrected claim, its 15 results and the status
    changes, which the interface reads with --corrections;
  - with --log, appends a version_created event to the audit chain;
  - prints what moved, e.g. R008 FAIL -> PASS.

A rule that crashes during the recheck is reported as UNABLE_TO_ASSESS, as in
a run: the version is still written, its rule_errors list the crash, and the
command exits with 2.

A correction that changes nothing, a blank actor or reason, an invalid
operation, an edit to an identifier, or a corrected claim that fails the
transport contract is refused, and nothing is written (DEC-011).
"""
import argparse
import json
from pathlib import Path

from claimguard._pack import load_jsonl
from claimguard.audit import chain
from claimguard.review.correction import original, recheck, rule_engine


def correct_claim(claims_path, claim_id, changes, *, actor, reason, output, log=None, anchor=None):
    """Recheck one correction; returns the written record. Raises ValueError, writing nothing."""
    claims = {c["claim_id"]: c for c in load_jsonl(claims_path)}
    if claim_id not in claims:
        raise ValueError(f"claim {claim_id} is not in {claims_path}")
    if not isinstance(changes, list):
        raise ValueError("changes must be a JSON list of operations")
    run = recheck(original(claims[claim_id]), changes, actor=actor, reason=reason, engine=rule_engine())
    record = {**run.version.record(), "claim": run.version.claim, "results": run.results,
              "status_changes": run.status_changes, "rule_errors": run.rule_errors}
    out = Path(output) / f"{claim_id}.v{run.version.version}.json"
    if log:
        # The chain first: if it refuses, no version file claims to be recorded.
        chain.append(log, [{"event": "version_created", **run.version.record()}], anchor or chain.default_anchor(log))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out, record


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--claims", required=True)
    p.add_argument("--claim-id", required=True)
    p.add_argument("--changes", required=True, help="JSON file: a list of JSON Patch operations")
    p.add_argument("--actor", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--output", default="outputs/corrections")
    p.add_argument("--log", help="audit log to record the version in")
    p.add_argument("--anchor")
    a = p.parse_args(argv)
    try:
        changes = json.loads(Path(a.changes).read_text(encoding="utf-8"))
        out, record = correct_claim(a.claims, a.claim_id, changes, actor=a.actor, reason=a.reason,
                                    output=a.output, log=a.log, anchor=a.anchor)
    except (ValueError, chain.AuditError) as e:
        print(f"Correction refused: {e}")
        return 1
    moved = ", ".join(f"{c['rule_id']} {c['before']} -> {c['after']}" for c in record["status_changes"]) or "no status changed"
    print(f"{a.claim_id} v{record['version']} ({record['input_hash'][:12]}): {moved}. Written: {out}")
    for e in record["rule_errors"]:
        print(f"Rule error: {e['rule_id']} failed on version {e['version']} ({e['error']}); "
              f"its result is UNABLE_TO_ASSESS.")
    return 2 if record["rule_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
