"""End-to-end test of the review interface in a real headless Chrome.

Builds the page from a real run, then tests/ui_e2e.mjs drives it: every page
draws without a JavaScript error, the decision flow works and records the
audit format, and hostile claim text never runs. Skipped when Node or
Chrome is not installed.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from claimguard.run import main as run_main
from claimguard.ui import build, render

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / "data" / "development"
NODE = shutil.which("node")
CHROME = next((p for p in (
    os.environ.get("CHROME"),
    shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("chromium-browser"), shutil.which("chrome"),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
) if p and Path(p).exists()), None)
HOSTILE = '<img src=x onerror="window.__pwned=1"></script><script>window.__pwned=1</script>'


@unittest.skipUnless(NODE and CHROME, "needs Node and Chrome")
class EndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        results, audit = tmp / "pred.jsonl", tmp / "audit.jsonl"
        with contextlib.redirect_stdout(io.StringIO()):
            run_main(["--input", str(DEV / "claims.jsonl"), "--output", str(results), "--explain", "--audit-log", str(audit)])
        data = build(results, DEV / "claims.jsonl", audit_log=audit, gold_path=DEV / "expected_results.jsonl")
        page = tmp / "page.html"
        page.write_text(render(data), encoding="utf-8")

        hostile = json.loads(json.dumps(data))
        hostile["claims"] = hostile["claims"][:3]
        hostile["claims"][0]["claim"]["notes"] = HOSTILE
        for r in hostile["claims"][0]["results"]:
            r["explanation"] = HOSTILE
        hostile["evaluation"]["mismatches"] = [{"claim_id": hostile["claims"][0]["claim"]["claim_id"], "rule_id": "R003",
                                                "expected": "FAIL", "predicted": "PASS"}]
        hostile_page = tmp / "hostile.html"
        hostile_page.write_text(render(hostile), encoding="utf-8")

        done = subprocess.run([NODE, str(ROOT / "tests" / "ui_e2e.mjs"), CHROME, str(page), str(hostile_page)],
                              capture_output=True, text=True, encoding="utf-8", timeout=240)
        cls.out = json.loads(done.stdout or "{}")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_run_completed(self):
        self.assertNotIn("failure", self.out, self.out.get("failure"))

    def test_no_javascript_error_on_any_page(self):
        self.assertEqual(self.out.get("errors"), [])
        for key, page in self.out["pages"].items():
            self.assertFalse(page["crashed"], key)
            self.assertTrue(page["title"], key)
        self.assertEqual(self.out["pages"]["claims"]["current"], "Claims")
        self.assertEqual(self.out["sidebarSame"], 7)

    def test_accessibility_on_every_page(self):
        for key, page in self.out["pages"].items():
            self.assertEqual(page["a11y"], [], key)
        self.assertEqual(self.out["keyboard"]["firstStop"], "Skip to content")
        self.assertEqual(self.out["keyboard"]["afterSkip"], "content")

    def test_no_page_scrolls_sideways_at_1280px(self):
        for key, overflow in self.out["narrow"].items():
            self.assertLessEqual(overflow, 0, key)

    def test_offline(self):
        self.assertEqual(self.out["network"], [])

    def test_decision_flow(self):
        o = self.out
        self.assertTrue(o["saveDisabledWithoutName"])
        self.assertIn("To review", o["headBefore"])
        self.assertIn("In review", o["afterOne"]["head"])
        self.assertIn("1 / 2 decided", o["afterOne"]["lifecycle"])
        self.assertIn("Ready for submission", o["afterTwo"]["head"])
        self.assertEqual(int(o["afterTwo"]["count"]), int(o["queueCountBefore"]) - 1)
        self.assertEqual(o["reviewerShown"], "Reviewer 01")
        self.assertIn("Waiting for information", o["afterReplace"]["head"])
        self.assertEqual(o["afterReplace"]["drafts"], 2)
        self.assertIn("Waiting for information", o["afterReload"])
        self.assertEqual(o["reloadedFresh"], "navigate")  # a real page load, not a hash change
        self.assertNotIn("null", o["headBefore"])

    def test_dashboard(self):
        d = self.out["dashboard"]
        for part in ("400 records", "400 accepted · 0 rejected", "6,000 results · 0 rule errors", "4 flagged for injection",
                     "201 escalate · 63 review · 136 clear", "136 ready · 264 open"):
            self.assertIn(part, d["lifecycle"])
        self.assertIn("Routed for review264", d["stats"])
        self.assertIn("Ready for submission136", d["stats"])
        self.assertIn("No record was rejected", d["rejected"])

    def test_rules(self):
        r = self.out["rules"]
        self.assertEqual(len(r["rows"]), 15)
        self.assertTrue(r["rows"][2].startswith("R003 Coverage active on service date"))
        self.assertTrue(r["rows"][14].startswith("R015 Currency matches policy"))
        page = r["r013"]["page"]
        for part in ("Quantity and price limits", "max_unit_price", "max_quantity_per_line", "EDU-BASIC 1.0.0", "Deterministic"):
            self.assertIn(part, page)
        self.assertNotIn("Failing or unassessed rule", r["r013"]["filters"])
        self.assertEqual(r["r013"]["diagonal"], ["344", "30", "26"])
        self.assertEqual(r["r013"]["offDiagonal"], 0)

    def test_audit_page_follows_the_role(self):
        a = self.out["audit"]
        self.assertIn("Valid", a["reviewer"]["page"])
        self.assertIn("6 run events hidden for your role", a["reviewer"]["page"])
        self.assertEqual(a["reviewer"]["count"], "0 of 0 events")
        self.assertEqual(a["admin"]["count"], "6 of 6 events")
        self.assertEqual(a["admin"]["types"][0], "Run finished")
        self.assertEqual(a["admin"]["types"][-1], "Run started")

    def test_settings(self):
        s = self.out["settings"]
        self.assertEqual(s["name"], "Reviewer 01")
        self.assertIn("Routing policy1.0.0", s["stats"])
        self.assertIn("Explanationsmock", s["stats"])
        self.assertIn("mock (no model is wired yet)", s["page"])
        self.assertNotIn("sk-ant", s["page"])
        rows = {r[0].split("  ")[0]: r[1:] for r in s["rbacRows"]}
        self.assertEqual(rows["Dismiss with reason"], ["Allowed", "Allowed"])
        self.assertEqual(rows["See run events (runs, rejections, flags, model failures)"], ["Not allowed", "Allowed"])
        self.assertTrue(s["confirmShown"])
        self.assertEqual(s["keptDrafts"], 2)

    def test_evaluation(self):
        e = self.out["evaluation"]
        self.assertIn("Status accuracy100.0%", e["stats"])
        self.assertIn("Claims fully correct400 / 400", e["stats"])
        self.assertIn("No disagreement", e["page"])
        self.assertIn("Template text (mock, no model): 495", e["page"])
        self.assertNotIn("AI explanation: 495", e["page"])
        self.assertEqual(self.out["hostile"]["mismatchRows"], 1)

    def test_review_queue(self):
        o = self.out
        self.assertEqual(o["queueBefore"]["count"], "264 of 264 claims")
        self.assertTrue(all("Escalate" in r for r in o["queueBefore"]["firstRoutes"]))
        self.assertTrue(o["queueRowOpens"].startswith("#/claims/CG-"))
        # Both findings dismissed: the claim is ready and leaves the open queue.
        self.assertEqual(o["queueAfter"]["count"], "263 of 264 claims")
        self.assertEqual(o["queueAfter"]["drafts"], "2")
        self.assertEqual(o["queueAll"], "264 of 264 claims")

    def test_drafts_have_the_audit_format(self):
        required = {"event", "claim_id", "rule_id", "action", "actor", "reason", "created_at", "original_status", "input_hash"}
        for d in self.out["drafts"]:
            self.assertEqual(set(d), required)
            self.assertEqual((d["event"], d["claim_id"], d["actor"]), ("review_decision", "CG-785C09BD9CC8", "Reviewer 01"))
            self.assertEqual(d["original_status"], "FAIL")

    def test_flagged_claim(self):
        self.assertIn("Flagged by the injection pre-filter", self.out["flagged"]["callout"])
        self.assertIn("Withheld from the model", self.out["flagged"]["explanation"])

    def test_filters_reach_the_url(self):
        self.assertIn("route=REVIEW", self.out["filtered"]["hash"])
        self.assertTrue(self.out["filtered"]["count"].startswith("63 of"))

    def test_hostile_text_never_runs(self):
        h = self.out["hostile"]
        self.assertFalse(h["pwned"])
        self.assertEqual(h["injectedImages"], 0)
        self.assertTrue(h["shownAsText"])


if __name__ == "__main__":
    unittest.main()
