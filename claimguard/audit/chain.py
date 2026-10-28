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
    detected (the gap src/audit.py documents); a log with events and no
    anchor fails too, or deleting the anchor would hide a rewrite
  - a count and head recorded outside this machine (--expect-count,
    --expect-head) detect a rewrite of the log and its anchor together, and
    are the only way to restore a lost anchor (--restore-anchor)

Tamper-evident, not immutable: whoever controls both the log and the anchor
can rewrite both, unless the head is also recorded somewhere they cannot
change. Production needs append-only (WORM) storage and an anchor held
outside the system's control. Concurrent writers are not supported.
"""
import argparse
import hashlib
import json
import re
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


class MissingAnchor(AuditError):
    """The log has events but its anchor file is gone."""


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


def _check_expected(hashes: List[str], expect: Tuple[int, str]) -> None:
    n, expected = expect
    if isinstance(n, bool) or not isinstance(n, int) or n < 1 or not isinstance(expected, str) \
            or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise AuditError("the count recorded outside this machine must be at least 1, "
                         "and its head 64 lowercase hexadecimal characters")
    if len(hashes) < n:
        raise AuditError(f"log has {len(hashes)} events, fewer than the {n} recorded outside this machine")
    if hashes[n - 1] != expected:
        raise AuditError(f"event {n} does not match the head recorded outside this machine: the log was rewritten")


def verify(log, anchor: Optional[str] = None, expect: Optional[Tuple[int, str]] = None) -> Tuple[str, int]:
    """(head, count). Raises AuditError on any broken link; when an anchor
    path is given, if the log has events and no anchor file (MissingAnchor),
    or if events were removed or the log was rewritten; and when expect =
    (count, head) recorded outside this machine is given, unless event count
    still has that head (later appends still pass)."""
    hashes = _hashes(log)
    head, count = (hashes[-1] if hashes else GENESIS), len(hashes)
    if anchor and Path(anchor).exists():
        recorded = json.loads(Path(anchor).read_text(encoding="utf-8"))
        if count < recorded["count"]:
            raise AuditError(f"log has {count} events but the anchor recorded {recorded['count']}: events were removed")
        if recorded["count"] and hashes[recorded["count"] - 1] != recorded["head"]:
            raise AuditError("the anchored head does not match the log: the log was rewritten")
    elif anchor and count:
        raise MissingAnchor(f"log has {count} events but its anchor is missing: the log may have been rewritten")
    if expect:
        _check_expected(hashes, expect)
    return head, count


def restore_anchor(log, anchor: str, expect: Tuple[int, str], *, trust_later: bool = False) -> Tuple[str, int]:
    """Write a new anchor for a log whose anchor was lost, only after its links
    verify and event count has the head recorded outside this machine. Never
    over an existing anchor: overwriting one would hide a rewrite. Events
    after that one are checked against nothing, so they are refused unless
    trust_later is given."""
    if Path(anchor).exists():
        raise AuditError("an anchor already exists: restoring over it would hide a rewrite")
    hashes = _hashes(log)
    _check_expected(hashes, expect)
    later = len(hashes) - expect[0]
    if later and not trust_later:
        raise AuditError(f"{later} event(s) after event {expect[0]} are vouched for by nothing outside this machine; "
                         "record a newer head, or accept them explicitly")
    Path(anchor).parent.mkdir(parents=True, exist_ok=True)
    Path(anchor).write_text(json.dumps({"count": len(hashes), "head": hashes[-1]}) + "\n", encoding="utf-8")
    return hashes[-1], len(hashes)


def append(log, events: Sequence[Mapping[str, Any]], anchor: Optional[str] = None) -> Tuple[str, int]:
    """Append events after verifying the chain; update the anchor. All or nothing:
    every row is hashed and encoded before the first byte is written, so an
    event that cannot be recorded (text that is not valid Unicode, a value
    that is not JSON) refuses the whole batch with AuditError."""
    head, count = verify(log, anchor)
    for event in events:
        _check(event)
    lines: List[bytes] = []
    for position, event in enumerate(events, start=1):
        row = {"sequence": count + 1, "recorded_at": datetime.now(timezone.utc).isoformat(),
               "previous_hash": head, "event": dict(event)}
        try:
            head = digest(row)
            lines.append((json.dumps({**row, "hash": head}, ensure_ascii=False) + "\n").encode("utf-8"))
        except (TypeError, ValueError) as e:  # UnicodeEncodeError is a ValueError
            raise AuditError(f"event {position} of the batch cannot be recorded ({type(e).__name__}); "
                             "nothing was written") from None
        count += 1
    path = Path(log)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as fh:
        fh.write(b"".join(lines))
    if anchor:
        Path(anchor).parent.mkdir(parents=True, exist_ok=True)
        Path(anchor).write_text(json.dumps({"count": count, "head": head}) + "\n", encoding="utf-8")
    return head, count


def add_expect_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("--expect-count", type=int, metavar="N",
                   help="an event count recorded outside this machine (with --expect-head)")
    p.add_argument("--expect-head", metavar="HASH", help="the head recorded with it: event N must still have it")


def expected(p: argparse.ArgumentParser, a: argparse.Namespace) -> Optional[Tuple[int, str]]:
    """(count, head) from --expect-count and --expect-head, which go together."""
    if (a.expect_count is None) != (a.expect_head is None):
        p.error("--expect-count and --expect-head go together")
    return None if a.expect_count is None else (a.expect_count, a.expect_head)


def record_hint(count: int, head: str) -> str:
    return (f"Record this outside this machine (pull request description, email to the mentor, or a git tag): "
            f"--expect-count {count} --expect-head {head}")


RESTORE_HINT = ("If the anchor was lost by accident, restore it against a head recorded outside this machine: "
                "--restore-anchor --expect-count N --expect-head HASH. With no head kept outside there is "
                "nothing to check the log against: whether to trust it is a person's decision, not the tool's.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Verify a ClaimGuard audit chain.")
    p.add_argument("--log", default="outputs/audit.jsonl")
    p.add_argument("--anchor", help="head anchor (default: <log>.head.json beside the log)")
    add_expect_arguments(p)
    p.add_argument("--restore-anchor", action="store_true",
                   help="write a lost anchor, after checking the log against --expect-count and --expect-head")
    p.add_argument("--trust-events-after-head", action="store_true",
                   help="with --restore-anchor: accept events after event N, which nothing outside vouches for")
    a = p.parse_args(argv)
    anchor = a.anchor or default_anchor(a.log)
    expect = expected(p, a)
    if a.restore_anchor and not expect:
        p.error("--restore-anchor needs --expect-count and --expect-head")
    if a.trust_events_after_head and not a.restore_anchor:
        p.error("--trust-events-after-head goes with --restore-anchor")
    try:
        if a.restore_anchor:
            head, count = restore_anchor(a.log, anchor, expect, trust_later=a.trust_events_after_head)
            print(f"Anchor restored: {count} events; head {head}. Anchor: {anchor}")
            return 0
        head, count = verify(a.log, anchor, expect)
    except MissingAnchor as e:
        print(f"Audit chain INVALID: {e}\n{RESTORE_HINT}")
        return 1
    except AuditError as e:
        print(f"Audit chain INVALID: {e}")
        return 1
    print(f"Audit chain valid: {count} events; head {head}. Anchor: {anchor if Path(anchor).exists() else 'none'}")
    if expect:
        print(f"Event {expect[0]} matches the head recorded outside this machine.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
