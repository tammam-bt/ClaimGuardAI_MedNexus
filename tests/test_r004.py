"""Tests for R004 | Member and beneficiary consistency."""
import unittest

from claimguard.engine.context import RuleContext
from claimguard.rules.r004 import check

RULE = {
    "rule_id": "R004",
    "severity": "high",
    "version": "1.0.0",
    "source": "fictional-rulebook/R004@1.0.0",
    "corrective_action": "Resolve the patient/member mismatch using the authoritative records.",
}


def make_ctx(patient_id, member_id, beneficiary_id, coverage_member_id):
    claim = {
        "claim_id": "CG-TEST-R004",
        "patient_id": patient_id,
        "member_id": member_id,
        "coverage": {
            "beneficiary_patient_id": beneficiary_id,
            "member_id": coverage_member_id,
        },
        "lines": [],
    }
    return RuleContext(
        claim=claim, rule=RULE, policy=None, services={}, prior={},
    )


class R004Tests(unittest.TestCase):
    def test_pass_when_both_match_exactly(self):
        ctx = make_ctx("PAT001", "MEM001", "PAT001", "MEM001")
        self.assertEqual(check(ctx).status, "PASS")

    def test_fail_when_patient_id_mismatches(self):
        ctx = make_ctx("PAT001", "MEM001", "PAT002", "MEM001")
        self.assertEqual(check(ctx).status, "FAIL")

    def test_fail_is_case_sensitive(self):
        ctx = make_ctx("PAT001", "MEM001", "pat001", "MEM001")
        self.assertEqual(check(ctx).status, "FAIL")

    def test_fail_when_member_id_mismatches(self):
        ctx = make_ctx("PAT001", "MEM001", "PAT001", "MEM002")
        self.assertEqual(check(ctx).status, "FAIL")

    def test_unknown_when_patient_id_missing(self):
        ctx = make_ctx(None, "MEM001", "PAT001", "MEM001")
        self.assertEqual(check(ctx).status, "UNABLE_TO_ASSESS")

    def test_unknown_when_beneficiary_id_missing(self):
        ctx = make_ctx("PAT001", "MEM001", None, "MEM001")
        self.assertEqual(check(ctx).status, "UNABLE_TO_ASSESS")

    def test_unknown_when_member_id_missing(self):
        ctx = make_ctx("PAT001", None, "PAT001", "MEM001")
        self.assertEqual(check(ctx).status, "UNABLE_TO_ASSESS")


if __name__ == "__main__":
    unittest.main()