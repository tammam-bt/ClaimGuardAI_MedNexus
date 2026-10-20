"""Tests for the review feedback summary (claimguard.review.feedback, D5)."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from claimguard.audit.chain import append, default_anchor
from claimguard.review.feedback import summarize, main


def decision(claim, rule, action, actor="Reviewer 01", status="FAIL", h="H1"):
    return {"event": "review_decision", "claim_id": claim, "rule_id": rule, "action": action, "actor": actor,
            "reason": "r", "created_at": "2026-10-19T10:00:00Z", "original_status": status, "input_hash": h}


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "audit.jsonl"
        events = [
            decision("CG-1", "R006", "confirm_issue"),
            decision("CG-1", "R006", "dismiss_with_reason"),        # the latest decision on this finding wins
            decision("CG-2", "R006", "dismiss_with_reason", actor="Reviewer 02"),
            decision("CG-3", "R006", "dismiss_with_reason"),
            decision("CG-4", "R007", "confirm_issue"),
            decision("CG-5", "R007", "dismiss_with_reason"),
            decision("CG-6", "R007", "confirm_issue", h="H2"),
            {"event": "version_created", "claim_id": "CG-6", "version": 2, "input_hash": "H2", "parent_hash": "H1",
             "actor": "Reviewer 01", "reason": "r", "changes": "[]"},
        ]
        append(self.log, events, default_anchor(self.log))

    def tearDown(self):
        self.tmp.cleanup()

    def test_counts_every_recorded_decision_and_the_latest_per_finding(self):
        s = summarize(self.log)
        self.assertEqual(s["decisions_recorded"], 7)
        self.assertEqual(s["findings_decided"], 6)
        self.assertEqual(s["by_action"], {"confirm_issue": 3, "dismiss_with_reason": 4})
        self.assertEqual(s["by_actor"], {"Reviewer 01": 6, "Reviewer 02": 1})
        r006 = s["by_rule"]["R006"]
        self.assertEqual((r006["findings"], r006["dismissed"], r006["dismissal_rate"]), (3, 3, 1.0))
        self.assertEqual(s["by_rule"]["R007"]["dismissal_rate"], 1 / 3)

    def test_often_dismissed_rules_are_flagged_for_review_never_changed(self):
        s = summarize(self.log, min_findings=3, threshold=0.5)
        self.assertEqual([c["rule_id"] for c in s["review_candidates"]], ["R006"])
        self.assertIn("mentor", s["review_candidates"][0]["suggestion"])

    def test_a_tampered_log_is_refused(self):
        self.log.write_text(self.log.read_text(encoding="utf-8").replace("CG-2", "CG-9"), encoding="utf-8")
        with self.assertRaises(ValueError):
            summarize(self.log)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--log", str(self.log)]), 2)

    def test_command_writes_the_summary(self):
        out = Path(self.tmp.name) / "feedback.json"
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            self.assertEqual(main(["--log", str(self.log), "--output", str(out)]), 0)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["decisions_recorded"], 7)
        self.assertIn("R006", printed.getvalue())


if __name__ == "__main__":
    unittest.main()
