"""Tests for R002 | Service and submission chronology."""
import unittest

from claimguard.engine.context import RuleContext
from claimguard.rules.r002 import check

RULE = {
    "rule_id": "R002",
    "severity": "high",
    "version": "1.0.0",
    "source": "fictional-rulebook/R002@1.0.0",
    "corrective_action": "Verify and correct dates against the original record.",
}


def make_ctx(submission_date, service_dates):
    claim = {
        "claim_id": "CG-TEST-R002",
        "submission_date": submission_date,
        "lines": [
            {"line_id": f"L{i + 1}", "service_date": d}
            for i, d in enumerate(service_dates)
        ],
    }
    return RuleContext(
        claim=claim, rule=RULE, policy=None, services={}, prior={},
    )


class R002Tests(unittest.TestCase):
    def test_pass_when_all_service_dates_before_submission(self):
        ctx = make_ctx("2026-03-10", ["2026-03-01", "2026-03-05"])
        self.assertEqual(check(ctx).status, "PASS")

    def test_pass_on_equal_boundary(self):
        ctx = make_ctx("2026-03-10", ["2026-03-10"])
        v = check(ctx)
        self.assertEqual(v.status, "PASS")

    def test_fail_when_service_date_after_submission(self):
        ctx = make_ctx("2026-03-01", ["2026-03-05"])
        v = check(ctx)
        self.assertEqual(v.status, "FAIL")
        self.assertEqual(v.line_ids, ("L1",))

    def test_fail_wins_even_with_another_unknown_line(self):
        ctx = make_ctx("2026-03-01", ["2026-03-05", None])
        v = check(ctx)
        self.assertEqual(v.status, "FAIL")
        self.assertEqual(v.line_ids, ("L1",))

    def test_unknown_when_service_date_missing(self):
        ctx = make_ctx("2026-03-10", [None])
        self.assertEqual(check(ctx).status, "UNABLE_TO_ASSESS")

    def test_unknown_when_submission_date_missing(self):
        ctx = make_ctx(None, ["2026-03-01"])
        self.assertEqual(check(ctx).status, "UNABLE_TO_ASSESS")


if __name__ == "__main__":
    unittest.main()