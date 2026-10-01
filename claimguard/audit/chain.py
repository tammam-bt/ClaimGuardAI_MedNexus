"""U4.4 event types, U4.5 version lineage, U4.6 chain-head anchoring.

Rows use the same format and hash as src/audit.py, so the pack's own verifier
(python src/audit.py --verify --log <log>) accepts a log written here. On top:

  - every event names its type in an "event" key, the team's convention
    (claimguard.ingest, claimguard.guards and claimguard.ai already emit
    ingestion_error, injection_flag and model_failure this way, so their
    records go in unchanged); required fields are checked before anything is
    written, and a batch with one bad event writes nothing
  - an anchor file holds the count and head after every append, so cutting
    events off the end, deleting the log or rewriting it wholesale is
    detected (the gap src/audit.py documents)

Tamper-evident, not immutable: whoever controls both the log and the anchor
can rewrite both. Production needs append-only (WORM) storage and an anchor
held outside the system's control. Concurrent writers are not supported.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

GENESIS = "0" * 64
REVIEW_ACTIONS = {"confirm_issue", "dismiss_with_reason", "request_information", "mark_corrected_for_recheck"}
EVENT_FIELDS: Dict[str, Set[str]] = {
    "run_started": {"run_id", "input_sha256", "engine_version", "rule_versions", "policy_versions"},
    "ingestion_error": {"stage", "reason", "claim_id", "provenance"},
    "injection_flag": {"claim_id", "scanner_version", "hits"},
    "model_failure": {"claim_id", "rule_id", "provider", "model", "prompt_version", "latency_ms", "reason", "detail"},
    "run_finished": {"run_id", "records", "accepted", "rejected", "results", "statuses", "rule_errors",
                     "injection_flags", "manifest_sha256"},
    "review_decision": {"claim_id", "rule_id", "action", "actor", "reason", "created_at", "original_status", "input_hash"},
    "version_created": {"claim_id", "version", "input_hash", "parent_hash", "actor", "reason", "changes"},
}


class AuditError(ValueError):
    """The chain is invalid, or an event would make it so."""


def digest(obj: Any) -> str:
    """Identical to src/audit.py's digest()."""
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def default_anchor(log) -> str:
    return str(Path(log).with_suffix("")) + ".head.json"


def _check(event: Mapping[str, Any]) -> None:
    kind = event.get("event") if isinstance(event, Mapping) else None
    if kind not in EVENT_FIELDS:
        raise AuditError(f"unknown event type {kind!r}")
    missing = EVENT_FIELDS[kind] - set(event)
    if missing:
        raise AuditError(f"{kind} event is missing {sorted(missing)}")
    if kind == "review_decision":
        if event["action"] not in REVIEW_ACTIONS:
            raise AuditError(f"unknown review action {event['action']!r}")
        for field in ("actor", "reason"):
            if not str(event[field] or "").strip():
                raise AuditError(f"review_decision needs a non-blank {field}")


def _hashes(log) -> List[str]:
    path = Path(log)
    if not path.exists():
        return []
    hashes: List[str] = []
    previous = GENESIS
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            row = json.loads(line)
            claimed = row.pop("hash")
            ok = row["sequence"] == number and row["previous_hash"] == previous and digest(row) == claimed
        except (ValueError, KeyError, TypeError, AttributeError):
            ok = False
        if not ok:
            raise AuditError(f"audit chain invalid at event {number}")
        hashes.append(claimed)
        previous = claimed
    return hashes


def verify(log, anchor: Optional[str] = None) -> Tuple[str, int]:
    """(head, count). Raises AuditError on any broken link and, when the anchor
    file exists, if events were removed or the log was rewritten."""
    hashes = _hashes(log)
    head, count = (hashes[-1] if hashes else GENESIS), len(hashes)
    if anchor and Path(anchor).exists():
        recorded = json.loads(Path(anchor).read_text(encoding="utf-8"))
        if count < recorded["count"]:
            raise AuditError(f"log has {count} events but the anchor recorded {recorded['count']}: events were removed")
        if recorded["count"] and hashes[recorded["count"] - 1] != recorded["head"]:
            raise AuditError("the anchored head does not match the log: the log was rewritten")
    return head, count


def append(log, events: Sequence[Mapping[str, Any]], anchor: Optional[str] = None) -> Tuple[str, int]:
    """Append events after verifying the chain; update the anchor. All or nothing."""
    head, count = verify(log, anchor)
    for event in events:
        _check(event)
    path = Path(log)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for event in events:
            row = {"sequence": count + 1, "recorded_at": datetime.now(timezone.utc).isoformat(),
                   "previous_hash": head, "event": dict(event)}
            head = digest(row)
            fh.write(json.dumps({**row, "hash": head}, ensure_ascii=False) + "\n")
            count += 1
    if anchor:
        Path(anchor).parent.mkdir(parents=True, exist_ok=True)
        Path(anchor).write_text(json.dumps({"count": count, "head": head}) + "\n", encoding="utf-8")
    return head, count


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Verify a ClaimGuard audit chain.")
    p.add_argument("--log", default="outputs/audit.jsonl")
    p.add_argument("--anchor", help="head anchor (default: <log>.head.json beside the log)")
    a = p.parse_args(argv)
    anchor = a.anchor or default_anchor(a.log)
    try:
        head, count = verify(a.log, anchor)
    except AuditError as e:
        print(f"Audit chain INVALID: {e}")
        return 1
    print(f"Audit chain valid: {count} events; head {head}. Anchor: {anchor if Path(anchor).exists() else 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
