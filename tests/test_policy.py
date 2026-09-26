"""Tests for policy resolution (claimguard.engine.policy)."""
import unittest
from pathlib import Path

from claimguard._pack import config, load_jsonl
from claimguard.engine.policy import PolicyBook

ROOT = Path(__file__).resolve().parents[1]


class PolicyBookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = config(ROOT)
        cls.book = PolicyBook(cls.cfg["policies"])

    def test_resolves_both_supplied_policies(self):
        self.assertEqual(self.book.resolve("EDU-BASIC")["submission_window_days"], 30)
        self.assertEqual(self.book.resolve("EDU-PLUS")["submission_window_days"], 60)

    def test_unrecognised_policy_is_none_not_a_fallback(self):
        self.assertIsNone(self.book.resolve("EDU-NO-POLICY"))

    def test_lookup_is_exact(self):
        for near_miss in ("edu-basic", " EDU-BASIC", "EDU-BASIC ", "EDU_BASIC"):
            with self.subTest(policy_id=near_miss):
                self.assertIsNone(self.book.resolve(near_miss))

    def test_policy_cannot_be_mutated(self):
        p = self.book.resolve("EDU-BASIC")
        with self.assertRaises(TypeError):
            p["currency"] = "USD"
        with self.assertRaises(TypeError):
            p["max_unit_price"]["SVC-LAB"] = 0
        with self.assertRaises(AttributeError):
            p["allowed_providers"].append("EDU-PROV-OUT")

    def test_frozen_policy_still_answers_rule_questions(self):
        p = self.book.resolve("EDU-PLUS")
        self.assertIn("EDU-PROV-01", p["allowed_providers"])
        self.assertIn("SVC-IMAGE", p["auth_required_services"])
        self.assertEqual(p["max_quantity_per_line"]["SVC-PHARM"], 10)
        self.assertEqual(p["required_documents"]["SVC-DENTAL"], "service-note")

    def test_not_aliased_to_the_loaded_config(self):
        raw = {"EDU-X": {"policy_id": "EDU-X", "currency": "SAR"}}
        book = PolicyBook(raw)
        raw["EDU-X"]["currency"] = "USD"
        self.assertEqual(book.resolve("EDU-X")["currency"], "SAR")

    def test_key_and_policy_id_must_agree(self):
        with self.assertRaises(ValueError):
            PolicyBook({"EDU-A": {"policy_id": "EDU-B"}})

    def test_every_public_claim_resolves_exactly_when_its_policy_exists(self):
        unresolved = 0
        for split in ("development", "validation", "stress"):
            for claim in load_jsonl(ROOT / "data" / split / "claims.jsonl"):
                policy = self.book.resolve(claim["policy_id"])
                self.assertEqual(policy is None, claim["policy_id"] not in self.cfg["policies"])
                unresolved += policy is None
        self.assertEqual(unresolved, 15)


if __name__ == "__main__":
    unittest.main()
