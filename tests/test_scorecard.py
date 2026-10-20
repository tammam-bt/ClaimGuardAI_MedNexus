"""Tests for the filled explanation scorecard (C4, docs/AI_SCORECARD.md).

The card must keep the pack's columns and cases, hold only 0/1 scores, agree
with a fresh mock run on the two mechanical criteria, and match the totals
the write-up states.
"""
import csv
import json
import unittest
from pathlib import Path

from claimguard.ai.exercises import run
from claimguard.ai.provider import MockProvider

ROOT = Path(__file__).resolve().parents[1]
CARD = ROOT / "docs" / "llm_manual_scorecard_mock.csv"
DOC = ROOT / "docs" / "AI_SCORECARD.md"
SCORES = ["correct_finding_0_1", "correct_evidence_0_1", "correct_rule_0_1", "appropriate_action_0_1",
          "honest_uncertainty_0_1"]


def rows():
    with open(CARD, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


class ScorecardTests(unittest.TestCase):
    def test_columns_and_cases_are_the_packs(self):
        with open(ROOT / "exercises" / "llm_manual_scorecard.csv", encoding="utf-8", newline="") as f:
            original = list(csv.reader(f))
        with open(CARD, encoding="utf-8", newline="") as f:
            self.assertEqual(next(csv.reader(f)), original[0])
        cases = [json.loads(x)["case_id"] for x in
                 (ROOT / "exercises" / "llm_explanation_cases.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        self.assertEqual([r["case_id"] for r in rows()], cases)
        self.assertEqual([r[0] for r in original[1:]], cases)

    def test_every_score_is_0_or_1_and_every_0_is_explained(self):
        for r in rows():
            for column in SCORES:
                self.assertIn(r[column], ("0", "1"), (r["case_id"], column))
            self.assertTrue(r["unsupported_fact"].strip(), r["case_id"])
            self.assertTrue(r["latency_ms"].isdigit(), r["case_id"])
            if "0" in (r[c] for c in SCORES):
                self.assertTrue(r["reviewer_notes"].strip(), r["case_id"])

    def test_mechanical_scores_match_a_fresh_mock_run(self):
        card = {r["case_id"]: r for r in rows()}
        for case, record, event in run(MockProvider(), timeout=5.0):
            f = case["finding"]
            evidence = int(record["cited_evidence_paths"] == [e["path"] for e in f["evidence"]])
            rule = int(record["cited_rule_ids"] == [f["rule_id"]])
            self.assertEqual(int(card[case["case_id"]]["correct_evidence_0_1"]), evidence, case["case_id"])
            self.assertEqual(int(card[case["case_id"]]["correct_rule_0_1"]), rule, case["case_id"])
            self.assertIsNone(event, case["case_id"])  # the card says 0 fallbacks

    def test_the_write_up_states_the_cards_totals(self):
        doc = DOC.read_text(encoding="utf-8")
        labels = ["Correct finding", "Correct evidence", "Correct rule", "Appropriate action", "Honest uncertainty"]
        for label, column in zip(labels, SCORES):
            total = sum(int(r[column]) for r in rows())
            self.assertIn(f"| {label} | {total} / {len(rows())} |", doc)
        unsupported = sum(1 for r in rows() if r["unsupported_fact"].strip().lower() != "none")
        self.assertIn(f"| Unsupported facts | {unsupported} |", doc)


if __name__ == "__main__":
    unittest.main()
