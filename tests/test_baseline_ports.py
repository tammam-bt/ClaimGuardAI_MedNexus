"""Block D: R001, R003 and R006, ported into claimguard, reproduce the pack's
engine_core.base_check result exactly — every field — on every public claim."""
import unittest
from pathlib import Path

import claimguard._pack  # noqa: F401  puts src/ on sys.path for the reference below
from claimguard._pack import load_jsonl
from claimguard.engine.registry import REGISTRY
from claimguard.engine.runner import Engine
from engine_core import base_check  # reference implementation, read-only

ROOT = Path(__file__).resolve().parents[1]
PORTED = ("R001", "R003", "R006")


class BaselinePortTests(unittest.TestCase):
    def test_ports_are_registered(self):
        for rule_id in PORTED:
            self.assertIn(rule_id, REGISTRY)

    def test_identical_to_baseline_on_every_public_claim(self):
        engine = Engine(ROOT, strict=True)
        rules = {r["rule_id"]: r for r in engine.cfg["rules"]}
        mismatches, checked = [], 0
        for split in ("development", "validation", "stress"):
            for claim in load_jsonl(ROOT / "data" / split / "claims.jsonl"):
                ours = {r["rule_id"]: r for r in engine.evaluate_claim(claim)}
                for rule_id in PORTED:
                    checked += 1
                    theirs = base_check(claim, rules[rule_id])
                    if ours[rule_id] != theirs:
                        diff = {k: (theirs[k], ours[rule_id][k]) for k in theirs if theirs[k] != ours[rule_id][k]}
                        mismatches.append((claim["claim_id"], rule_id, diff))
        self.assertEqual(checked, 1800)
        self.assertEqual(mismatches[:3], [], f"{len(mismatches)} of {checked} results differ from the baseline")


if __name__ == "__main__":
    unittest.main()
