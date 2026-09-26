"""Tests for the rule-engine interface (claimguard.engine).

"""
import dataclasses
import sys
import unittest

from claimguard._pack import pointer

from claimguard.engine.context import RuleContext
from claimguard.engine.findings import Findings
from claimguard.engine.registry import REGISTRY, rule


def make_ctx(n_lines=2):
    claim = {
        "claim_id": "CG-TEST",
        "member_id": None,
        "lines": [{"line_id": f"L{i + 1}", "service_date": "2026-03-01"} for i in range(n_lines)],
    }
    return RuleContext(
        claim=claim,
        rule={"rule_id": "R999", "severity": "high", "version": "1.0.0",
              "source": "fictional-rulebook/R999@1.0.0", "corrective_action": "Fix it."},
        policy=None, services={}, prior={},
    )


class ContextTests(unittest.TestCase):
    def test_path_builds_json_pointers(self):
        self.assertEqual(RuleContext.path("member_id"), "/member_id")
        self.assertEqual(RuleContext.path("lines", 0, "service_date"), "/lines/0/service_date")

    def test_path_escapes_pointer_characters(self):
        self.assertEqual(RuleContext.path("a/b", "c~d"), "/a~1b/c~0d")

    def test_path_round_trips_through_the_packs_pointer(self):
        obj = {"a/b": {"c~d": [10, 20]}}
        self.assertEqual(pointer(obj, RuleContext.path("a/b", "c~d", 1)), 20)

    def test_lines_yields_index_and_line_in_order(self):
        self.assertEqual([(i, l["line_id"]) for i, l in make_ctx(3).lines()],
                         [(0, "L1"), (1, "L2"), (2, "L3")])

    def test_context_is_frozen(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            make_ctx().policy = {}

    def test_rule_id_shortcut(self):
        self.assertEqual(make_ctx().rule_id, "R999")


class RegistryTests(unittest.TestCase):
    def test_duplicate_registration_raises(self):
        rule("R998")(lambda ctx: None)
        try:
            with self.assertRaises(RuntimeError):
                rule("R998")(lambda ctx: None)
        finally:
            REGISTRY.pop("R998", None)

    def test_malformed_rule_id_is_rejected(self):
        for bad in ("R2", "r002", "R0002", "002", ""):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                rule(bad)

    def test_discovery_skips_underscore_modules(self):
        import claimguard.rules  # noqa: F401
        self.assertIn("claimguard.rules", sys.modules)
        self.assertNotIn("claimguard.rules._template", sys.modules)


class FindingsAccumulatorTests(unittest.TestCase):
    def test_reasons_are_distinct_and_sorted(self):
        f = Findings(make_ctx())
        f.fail("b").fail("a").fail("b")
        f.unknown("z").unknown("y").unknown("z")
        self.assertEqual(f.failures, ("a", "b"))
        self.assertEqual(f.unknowns, ("y", "z"))

    def test_unknown_does_not_accept_a_line_id(self):
        with self.assertRaises(TypeError):
            Findings(make_ctx()).unknown("x", line_id="L1")


class VerdictContractTests(unittest.TestCase):
    """The spec for Block C1. Each test mirrors the rulebook's conventions or
    a check in src/evaluate.py:index()."""

    def test_failure_beats_unknown(self):
        f = Findings(make_ctx()).cite("/member_id")
        f.unknown("coverage period").fail("service outside coverage period", "/lines/0/service_date", line_id="L1")
        self.assertEqual(f.verdict("ok").status, "FAIL")

    def test_unknown_beats_pass(self):
        f = Findings(make_ctx()).cite("/member_id").unknown("coverage period")
        self.assertEqual(f.verdict("ok").status, "UNABLE_TO_ASSESS")

    def test_unknown_beats_not_applicable(self):
        f = Findings(make_ctx(), applicable=False).cite("/member_id")
        f.unknown("unknown service code")
        self.assertEqual(f.verdict("ok", not_applicable_message="n/a").status, "UNABLE_TO_ASSESS")

    def test_not_applicable_when_never_marked(self):
        v = Findings(make_ctx(), applicable=False).cite("/lines").verdict("ok", not_applicable_message="No line requires it.")
        self.assertEqual((v.status, v.message), ("NOT_APPLICABLE", "No line requires it."))

    def test_clean_is_pass_with_pass_message(self):
        v = Findings(make_ctx()).cite("/member_id").verdict("All good.")
        self.assertEqual((v.status, v.message), ("PASS", "All good."))

    def test_failure_message_keeps_uncertainty(self):
        f = Findings(make_ctx()).cite("/member_id")
        f.fail("b reason").fail("a reason").unknown("service date").unknown("coverage period")
        self.assertEqual(f.verdict("ok").message,
                         "a reason; b reason; Additional unknown inputs: coverage period, service date")

    def test_unknown_message_joins_reasons(self):
        f = Findings(make_ctx()).cite("/member_id").unknown("b").unknown("a")
        self.assertEqual(f.verdict("ok").message, "a; b")

    def test_message_override_applies_to_fail(self):
        f = Findings(make_ctx()).fail("x", "/member_id")
        self.assertEqual(f.verdict("ok", message="Required information is missing.").message,
                         "Required information is missing.")

    def test_evidence_deduplicated_in_first_cited_order(self):
        f = Findings(make_ctx()).cite("/member_id", "/claim_id").fail("x", "/claim_id", "/lines")
        self.assertEqual(f.verdict("ok").paths, ("/member_id", "/claim_id", "/lines"))

    def test_fallback_evidence_used_only_when_nothing_cited(self):
        self.assertEqual(Findings(make_ctx()).verdict("ok", fallback_evidence=["/lines"]).paths, ("/lines",))
        cited = Findings(make_ctx()).cite("/member_id").verdict("ok", fallback_evidence=["/lines"])
        self.assertEqual(cited.paths, ("/member_id",))

    def test_line_ids_in_claim_order_and_distinct(self):
        f = Findings(make_ctx(3)).cite("/lines")
        f.fail("x", line_id="L3").fail("x", line_id="L1").fail("y", line_id="L3")
        self.assertEqual(f.verdict("ok").line_ids, ("L1", "L3"))

    def test_rejects_result_with_no_evidence(self):
        with self.assertRaises(AssertionError):
            Findings(make_ctx()).verdict("ok")

    def test_rejects_blank_message(self):
        with self.assertRaises(AssertionError):
            Findings(make_ctx()).cite("/member_id").verdict("   ")

    def test_rejects_foreign_line_id(self):
        with self.assertRaises(AssertionError):
            Findings(make_ctx()).fail("x", "/member_id", line_id="L99").verdict("ok")

    def test_rejects_evidence_path_missing_from_claim(self):
        with self.assertRaisesRegex(AssertionError, "/no_such_field"):
            Findings(make_ctx()).cite("/no_such_field").verdict("ok")

    def test_null_field_is_valid_evidence(self):
        v = Findings(make_ctx()).fail("member ID is missing", "/member_id").verdict("ok")
        self.assertEqual((v.status, v.paths), ("FAIL", ("/member_id",)))

    def test_line_ids_only_come_from_failures(self):
        f = Findings(make_ctx()).cite("/lines").unknown("service date")
        self.assertEqual(f.verdict("ok").line_ids, ())

    def test_not_applicable_requires_a_message(self):
        with self.assertRaises(AssertionError):
            Findings(make_ctx(), applicable=False).cite("/lines").verdict("ok")


if __name__ == "__main__":
    unittest.main()
