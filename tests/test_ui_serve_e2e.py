"""End-to-end test of the review loop against the local server (Track C, B5).

A real run, a real server on 127.0.0.1, and headless Chrome driven by
tests/serve_e2e.mjs: a reviewer decides, saves and sees "In the audit log"
without a terminal; a refused save keeps its draft; a correction is rechecked
as a new version. Skipped when Node or Chrome is missing; with REQUIRE_E2E=1,
as in CI, test_ui_e2e.RequiredTests then fails the run, so it never quietly
does not run.
"""
import contextlib
import io
import json
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from claimguard._pack import load_jsonl
from claimguard.audit import chain
from claimguard.review.gate import judge
from claimguard.run import main as run_main
from claimguard.ui.serve import App, Run, make_server

try:
    from test_ui_e2e import CHROME, NODE  # python -m unittest discover -s tests
except ImportError:
    from tests.test_ui_e2e import CHROME, NODE

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / "data" / "development"
DIRECTORY = {"Reviewer 01": "reviewer", "Admin 01": "admin"}


@unittest.skipUnless(NODE and CHROME, "needs Node and Chrome")
class ServedEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        tmp = Path(cls._tmp.name)
        cls.results, cls.log = tmp / "pred.jsonl", tmp / "audit.jsonl"
        with contextlib.redirect_stdout(io.StringIO()):
            run_main(["--input", str(DEV / "claims.jsonl"), "--output", str(cls.results), "--explain", "--audit-log", str(cls.log)])
        cls.before = len(load_jsonl(cls.log))
        cls.corrections = tmp / "corrections"
        app = App(Run(str(cls.results), str(DEV / "claims.jsonl"), str(cls.log), chain.default_anchor(cls.log), DIRECTORY,
                      str(cls.corrections)), quiet=True)
        server = make_server(app, 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            done = subprocess.run([NODE, str(ROOT / "tests" / "serve_e2e.mjs"), CHROME, app.url],
                                  capture_output=True, text=True, encoding="utf-8", timeout=300)
        finally:
            server.shutdown()
            server.server_close()
        try:
            cls.out = json.loads(done.stdout)
        except ValueError:
            raise RuntimeError(f"serve_e2e.mjs printed no result (exit {done.returncode}): {done.stderr.strip()[-2000:]}") from None
        cls.port = app.port

    def test_the_run_completed_without_an_error(self):
        self.assertNotIn("failure", self.out, self.out.get("failure"))
        self.assertEqual(self.out["errors"], [])

    def test_the_page_talks_to_this_server_only(self):
        self.assertTrue(self.out["live"])
        self.assertEqual(self.out["offOrigin"], [])
        self.assertIn("connect-src 'self'", self.out["policy"])
        # The token left the address bar for a cookie.
        self.assertTrue(self.out["addressAfterRedirect"].startswith(f"http://127.0.0.1:{self.port}/#/"))
        self.assertNotIn("token", self.out["addressAfterRedirect"])

    def test_a_reviewer_saves_and_sees_in_the_audit_log(self):
        self.assertEqual(self.out["draftsBefore"], 2)
        self.assertEqual(self.out["saveLabel"], "Save to the audit log (2)")
        saved = self.out["saved"]
        self.assertEqual(saved["notice"], "Saved to the audit log: 2 decisions")
        # The gate's verdict in the page's words, never its codes.
        self.assertRegex(saved["text"], r"Gate: \d+ of 400 claims ready; blocked: .*correction needed")
        self.assertNotIn("_", saved["text"])
        self.assertEqual(saved["drafts"], 0)
        self.assertTrue(saved["inLog"])
        events = [r["event"] for r in load_jsonl(self.log)][self.before:]
        decisions = [e for e in events if e["event"] == "review_decision"]
        self.assertEqual([(e["rule_id"], e["action"], e["actor"]) for e in decisions],
                         [("R003", "confirm_issue", "Reviewer 01"), ("R004", "confirm_issue", "Reviewer 01")])
        self.assertIn({"event": "append_performed", "command": "claimguard.ui.serve", "events": 2},
                      [{k: e.get(k) for k in ("event", "command", "events")} for e in events])
        chain.verify(self.log, chain.default_anchor(self.log))

    def test_a_refused_save_keeps_the_draft(self):
        refused = self.out["refused"]
        self.assertEqual(refused["title"], "No decision was saved.")
        self.assertEqual(len(refused["problems"]), 1)
        self.assertIn("R001", refused["problems"][0])
        self.assertEqual((refused["drafts"], refused["stored"]), (1, 1))

    def test_a_correction_is_rechecked_as_a_new_version(self):
        self.assertEqual(self.out["correctionButton"], "Recheck as a new version")
        corrected = self.out["corrected"]
        self.assertEqual(corrected["notice"], "CG-B39790AC3604 v2 recorded and rechecked")
        self.assertIn("R008 Fail → Pass, R009 Unable to assess → Fail", corrected["text"])
        self.assertNotIn("_", corrected["text"])
        self.assertEqual(corrected["deciding"], "Deciding on version 2")
        self.assertTrue((self.corrections / "CG-B39790AC3604.v2.json").exists())
        rows = judge(self.results, DEV / "claims.jsonl", self.log, DIRECTORY, corrections=self.corrections)
        self.assertEqual(next(r for r in rows if r["claim_id"] == "CG-B39790AC3604")["version"], 2)
