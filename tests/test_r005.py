"""Tests for R005 | Provider in the supplied network."""
import unittest

from claimguard.engine.context import RuleContext
from claimguard.rules.r005 import check

RULE = {
    "rule_id": "R005",
    "severity": "high",
    "version": "1.0.0",
    "source": "fictional-rulebook/R005@1.0.0",
    "corrective_action": "Verify provider identity and the applicable fictional network list.",
}

POLICY = {
    "policy_id": "EDU-PLUS",
    "allowed_providers": ("EDU-PROV-01", "EDU-PROV-02", "EDU-PROV-03"),
}


def make_ctx(provider_id, policy=POLICY):
    claim = {
        "claim_id": "CG-TEST-R005",
        "provider_id": provider_id,
        "policy_id": policy["policy_id"] if policy else "EDU-NO-POLICY",
        "lines": [],
    }
    return RuleContext(
        claim=claim, rule=RULE, policy=policy, services={}, prior={},
    )


class R005Tests(unittest.TestCase):
    def test_pass_when_provider_in_network(self):
        ctx = make_ctx("EDU-PROV-02")
        self.assertEqual(check(ctx).status, "PASS")

    def test_fail_when_provider_not_in_network(self):
        ctx = make_ctx("EDU-PROV-OUT")
        v = check(ctx)
        self.assertEqual(v.status, "FAIL")
        self.assertEqual(v.line_ids, ())  # claim-level, no line_id

    def test_unknown_when_provider_missing(self):
        ctx = make_ctx(None)
        self.assertEqual(check(ctx).status, "UNABLE_TO_ASSESS")

    def test_unknown_when_no_policy(self):
        # Mirrors the worked case "Unknown policy": single evidence path
        # (/policy_id only) and the fixed cross-rule message.
        ctx = make_ctx("EDU-PROV-02", policy=None)
        v = check(ctx)
        self.assertEqual(v.status, "UNABLE_TO_ASSESS")
        self.assertEqual(v.paths, ("/policy_id",))
        self.assertEqual(v.message, "No policy is supplied for this policy_id.")


if __name__ == "__main__":
    unittest.main()