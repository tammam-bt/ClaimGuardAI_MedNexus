"""Tests for the Phase 2 headline metrics (claimguard.evaluation.summary).

Every number here is derived from the official scorer's report, so the
summary can never disagree with src/evaluate.py about a single pair.
"""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from claimguard._pack import load_jsonl
from claimguard.evaluation.summary import (CATEGORIES_PATH, latency, load_categories, macro, markdown,
                                           summarize)

ROOT = Path(__file__).resolve().parents[1]
RULES = [f"R{i:03}" for i in range(1, 16)]
TEN_CLAIMS = ROOT / "examples/first_10_claims.jsonl"
TEN_GOLD = ROOT / "examples/first_10_expected_results.jsonl"


def as_fail(row):
    """A schema-valid FAIL version of a result row."""
    return {**row, "status": "FAIL", "requires_human_review": True,
            "corrective_action": row["corrective_action"] or "Verify the source record."}


class CategoryTests(unittest.TestCase):
    def test_shipped_grouping_covers_every_rule_once(self):
        cats = load_categories()
        self.assertEqual(sorted(r for rules in cats.values() for r in rules), RULES)

    def test_a_grouping_that_misses_or_repeats_a_rule_is_refused(self):
        good = json.loads(CATEGORIES_PATH.read_text(encoding="utf-8"))
        first = next(iter(good["categories"]))
        missing = copy.deepcopy(good)
        missing["categories"][first] = missing["categories"][first][1:]
        repeated = copy.deepcopy(good)
        repeated["categories"][first] = repeated["categories"][first] + ["R001"] * 2
        with tempfile.TemporaryDirectory() as d:
            for name, data in (("missing", missing), ("repeated", repeated)):
                path = Path(d, f"{name}.json")
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.subTest(name), self.assertRaises(ValueError):
                    load_categories(path)


class MacroTests(unittest.TestCase):
    def test_undefined_values_are_listed_not_counted_as_zero(self):
        self.assertEqual(macro({"R001": 1.0, "R002": 0.5, "R003": None}),
                         {"macro_f1": 0.75, "defined": 2, "undefined": ["R003"]})

    def test_all_undefined_is_null_not_one(self):
        self.assertEqual(macro({"R001": None}), {"macro_f1": None, "defined": 0, "undefined": ["R001"]})


class SummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.claims = {c["claim_id"]: c for c in load_jsonl(TEN_CLAIMS)}
        cls.gold = load_jsonl(TEN_GOLD)

    def test_gold_against_itself(self):
        s = summarize(self.gold, self.gold, self.claims)
        failing = sorted({r["rule_id"] for r in self.gold if r["status"] == "FAIL"})
        self.assertEqual(s["macro_f1_by_rule"]["macro_f1"], 1.0)
        self.assertEqual(s["macro_f1_by_rule"]["defined"], len(failing))
        self.assertEqual(s["macro_f1_by_rule"]["undefined"], [r for r in RULES if r not in failing])
        self.assertEqual(s["claims"]["exact_match"], {"count": 10, "of": 10, "rate": 1.0})
        self.assertEqual(s["claims"]["false_alarm"]["count"], 0)
        self.assertEqual(s["claims"]["clean_flagged"]["count"], 0)

    def test_official_overall_is_kept_unchanged(self):
        from claimguard._pack import score
        self.assertEqual(summarize(self.gold, self.gold, self.claims)["official_overall"],
                         score(self.gold, self.gold, self.claims)["overall"])

    def test_one_false_fail_on_a_claim_without_issues(self):
        no_fail = [c for c in self.claims if not any(r["claim_id"] == c and r["status"] == "FAIL" for r in self.gold)]
        pred = copy.deepcopy(self.gold)
        i = next(i for i, r in enumerate(pred) if r["claim_id"] == no_fail[0] and r["status"] == "PASS")
        pred[i] = as_fail(pred[i])
        s = summarize(self.gold, pred, self.claims)
        self.assertEqual(s["claims"]["false_alarm"], {"count": 1, "of": len(no_fail), "rate": 1 / len(no_fail),
                                                      "claim_ids": [no_fail[0]]})
        self.assertEqual(s["claims"]["exact_match"]["count"], 9)
        self.assertLess(s["per_rule_f1"][pred[i]["rule_id"]], 1.0)

    def test_a_missed_issue_lowers_its_category(self):
        pred = copy.deepcopy(self.gold)
        i = next(i for i, r in enumerate(pred) if r["status"] == "FAIL")
        rule = pred[i]["rule_id"]
        pred[i]["status"] = "PASS"
        s = summarize(self.gold, pred, self.claims)
        cat = next(name for name, rules in load_categories().items() if rule in rules)
        self.assertEqual(s["per_category"][cat]["fn"], 1)
        self.assertLess(s["per_category"][cat]["issue_f1"], 1.0)
        self.assertLess(s["macro_f1_by_category"]["macro_f1"], 1.0)

    def test_rejects_what_the_official_scorer_rejects(self):
        with self.assertRaises(ValueError):
            summarize(self.gold, self.gold[:-1], self.claims)

    def test_markdown_states_the_definitions(self):
        text = markdown(summarize(self.gold, self.gold, self.claims))
        for phrase in ("Macro F1 over rules", "Macro F1 over categories", "False-alarm claims", "undefined"):
            self.assertIn(phrase, text)


class LatencyTests(unittest.TestCase):
    def test_latency_comes_only_from_the_manifest_of_this_results_file(self):
        with tempfile.TemporaryDirectory() as d:
            results = Path(d, "r.jsonl")
            results.write_bytes(TEN_GOLD.read_bytes())
            digest = hashlib.sha256(results.read_bytes()).hexdigest()
            manifest = {"claims": [{}] * 10, "duration_ms": 250, "outputs": {"results_sha256": digest}}
            self.assertEqual(latency(manifest, results)["run"], {"claims": 10, "duration_ms": 250, "ms_per_claim": 25.0})
            stale = dict(manifest, outputs={"results_sha256": "0" * 64})
            with self.assertRaises(ValueError):
                latency(stale, results)

    def test_explanation_latency_ignores_rows_without_a_model_call(self):
        with tempfile.TemporaryDirectory() as d:
            results = Path(d, "r.jsonl")
            results.write_bytes(TEN_GOLD.read_bytes())
            manifest = {"claims": [{}], "duration_ms": 10,
                        "outputs": {"results_sha256": hashlib.sha256(results.read_bytes()).hexdigest()}}
            rows = [{"latency_ms": v} for v in (1, 2, 3, 4, None)]
            self.assertEqual(latency(manifest, results, rows)["explanations"],
                             {"count": 4, "median_ms": 2.5, "max_ms": 4})


class CliTests(unittest.TestCase):
    def test_cli_writes_reports_and_rejects_bad_runs(self):
        with tempfile.TemporaryDirectory() as d:
            base = [sys.executable, "-m", "claimguard.evaluation.summary",
                    "--gold", str(TEN_GOLD), "--claims", str(TEN_CLAIMS), "--split", "first_10"]
            ok = subprocess.run(base + ["--pred", str(TEN_GOLD), "--output", f"{d}/s.json", "--markdown", f"{d}/s.md"],
                                cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertEqual(json.loads(Path(d, "s.json").read_text(encoding="utf-8"))["split"], "first_10")
            self.assertIn("Macro F1 over rules", Path(d, "s.md").read_text(encoding="utf-8"))

            short = Path(d, "short.jsonl")
            short.write_text("".join(TEN_GOLD.read_text(encoding="utf-8").splitlines(True)[:-1]), encoding="utf-8")
            bad = subprocess.run(base + ["--pred", str(short), "--output", f"{d}/bad.json"],
                                 cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(bad.returncode, 2)
            self.assertIn("Evaluation rejected", bad.stderr)
            self.assertFalse(Path(d, "bad.json").exists())


if __name__ == "__main__":
    unittest.main()
