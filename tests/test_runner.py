"""Tests for the runner (claimguard.engine.runner)."""
import unittest
from pathlib import Path

from claimguard._pack import index, load_jsonl
from claimguard.engine.findings import Findings
from claimguard.engine.registry import REGISTRY
from claimguard.engine.runner import RULE_ERROR_MESSAGE, Engine

ROOT = Path(__file__).resolve().parents[1]
RULE_IDS = [f"R{i:03}" for i in range(1, 16)]


class swap_rule:
    """Temporarily replace (or, with fn=None, remove) one registered rule."""

    def __init__(self, rule_id, fn):
        self.rule_id, self.fn = rule_id, fn

    def __enter__(self):
        self.saved = REGISTRY.get(self.rule_id)
        if self.fn is None:
            REGISTRY.pop(self.rule_id, None)
        else:
            REGISTRY[self.rule_id] = self.fn

    def __exit__(self, *exc):
        if self.saved is None:
            REGISTRY.pop(self.rule_id, None)
        else:
            REGISTRY[self.rule_id] = self.saved


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.claims = load_jsonl(ROOT / "examples" / "first_10_claims.jsonl")

    def test_fifteen_results_in_rulebook_order(self):
        results = Engine(ROOT).evaluate_claim(self.claims[0])
        self.assertEqual([r["rule_id"] for r in results], RULE_IDS)
        self.assertEqual({r["claim_id"] for r in results}, {self.claims[0]["claim_id"]})

    def test_results_pass_the_official_validator(self):
        engine = Engine(ROOT, strict=True)
        rows = [r for c in self.claims for r in engine.evaluate_claim(c)]
        index(rows, {c["claim_id"]: c for c in self.claims})

    def test_unregistered_rule_reports_not_implemented(self):
        with swap_rule("R015", None):
            result = Engine(ROOT).evaluate_claim(self.claims[0])[14]
        self.assertEqual((result["rule_id"], result["status"]), ("R015", "NOT_IMPLEMENTED"))

    def test_rule_exception_becomes_unable_to_assess_and_is_recorded(self):
        def boom(ctx):
            raise ZeroDivisionError("division by zero")

        engine = Engine(ROOT)
        with swap_rule("R007", boom):
            result = engine.evaluate_claim(self.claims[0])[6]
        self.assertEqual((result["status"], result["explanation"]), ("UNABLE_TO_ASSESS", RULE_ERROR_MESSAGE))
        self.assertEqual(result["evidence"][0]["path"], "/claim_id")
        self.assertTrue(result["requires_human_review"])
        self.assertTrue(result["corrective_action"])
        self.assertEqual([(e.rule_id, "ZeroDivisionError" in e.error) for e in engine.errors], [("R007", True)])

    def test_strict_mode_reraises(self):
        def boom(ctx):
            raise ZeroDivisionError("division by zero")

        with swap_rule("R007", boom), self.assertRaises(ZeroDivisionError):
            Engine(ROOT, strict=True).evaluate_claim(self.claims[0])

    def test_prior_holds_earlier_results_read_only(self):
        seen = {}

        def probe(ctx):
            seen["keys"] = sorted(ctx.prior)
            with self.assertRaises(TypeError):
                ctx.prior["R001"] = {}
            ctx.prior["R001"]["status"] = "TAMPERED"  # a private copy: must not leak
            return Findings(ctx).cite("/claim_id").verdict("probe")

        with swap_rule("R015", probe):
            results = Engine(ROOT, strict=True).evaluate_claim(self.claims[0])
        self.assertEqual(seen["keys"], RULE_IDS[:14])
        self.assertNotEqual(results[0]["status"], "TAMPERED")

    def test_rule_registered_but_absent_from_rulebook_is_refused(self):
        with swap_rule("R016", lambda ctx: None), self.assertRaises(RuntimeError):
            Engine(ROOT)

    def test_correction_uses_the_one_runner(self):
        from claimguard.review.correction import rule_engine
        run = rule_engine()
        self.assertIsInstance(run.__self__, Engine)
        self.assertEqual(run(self.claims[0]), Engine(ROOT).evaluate_claim(self.claims[0]))


if __name__ == "__main__":
    unittest.main()
