"""Tests for the audit chain (claimguard.audit.chain)."""
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout
from pathlib import Path

from claimguard._pack import config, load_jsonl
from claimguard.ai.watchdog import explain_safely
from claimguard.audit.chain import (
    GENESIS, AuditError, MissingAnchor, append, default_anchor, restore_anchor, verify,
)
from claimguard.audit.chain import main as chain_main
from claimguard.engine.runner import Engine
from claimguard.guards import screen
from claimguard.ingest import read_jsonl
from claimguard.review.correction import correct, original
from claimguard.run import main as run_main

ROOT = Path(__file__).resolve().parents[1]
STRESS = ROOT / "data" / "stress" / "claims.jsonl"


def pack_audit():
    spec = importlib.util.spec_from_file_location("pack_audit_for_test", ROOT / "src" / "audit.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def review(**overrides):
    event = {"event": "review_decision", "claim_id": "CG-1", "rule_id": "R001", "action": "confirm_issue",
             "actor": "reviewer-1", "reason": "Invoice number missing on the source bill.",
             "created_at": "2026-10-01T10:00:00+00:00", "original_status": "FAIL", "input_hash": "0" * 64}
    event.update(overrides)
    return event


class ChainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "audit.jsonl"
        self.anchor = default_anchor(self.log)

    def tearDown(self):
        self.tmp.cleanup()

    def three(self):
        append(self.log, [review(claim_id=f"CG-{i}") for i in range(3)], self.anchor)

    def test_default_anchor_sits_beside_the_log(self):
        self.assertEqual(Path(self.anchor).name, "audit.head.json")

    def test_append_then_verify(self):
        head, _ = append(self.log, [review()], self.anchor)
        self.assertEqual(verify(self.log, self.anchor), (head, 1))

    def test_the_packs_own_verifier_accepts_our_log(self):
        self.three()
        self.assertEqual(pack_audit().verify(self.log)[1], 3)

    def test_edited_event_detected(self):
        self.three()
        self.log.write_text(self.log.read_text(encoding="utf-8").replace("CG-1", "CG-9"), encoding="utf-8")
        with self.assertRaisesRegex(AuditError, "event 2"):
            verify(self.log)

    def test_truncation_detected_with_anchor(self):
        self.three()
        lines = self.log.read_text(encoding="utf-8").splitlines()
        self.log.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
        self.assertEqual(verify(self.log)[1], 2)  # without the anchor: the pack's documented gap
        with self.assertRaisesRegex(AuditError, "removed"):
            verify(self.log, self.anchor)

    def test_deleted_log_detected_with_anchor(self):
        self.three()
        self.log.unlink()
        with self.assertRaisesRegex(AuditError, "removed"):
            verify(self.log, self.anchor)

    def test_wholesale_rewrite_detected_with_anchor(self):
        self.three()
        saved = Path(self.anchor).read_text(encoding="utf-8")
        self.log.unlink()
        append(self.log, [review(claim_id=f"CG-X{i}") for i in range(3)])  # a fresh, internally valid chain
        Path(self.anchor).write_text(saved, encoding="utf-8")
        with self.assertRaisesRegex(AuditError, "rewritten"):
            verify(self.log, self.anchor)

    def test_invalid_events_rejected_and_nothing_written(self):
        for bad in ({"event": "made_up"}, {"event": "run_started", "run_id": "r"},
                    review(reason="   "), review(action="approve_payment"), {"type": "review_decision"}):
            with self.subTest(bad=bad), self.assertRaises(AuditError):
                append(self.log, [review(), bad], self.anchor)
        self.assertFalse(self.log.exists())

    def test_a_batch_that_cannot_be_recorded_writes_nothing(self):
        # A reviewer's reason is free text: a lone surrogate passes JSON but
        # cannot be hashed or written as UTF-8. Before the fix the valid event
        # in front of it was written and the anchor was not updated.
        self.three()
        log, anchor = self.log.read_bytes(), Path(self.anchor).read_bytes()
        for bad in (review(reason="bad \ud800 reason"), review(reason={"not", "json"})):
            with self.subTest(bad=type(bad["reason"]).__name__), self.assertRaises(AuditError):
                append(self.log, [review(claim_id="CG-OK"), bad], self.anchor)
            self.assertEqual(self.log.read_bytes(), log)
            self.assertEqual(Path(self.anchor).read_bytes(), anchor)
        self.assertEqual(verify(self.log, self.anchor)[1], 3)

    def test_cannot_append_to_a_broken_chain(self):
        self.three()
        self.log.write_text(self.log.read_text(encoding="utf-8").replace("CG-1", "CG-9"), encoding="utf-8")
        with self.assertRaises(AuditError):
            append(self.log, [review()], self.anchor)

    def test_correction_version_is_a_lineage_event(self):
        claim = load_jsonl(ROOT / "examples" / "first_10_claims.jsonl")[0]
        v2 = correct(original(claim), [{"op": "replace", "path": "/total_amount", "value": claim["total_amount"] + 1}],
                     actor="reviewer-1", reason="Total re-read from the source bill.")
        self.assertEqual(append(self.log, [{"event": "version_created", **v2.record()}], self.anchor)[1], 1)

    def test_the_teams_own_records_go_in_unchanged(self):
        bad_file = Path(self.tmp.name) / "bad.jsonl"
        bad_file.write_text("{nope\n", encoding="utf-8")
        ingestion_error = read_jsonl(bad_file).errors[0]
        claims = load_jsonl(STRESS)
        injection_flag = next(s.as_event() for s in map(screen, claims) if s.flagged)

        class Broken:
            name, model = "broken", None

            def explain(self, finding, rule):
                raise RuntimeError("down")

        finding = next(r for c in claims for r in Engine(ROOT).evaluate_claim(c) if r["status"] == "FAIL")
        rule = {r["rule_id"]: r for r in config(ROOT)["rules"]}[finding["rule_id"]]
        _, model_failure = explain_safely(Broken(), finding, rule, "1.0.0", 1.0)
        _, count = append(self.log, [ingestion_error, injection_flag, model_failure], self.anchor)
        self.assertEqual(count, 3)


class AnchorTests(unittest.TestCase):
    """M2: a missing anchor fails. M3: a head recorded outside this machine,
    and restoring a lost anchor against it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "audit.jsonl"
        self.anchor = default_anchor(self.log)
        self.head2, _ = append(self.log, [review(claim_id=f"CG-{i}") for i in range(2)], self.anchor)
        self.head3, _ = append(self.log, [review(claim_id="CG-2")], self.anchor)

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args):
        with redirect_stdout(io.StringIO()) as printed:
            code = chain_main(["--log", str(self.log), *args])
        return code, printed.getvalue()

    def test_a_missing_anchor_fails_once_the_log_has_events(self):
        Path(self.anchor).unlink()
        with self.assertRaisesRegex(MissingAnchor, "3 events but its anchor is missing"):
            verify(self.log, self.anchor)
        self.assertEqual(verify(self.log)[1], 3)  # no anchor path given: links only, as the pack checks
        fresh = Path(self.tmp.name) / "fresh.jsonl"
        self.assertEqual(verify(fresh, default_anchor(fresh)), (GENESIS, 0))  # a fresh, empty log is fine

    def test_no_append_while_the_anchor_is_missing(self):
        # Otherwise the next append would quietly write a new, matching anchor.
        Path(self.anchor).unlink()
        before = self.log.read_bytes()
        with self.assertRaises(MissingAnchor):
            append(self.log, [review(claim_id="CG-X")], self.anchor)
        self.assertEqual(self.log.read_bytes(), before)
        self.assertFalse(Path(self.anchor).exists())

    def test_a_head_recorded_outside_still_passes_after_later_appends(self):
        self.assertEqual(verify(self.log, self.anchor, (2, self.head2))[1], 3)
        self.assertEqual(verify(self.log, self.anchor, (3, self.head3))[1], 3)

    def test_a_head_recorded_outside_detects_a_rewrite_of_both_files(self):
        events = [json.loads(line)["event"] for line in self.log.read_text(encoding="utf-8").splitlines()]
        events[-1] = {**events[-1], "reason": "Altered later."}
        self.log.unlink()
        Path(self.anchor).unlink()
        append(self.log, events, self.anchor)
        self.assertEqual(verify(self.log, self.anchor)[1], 3)  # the honest limit without an outside head
        for n, head in ((3, self.head3), (2, self.head2)):  # rewritten rows get new times, so new hashes
            with self.subTest(n=n), self.assertRaisesRegex(AuditError, f"event {n} does not match"):
                verify(self.log, self.anchor, (n, head))

    def test_a_head_recorded_outside_covers_only_events_up_to_it(self):
        # Keep events 1 and 2 byte for byte, replace event 3, and anchor that.
        lines = self.log.read_text(encoding="utf-8").splitlines(keepends=True)
        self.log.write_text("".join(lines[:2]), encoding="utf-8")
        Path(self.anchor).write_text(json.dumps({"count": 2, "head": self.head2}), encoding="utf-8")
        append(self.log, [review(claim_id="CG-2", reason="Altered later.")], self.anchor)
        self.assertEqual(verify(self.log, self.anchor, (2, self.head2))[1], 3)
        with self.assertRaisesRegex(AuditError, "event 3 does not match"):
            verify(self.log, self.anchor, (3, self.head3))

    def test_a_shorter_log_or_a_malformed_expectation_fails(self):
        with self.assertRaisesRegex(AuditError, "fewer than the 5"):
            verify(self.log, self.anchor, (5, self.head3))
        for bad in ((0, self.head3), (True, self.head3), (2, "XYZ"), (2, self.head2.upper())):
            with self.subTest(bad=bad), self.assertRaisesRegex(AuditError, "at least 1"):
                verify(self.log, self.anchor, bad)

    def test_restore_with_the_right_head_lets_appends_work_again(self):
        Path(self.anchor).unlink()
        self.assertEqual(restore_anchor(self.log, self.anchor, (3, self.head3)), (self.head3, 3))
        self.assertEqual(append(self.log, [review(claim_id="CG-3")], self.anchor)[1], 4)

    def test_restore_refuses_and_writes_nothing(self):
        Path(self.anchor).unlink()
        for expect, why in (((3, "0" * 64), "event 3 does not match"),
                            ((2, self.head2), "1 event\\(s\\) after event 2")):
            with self.subTest(why=why), self.assertRaisesRegex(AuditError, why):
                restore_anchor(self.log, self.anchor, expect)
            self.assertFalse(Path(self.anchor).exists())
        self.assertEqual(restore_anchor(self.log, self.anchor, (2, self.head2), trust_later=True), (self.head3, 3))

    def test_restore_never_overwrites_an_anchor(self):
        # Overwriting a present anchor is exactly the rewrite M2 detects.
        before = Path(self.anchor).read_bytes()
        with self.assertRaisesRegex(AuditError, "already exists"):
            restore_anchor(self.log, self.anchor, (3, self.head3))
        self.assertEqual(Path(self.anchor).read_bytes(), before)

    def test_command(self):
        self.assertEqual(self.cli("--expect-count", "2", "--expect-head", self.head2)[0], 0)
        self.assertEqual(self.cli("--expect-count", "2", "--expect-head", "0" * 64)[0], 1)
        Path(self.anchor).unlink()
        code, printed = self.cli()
        self.assertEqual(code, 1)
        self.assertIn("--restore-anchor", printed)  # the error names the way out
        self.assertEqual(self.cli("--restore-anchor", "--expect-count", "3", "--expect-head", self.head3)[0], 0)
        self.assertEqual(self.cli()[0], 0)
        for args in (("--expect-count", "3"), ("--restore-anchor",), ("--trust-events-after-head",)):
            with self.subTest(args=args), redirect_stdout(io.StringIO()), \
                    unittest.mock.patch("sys.stderr", io.StringIO()), self.assertRaises(SystemExit):
                chain_main(["--log", str(self.log), *args])


class RunWritesAuditTests(unittest.TestCase):
    def test_run_records_start_flags_and_finish(self):
        with tempfile.TemporaryDirectory() as d:
            out, log = Path(d) / "p.jsonl", Path(d) / "audit.jsonl"
            with redirect_stdout(io.StringIO()):
                code = run_main(["--strict", "--input", str(STRESS), "--output", str(out), "--audit-log", str(log)])
            self.assertEqual(code, 0)
            events = [json.loads(l)["event"] for l in log.read_text(encoding="utf-8").splitlines()]
            kinds = [e["event"] for e in events]
            self.assertEqual((kinds[0], kinds[-1]), ("run_started", "run_finished"))
            self.assertTrue(kinds.count("injection_flag") >= 1)
            self.assertEqual(len({e["run_id"] for e in events}), 1)
            manifest = Path(f"{out}.manifest.json")
            self.assertEqual(events[-1]["manifest_sha256"], hashlib.sha256(manifest.read_bytes()).hexdigest())
            self.assertEqual(verify(log, default_anchor(log))[1], len(events))


if __name__ == "__main__":
    unittest.main()
