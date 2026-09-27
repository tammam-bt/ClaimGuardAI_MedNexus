"""Tests for R015 | Currency matches policy."""
import unittest

from claimguard.engine.context import RuleContext
from claimguard.rules.r015 import check

RULE = {
    "rule_id": "R015",
    "severity": "high",
    "version": "1.0.0",
    "source": "fictional-rulebook/R015@1.0.0",
    "corrective_action": "Verify and correct the declared currency against the source bill.",
}

POLICY = {"policy_id": "EDU-PLUS", "currency": "SAR"}


def make_ctx(currency, policy=POLICY):
    claim = {
        "claim_id": "CG-TEST-R015",
        "currency": currency,
        "policy_id": policy["policy_id"] if policy else "EDU-NO-POLICY",
        "lines": [],
    }
    return RuleContext(
        claim=claim, rule=RULE, policy=policy, services={}, prior={},
    )


class R015Tests(unittest.TestCase):
    def test_pass_when_currency_matches_policy(self):
        ctx = make_ctx("SAR")
        self.assertEqual(check(ctx).status, "PASS")

    def test_fail_when_currency_differs(self):
        ctx = make_ctx("USD")
        v = check(ctx)
        self.assertEqual(v.status, "FAIL")
        self.assertEqual(v.line_ids, ()) 

    def test_unknown_when_currency_missing(self):
        ctx = make_ctx(None)
        self.assertEqual(check(ctx).status, "UNABLE_TO_ASSESS")

    def test_unknown_when_no_policy(self):    
        ctx = make_ctx("SAR", policy=None)
        v = check(ctx)
        self.assertEqual(v.status, "UNABLE_TO_ASSESS")
        self.assertEqual(v.paths, ("/policy_id",))
        self.assertEqual(v.message, "No policy is supplied for this policy_id.")


if __name__ == "__main__":
    unittest.main()