"""Tests for the tamper demonstration (claimguard.audit.tamper_demo, E5)."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from claimguard.audit.chain import append, default_anchor
from claimguard.audit.tamper_demo import SCENARIOS, main, run


def review(i):
    return {"event": "review_decision", "claim_id": f"CG-{i}", "rule_id": "R001", "action": "confirm_issue",
            "actor": "Reviewer 01", "reason": "Seen at the source.", "created_at": "2026-10-19T10:00:00+00:00",
            "original_status": "FAIL", "input_hash": "0" * 64}


class TamperDemoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "audit.jsonl"
        self.anchor = default_anchor(self.log)
        append(self.log, [review(i) for i in range(3)], self.anchor)

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_scenario_behaves_as_stated(self):
        rows = run(self.log)
        self.assertEqual([r["scenario"] for r in rows], [name for name, _, _ in SCENARIOS])
        self.assertTrue(all(r["as_stated"] for r in rows), rows)
        outcome = {r["scenario"]: r["outcome"] for r in rows}
        self.assertTrue(outcome["untouched"].startswith("verifies"))
        self.assertIn("invalid at event", outcome["one event edited"])
        self.assertIn("removed", outcome["last event removed"])
        self.assertIn("rewritten", outcome["history rewritten"])
        self.assertIn("anchor is missing", outcome["anchor deleted, history rewritten"])
        self.assertTrue(outcome["log and anchor both rewritten"].startswith("NOT detected"))
        self.assertIn("recorded outside this machine", outcome["both rewritten, head held outside"])

    def test_a_log_without_its_anchor_is_refused(self):
        Path(self.anchor).unlink()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--log", str(self.log)]), 1)

    def test_the_real_log_is_only_read(self):
        before = (self.log.read_bytes(), Path(self.anchor).read_bytes())
        run(self.log)
        self.assertEqual((self.log.read_bytes(), Path(self.anchor).read_bytes()), before)

    def test_command(self):
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            self.assertEqual(main(["--log", str(self.log)]), 0)
        self.assertIn("not immutable", printed.getvalue())

    def test_refuses_a_log_that_does_not_verify_or_is_too_short(self):
        broken = Path(self.tmp.name) / "broken.jsonl"
        broken.write_text(self.log.read_text(encoding="utf-8").replace("CG-1", "CG-9"), encoding="utf-8")
        short = Path(self.tmp.name) / "short.jsonl"
        append(short, [review(0)], default_anchor(short))
        for log in (broken, short, Path(self.tmp.name) / "absent.jsonl"):
            with self.subTest(log=log.name), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--log", str(log)]), 1)


if __name__ == "__main__":
    unittest.main()
