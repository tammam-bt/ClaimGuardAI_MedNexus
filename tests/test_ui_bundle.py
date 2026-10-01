"""Tests for the interface's data bundle and page rendering (claimguard.ui)."""
import contextlib
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from claimguard._pack import load_jsonl
from claimguard.guards.rbac import PERMISSIONS
from claimguard.review.correction import original
from claimguard.review.routing import route_run
from claimguard.run import main as run_main
from claimguard.ui import build, render

ROOT = Path(__file__).resolve().parents[1]
STRESS = ROOT / "data" / "stress"
HOSTILE = '</script><script>alert(1)</script><!-- /*@JS@*/ @DATA@ <!--@ICONS@-->   & end'


def page_data(html):
    """The embedded data, read back the way the browser does."""
    m = re.search(r'<script type="application/json" id="claimguard-data">(.*?)</script>', html, re.S)
    return json.loads(m.group(1))


class RunCase(unittest.TestCase):
    """One real run on the stress split, shared by the tests."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        cls.results = cls.tmp / "pred.jsonl"
        cls.audit = cls.tmp / "audit.jsonl"
        with contextlib.redirect_stdout(io.StringIO()):
            run_main(["--input", str(STRESS / "claims.jsonl"), "--output", str(cls.results),
                      "--explain", "--audit-log", str(cls.audit)])
        cls.data = build(cls.results, STRESS / "claims.jsonl", audit_log=cls.audit,
                         gold_path=STRESS / "expected_results.jsonl")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()


class BundleTests(RunCase):
    def test_claims_carry_their_results_route_and_hash(self):
        results = load_jsonl(self.results)
        routes = {r["claim_id"]: r for r in route_run(results)}
        claims = {c["claim_id"]: c for c in load_jsonl(STRESS / "claims.jsonl")}
        self.assertEqual(len(self.data["claims"]), 50)
        self.assertEqual([r for c in self.data["claims"] for r in c["results"]], results)
        for c in self.data["claims"]:
            cid = c["claim"]["claim_id"]
            self.assertEqual(c["claim"], claims[cid])
            self.assertEqual(len(c["results"]), 15)
            self.assertEqual(c["route"], routes[cid])
            self.assertEqual(c["input_hash"], original(claims[cid]).input_hash)
            self.assertEqual(c["provenance"]["claim_id"], cid)

    def test_explanations_and_flags_are_attached(self):
        flagged = {c["claim"]["claim_id"] for c in self.data["claims"] if c["flag"]}
        self.assertEqual(flagged, {f["claim_id"] for f in self.data["run"]["injection_flags"]})
        explained = [e for c in self.data["claims"] for e in c["explanations"]]
        self.assertEqual(len(explained), len(load_jsonl(f"{self.results}.explanations.jsonl")))

    def test_rules_policies_rbac_and_evaluation(self):
        self.assertEqual([r["rule_id"] for r in self.data["rules"]], [f"R{i:03}" for i in range(1, 16)])
        self.assertTrue(all(r["implemented"] for r in self.data["rules"]))
        self.assertEqual(self.data["rbac"], {k: sorted(v) for k, v in PERMISSIONS.items()})
        self.assertEqual(self.data["evaluation"]["overall"]["status_accuracy"], 1.0)
        self.assertIn("confusion_by_rule", self.data["evaluation"])

    def test_audit_chain_is_verified(self):
        audit = self.data["audit"]
        self.assertTrue(audit["valid"])
        self.assertTrue(audit["anchored"])
        self.assertEqual(audit["count"], len(audit["events"]))
        self.assertEqual(audit["events"][0]["event"]["event"], "run_started")

    def test_a_tampered_audit_log_shows_as_invalid(self):
        tampered = self.tmp / "tampered.jsonl"
        rows = self.audit.read_text(encoding="utf-8").splitlines()
        rows[0] = rows[0].replace('"run_started"', '"run_startedX"')
        tampered.write_text("\n".join(rows) + "\n", encoding="utf-8")
        audit = build(self.results, STRESS / "claims.jsonl", audit_log=tampered)["audit"]
        self.assertFalse(audit["valid"])
        self.assertIn("invalid", audit["error"])

    def test_missing_sources_are_null_not_invented(self):
        bare = self.tmp / "bare.jsonl"
        bare.write_bytes(self.results.read_bytes())  # no manifest, explanations, audit or gold beside it
        data = build(bare, STRESS / "claims.jsonl")
        self.assertIsNone(data["run"])
        self.assertIsNone(data["audit"])
        self.assertIsNone(data["evaluation"])
        self.assertTrue(all(c["explanations"] is None and c["provenance"] is None for c in data["claims"]))
        self.assertTrue(all(r["implemented"] is None for r in data["rules"]))

    def test_results_for_an_unknown_claim_are_refused(self):
        other = self.tmp / "other_claims.jsonl"
        other.write_text("", encoding="utf-8")
        with self.assertRaises(ValueError):
            build(self.results, other)


class RenderTests(RunCase):
    def test_round_trip(self):
        self.assertEqual(page_data(render(self.data)), self.data)

    def test_hostile_text_cannot_leave_the_data_element(self):
        data = json.loads(json.dumps(self.data))
        data["claims"][0]["claim"]["notes"] = HOSTILE
        data["claims"][0]["results"][0]["explanation"] = HOSTILE
        html = render(data)
        self.assertEqual(html.count("</script>"), 2)  # the data element and the app script
        self.assertNotIn("<script>alert", html)
        self.assertNotIn(" ", html.split('id="claimguard-data">', 1)[1].split("</script>", 1)[0])
        self.assertEqual(page_data(html), data)

    def test_each_static_file_is_inlined_once(self):
        html = render(self.data)
        for marker in ("/*@CSS@*/", "<!--@ICONS@-->", "@DATA@", "/*@JS@*/"):
            self.assertNotIn(marker, html)


class CliTests(RunCase):
    def test_command_writes_the_page(self):
        out = self.tmp / "page.html"
        done = subprocess.run([sys.executable, "-m", "claimguard.ui", "--results", str(self.results),
                               "--claims", str(STRESS / "claims.jsonl"), "--audit-log", str(self.audit),
                               "--gold", str(STRESS / "expected_results.jsonl"), "--output", str(out)],
                              cwd=ROOT, check=True, capture_output=True, text=True)
        summary = json.loads(done.stdout)
        self.assertEqual((summary["claims"], summary["audit_valid"], summary["evaluation"]), (50, True, True))
        self.assertEqual(len(page_data(out.read_text(encoding="utf-8"))["claims"]), 50)


if __name__ == "__main__":
    unittest.main()
