"""A live demonstration of what the audit chain detects, and what it cannot.

Doc 10: "Demonstrate prototype tamper detection and state which of these
controls you actually implemented. Do not label a mutable local JSON file
immutable."

    python -m claimguard.audit.tamper_demo --log outputs/audit.jsonl

Every scenario runs on copies of the log and its anchor in a temporary
folder; the real files are only read. One line per scenario:

  untouched                verifies
  one event edited         detected: its hash no longer matches
  last event removed       detected by the anchor: events were removed
  log deleted              detected by the anchor
  history rewritten        detected by the anchor: a fresh, internally valid
                           chain of as many events, the last one altered
  anchor deleted, history  detected: a log with events and no anchor fails
  rewritten
  log and anchor both      NOT detected: whoever controls both files can
  rewritten                rewrite both. Tamper-evident, not immutable
  both rewritten, head     detected: event N no longer has the head recorded
  held outside             outside this machine (--expect-count,
                           --expect-head); see docs/PRIVACY_SECURITY.md

Exit code 0 when every scenario behaves exactly as stated, 1 otherwise.
"""
import argparse
import json
import shutil
import tempfile
from pathlib import Path
from typing import Callable, List, Tuple

from claimguard.audit import chain

UNDETECTED = "NOT detected"


def _events(log: Path) -> List[dict]:
    return [json.loads(line)["event"] for line in log.read_text(encoding="utf-8").splitlines()]


def _edit_one(log: Path, anchor: Path) -> None:
    lines = log.read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[len(lines) // 2])
    row["event"] = {**row["event"], "tampered": True}  # the hash field is left as it was
    lines[len(lines) // 2] = json.dumps(row, ensure_ascii=False)
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _drop_last(log: Path, anchor: Path) -> None:
    lines = log.read_text(encoding="utf-8").splitlines()
    log.write_text("".join(line + "\n" for line in lines[:-1]), encoding="utf-8")


def _delete(log: Path, anchor: Path) -> None:
    log.unlink()


def _altered_history(log: Path) -> List[dict]:
    """The same number of events, the last one changed: a quiet rewrite."""
    events = _events(log)
    events[-1] = {**events[-1], "tampered": True}
    return events


def _rewrite_log(log: Path, anchor: Path) -> None:
    events = _altered_history(log)
    log.unlink()
    chain.append(log, events)  # a fresh, internally valid chain; the recorded anchor stays


def _rewrite_drop_anchor(log: Path, anchor: Path) -> None:
    events = _altered_history(log)
    log.unlink()
    anchor.unlink()
    chain.append(log, events)  # no anchor written: the missing anchor gives it away


def _rewrite_both(log: Path, anchor: Path) -> None:
    events = _altered_history(log)
    log.unlink()
    anchor.unlink()
    chain.append(log, events, str(anchor))


SCENARIOS: List[Tuple[str, Callable[[Path, Path], None], bool]] = [
    # (name, tampering, should be detected)
    ("untouched", lambda log, anchor: None, False),
    ("one event edited", _edit_one, True),
    ("last event removed", _drop_last, True),
    ("log deleted", _delete, True),
    ("history rewritten", _rewrite_log, True),
    ("anchor deleted, history rewritten", _rewrite_drop_anchor, True),
    ("log and anchor both rewritten", _rewrite_both, False),
    ("both rewritten, head held outside", _rewrite_both, True),
]
# Verified against the real log's count and head, as if recorded outside this
# machine before the tampering (--expect-count, --expect-head).
HELD_OUTSIDE = {"both rewritten, head held outside"}


def run(log, anchor=None) -> List[dict]:
    """One row per scenario: name, outcome text, whether it behaved as stated."""
    log = Path(log)
    anchor = Path(anchor or chain.default_anchor(log))
    head, count = chain.verify(log, str(anchor))  # the real log must verify first
    if count < 2:
        raise chain.AuditError("the demonstration needs a verified log with at least 2 events")
    rows = []
    for name, tamper, should_detect in SCENARIOS:
        with tempfile.TemporaryDirectory() as d:
            copy, copy_anchor = Path(d) / log.name, Path(d) / "anchor.json"
            shutil.copy(log, copy)
            shutil.copy(anchor, copy_anchor)
            tamper(copy, copy_anchor)
            try:
                n = chain.verify(copy, str(copy_anchor), (count, head) if name in HELD_OUTSIDE else None)[1]
                outcome, detected = f"verifies ({n} events)", False
            except chain.AuditError as e:
                outcome, detected = f"detected: {e}", True
            if not detected and name != "untouched":
                outcome = f"{UNDETECTED}: {outcome}, the last event silently altered"
        rows.append({"scenario": name, "outcome": outcome, "as_stated": detected == should_detect})
    return rows


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--log", default="outputs/audit.jsonl")
    p.add_argument("--anchor", help="head anchor (default: <log>.head.json beside the log)")
    a = p.parse_args(argv)
    try:
        rows = run(a.log, a.anchor)
    except (OSError, chain.AuditError) as e:
        print(f"Cannot demonstrate on this log: {e}")
        return 1
    width = max(len(r["scenario"]) for r in rows)
    for r in rows:
        print(f"{r['scenario']:<{width}}  {r['outcome']}")
    print("Tamper-evident, not immutable: rewriting both the log and its anchor goes undetected "
          "unless the head is also recorded outside this machine (--expect-count, --expect-head).")
    return 0 if all(r["as_stated"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
