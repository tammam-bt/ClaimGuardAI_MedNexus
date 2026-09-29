"""Tests for per-rule confusion matrices (claimguard.evaluation.confusion).

The point of every invariant here: the per-rule view must never disagree with
the official scorer in src/evaluate.py.
"""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from claimguard._pack import config, load_jsonl
from claimguard.evaluation.confusion import EXPECTED, PREDICTED, confusion_by_rule, markdown, score
from engine_core import baseline  # tests may read the pack; importing claimguard._pack put src/ on sys.path

ROOT = Path(__file__).resolve().parents[1]
RULES = [f"R{i:03}" for i in range(1, 16)]


def claims_of(path):
    return {c["claim_id"]: c for c in load_jsonl(path)}


def grid(cells):
    return {(c["expected"], c["predicted"]): c["count"] for c in cells}


class ConfusionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = config(ROOT)
        cls.dev_claims = claims_of(ROOT / "data/development/claims.jsonl")
        cls.dev_gold = load_jsonl(ROOT / "data/development/expected_results.jsonl")
        cls.dev_baseline = [r for c in cls.dev_claims.values() for r in baseline(c, cls.cfg)]
        cls.report = confusion_by_rule(cls.dev_gold, cls.dev_baseline, cls.dev_claims)
        cls.ten_claims = claims_of(ROOT / "examples/first_10_claims.jsonl")
        cls.ten_gold = load_jsonl(ROOT / "examples/first_10_expected_results.jsonl")

    def test_score_is_the_packs_own_scorer(self):
        """Guards the file-path import: an installed `evaluate` package must not shadow src/evaluate.py."""
        self.assertEqual(Path(score.__code__.co_filename).resolve(), (ROOT / "src/evaluate.py").resolve())

    def test_official_report_is_kept_unchanged(self):
        official = score(self.dev_gold, self.dev_baseline, self.dev_claims)
        self.assertEqual({k: v for k, v in self.report.items() if k in official}, official)
        self.assertEqual(set(self.report) - set(official), {"confusion_by_rule", "mismatches"})

    def test_gold_against_itself_is_diagonal(self):
        report = confusion_by_rule(self.dev_gold, self.dev_gold, self.dev_claims)
        for rule_id, cells in report["confusion_by_rule"].items():
            with self.subTest(rule=rule_id):
                off = [c for c in cells if c["expected"] != c["predicted"] and c["count"]]
                self.assertEqual(off, [])
        self.assertEqual(report["mismatches"], [])

    def test_every_rule_has_a_full_fixed_grid(self):
        self.assertEqual(list(self.report["confusion_by_rule"]), RULES)
        for rule_id, cells in self.report["confusion_by_rule"].items():
            with self.subTest(rule=rule_id):
                self.assertEqual([(c["expected"], c["predicted"]) for c in cells],
                                 [(e, p) for e in EXPECTED for p in PREDICTED])
                self.assertEqual(sum(c["count"] for c in cells), len(self.dev_claims))

    def test_rules_sum_to_the_official_overall_confusion(self):
        total = Counter()
        for cells in self.report["confusion_by_rule"].values():
            total.update(grid(cells))
        official = {(c["expected"], c["predicted"]): c["count"] for c in self.report["confusion"]}
        self.assertEqual({k: v for k, v in total.items() if v}, official)

    def test_each_grid_agrees_with_the_official_per_rule_metrics(self):
        n = len(self.dev_claims)
        for rule_id, cells in self.report["confusion_by_rule"].items():
            m, g = self.report["by_rule"][rule_id], grid(cells)
            with self.subTest(rule=rule_id):
                self.assertAlmostEqual(sum(g[(s, s)] for s in EXPECTED) / n, m["status_accuracy"])
                self.assertEqual(g[("FAIL", "FAIL")], m["tp"])
                self.assertEqual(sum(g[(e, "FAIL")] for e in EXPECTED if e != "FAIL"), m["fp"])
                self.assertEqual(sum(g[("FAIL", p)] for p in PREDICTED if p != "FAIL"), m["fn"])
                self.assertEqual(sum(g[(e, "NOT_IMPLEMENTED")] for e in EXPECTED), m["not_implemented"])

    def test_baseline_matches_the_shipped_metrics(self):
        shipped = json.loads((ROOT / "examples/baseline_development_metrics.json").read_text(encoding="utf-8"))
        self.assertEqual(self.report["confusion"], shipped["confusion"])

    def test_mismatches_are_exactly_the_off_diagonal_cells(self):
        off = sum(c["count"] for cells in self.report["confusion_by_rule"].values()
                  for c in cells if c["expected"] != c["predicted"])
        self.assertEqual(len(self.report["mismatches"]), off)
        keys = [(m["rule_id"], m["claim_id"]) for m in self.report["mismatches"]]
        order = {cid: i for i, cid in enumerate(self.dev_claims)}
        self.assertEqual(keys, sorted(keys, key=lambda k: (k[0], order[k[1]])))

    def test_one_flipped_status_moves_one_cell_in_the_right_rule(self):
        pred = copy.deepcopy(self.ten_gold)
        i = next(i for i, r in enumerate(pred) if r["rule_id"] == "R007" and r["status"] == "PASS")
        pred[i]["status"] = "NOT_APPLICABLE"  # still a schema-valid result: no review/action requirement
        report = confusion_by_rule(self.ten_gold, pred, self.ten_claims)
        self.assertEqual(report["mismatches"], [{"claim_id": pred[i]["claim_id"], "rule_id": "R007",
                                                 "expected": "PASS", "predicted": "NOT_APPLICABLE"}])
        self.assertEqual(grid(report["confusion_by_rule"]["R007"])[("PASS", "NOT_APPLICABLE")], 1)
        for rule_id in RULES:
            if rule_id != "R007":
                self.assertEqual(sum(g for (e, p), g in grid(report["confusion_by_rule"][rule_id]).items() if e != p), 0)

    def test_rejects_what_the_official_scorer_rejects(self):
        gold, claims = self.ten_gold, self.ten_claims
        fabricated = copy.deepcopy(gold)
        fabricated[0]["evidence"][0]["value"] = "INVENTED"
        for name, pred in (("missing pair", gold[:-1]), ("duplicate", gold + [gold[0]]), ("fabricated evidence", fabricated)):
            with self.subTest(name):
                with self.assertRaises(ValueError):
                    confusion_by_rule(gold, pred, claims)

    def test_markdown_has_one_table_per_rule(self):
        text = markdown(self.report)
        self.assertEqual([l for l in text.splitlines() if l.startswith("## ")], [f"## {r}" for r in RULES])
        r001 = text.split("## R001")[1].split("## R002")[0]
        g = grid(self.report["confusion_by_rule"]["R001"])
        self.assertIn("| FAIL | " + " | ".join(str(g[("FAIL", p)]) for p in PREDICTED) + " |", r001)

    def test_cli_writes_reports_and_rejects_bad_runs(self):
        with tempfile.TemporaryDirectory() as d:
            base = [sys.executable, "-m", "claimguard.evaluation.confusion",
                    "--gold", str(ROOT / "examples/first_10_expected_results.jsonl"),
                    "--claims", str(ROOT / "examples/first_10_claims.jsonl")]
            ok = subprocess.run(base + ["--pred", str(ROOT / "examples/first_10_expected_results.jsonl"),
                                        "--output", f"{d}/c.json", "--markdown", f"{d}/c.md"],
                                cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertEqual(json.loads(Path(d, "c.json").read_text(encoding="utf-8"))["mismatches"], [])
            self.assertTrue(Path(d, "c.md").read_text(encoding="utf-8").startswith("# Per-rule"))

            short = Path(d, "short.jsonl")
            short.write_text("".join(l for l in (ROOT / "examples/first_10_expected_results.jsonl")
                                     .read_text(encoding="utf-8").splitlines(True)[:-1]), encoding="utf-8")
            bad = subprocess.run(base + ["--pred", str(short), "--output", f"{d}/bad.json"],
                                 cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(bad.returncode, 2)
            self.assertIn("Evaluation rejected", bad.stderr)
            self.assertFalse(Path(d, "bad.json").exists())


if __name__ == "__main__":
    unittest.main()
