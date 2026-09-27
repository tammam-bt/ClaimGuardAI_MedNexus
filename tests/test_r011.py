"""Tests for R011 | Service code in fictional catalogue."""
import unittest

from claimguard.engine.context import RuleContext
from claimguard.rules.r011 import check

RULE = {
    "rule_id": "R011",
    "severity": "high",
    "version": "1.0.0",
    "source": "fictional-rulebook/R011@1.0.0",
    "corrective_action": "Verify the intended code against the supplied teaching catalogue.",
}

CATALOGUE = {
    "SVC-CONSULT": {}, "SVC-LAB": {}, "SVC-IMAGE": {},
    "SVC-THERAPY": {}, "SVC-DENTAL": {}, "SVC-PHARM": {},
}


def make_ctx(service_codes, services=CATALOGUE):
    claim = {
        "claim_id": "CG-TEST-R011",
        "lines": [
            {"line_id": f"L{i + 1}", "service_code": c}
            for i, c in enumerate(service_codes)
        ],
    }
    return RuleContext(
        claim=claim, rule=RULE, policy=None, services=services, prior={},
    )


class R011Tests(unittest.TestCase):
    def test_pass_when_all_codes_in_catalogue(self):
        ctx = make_ctx(["SVC-LAB", "SVC-CONSULT"])
        self.assertEqual(check(ctx).status, "PASS")

    def test_fail_when_code_unknown(self):
        ctx = make_ctx(["SVC-XRAY"])
        v = check(ctx)
        self.assertEqual(v.status, "FAIL")
        self.assertEqual(v.line_ids, ("L1",))

    def test_unknown_when_code_missing(self):
        ctx = make_ctx([None])
        self.assertEqual(check(ctx).status, "UNABLE_TO_ASSESS")

    def test_unknown_when_code_empty_string(self):
        ctx = make_ctx([""])
        self.assertEqual(check(ctx).status, "UNABLE_TO_ASSESS")

    def test_fail_wins_over_unknown_on_another_line(self):
        ctx = make_ctx(["SVC-XRAY", None])
        v = check(ctx)
        self.assertEqual(v.status, "FAIL")
        self.assertEqual(v.line_ids, ("L1",))


if __name__ == "__main__":
    unittest.main()