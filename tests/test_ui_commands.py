"""Tests for appending decisions (claimguard.ui.decisions), correcting a claim
(claimguard.review.correct) and showing corrected versions (claimguard.ui)."""
import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from claimguard._pack import load_jsonl
from claimguard.audit import chain
from claimguard.engine.registry import REGISTRY
from claimguard.review.correct import correct_claim
from claimguard.review.correct import main as correct_main
from claimguard.review.correction import original
from claimguard.run import main as run_main
from claimguard.ui import build
from claimguard.ui.decisions import append_decisions, check

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / "data" / "development"
CLAIM = "CG-785C09BD9CC8"      # R003 and R004 FAIL
AUTH_CLAIM = "CG-B39790AC3604"  # R008 FAIL, R009 UNABLE_TO_ASSESS: no authorization
FIX = [{"op": "replace", "path": "/lines/0/authorization_id", "value": "AUTH-CG-B39790AC3604-1"},
       {"op": "add", "path": "/authorizations/0", "value": {
           "authorization_id": "AUTH-CG-B39790AC3604-1", "patient_id": "PAT-64397DF099", "service_code": "SVC-IMAGE",
           "status": "approved", "valid_from": "2026-03-01", "valid_to": "2026-04-30", "max_quantity": 5}}]


class RunCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.base = Path(cls._tmp.name)
        cls.results = cls.base / "pred.jsonl"
        cls.run_log = cls.base / "run_audit.jsonl"
        with contextlib.redirect_stdout(io.StringIO()):
            run_main(["--input", str(DEV / "claims.jsonl"), "--output", str(cls.results), "--audit-log", str(cls.run_log)])
        claims = {c["claim_id"]: c for c in load_jsonl(DEV / "claims.jsonl")}
        cls.hash = original(claims[CLAIM]).input_hash

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        # A fresh copy of the run's chain for each test.
        self.dir = Path(tempfile.mkdtemp(dir=self.base))
        self.log = self.dir / "audit.jsonl"
        shutil.copy(self.run_log, self.log)
        shutil.copy(chain.default_anchor(self.run_log), chain.default_anchor(self.log))

    def decision(self, **changes):
        e = {"event": "review_decision", "claim_id": CLAIM, "rule_id": "R003", "action": "dismiss_with_reason",
             "actor": "Reviewer 01", "reason": "Checked at the source.", "created_at": "2026-10-01T10:00:00Z",
             "original_status": "FAIL", "input_hash": self.hash}
        e.update(changes)
        return e

    def write(self, events):
        path = self.dir / "decisions.jsonl"
        path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
        return path

    def append(self, events, **kw):
        return append_decisions(self.write(events), self.log, claims_path=DEV / "claims.jsonl",
                                results_path=self.results, **kw)


class DecisionTests(RunCase):
    def test_good_decisions_are_appended_once(self):
        events = [self.decision(), self.decision(rule_id="R004")]
        first = self.append(events)
        self.assertEqual((first["appended"], first["events_in_chain"]), (2, 8))
        again = self.append(events)
        self.assertEqual((again["appended"], again["already_in_chain"], again["events_in_chain"]), (0, 2, 8))
        self.assertEqual(chain.verify(self.log, chain.default_anchor(self.log))[1], 8)
        recorded = [row["event"] for row in load_jsonl(self.log)][-2:]
        self.assertEqual(recorded, events)

    def test_one_bad_decision_writes_nothing(self):
        before = self.log.read_bytes()
        cases = {
            "stale status": self.decision(original_status="PASS"),
            "other version": self.decision(input_hash="0" * 64),
            "not a finding": self.decision(rule_id="R001"),
            "blank reason": self.decision(reason="  "),
            "unknown action": self.decision(action="approve_claim"),
            "extra field": dict(self.decision(), role="admin"),
            "missing field": {k: v for k, v in self.decision().items() if k != "input_hash"},
            "bad date": self.decision(created_at="yesterday"),
            "unknown claim": self.decision(claim_id="CG-NOT-IN-RUN"),
        }
        for name, bad in cases.items():
            with self.assertRaises(ValueError, msg=name):
                self.append([self.decision(rule_id="R004"), bad])
            self.assertEqual(self.log.read_bytes(), before, name)

    def test_the_directory_decides_who_may_act(self):
        with self.assertRaises(ValueError):
            self.append([self.decision()], directory={"Someone else": "reviewer"})
        self.assertEqual(self.append([self.decision()], directory={"Reviewer 01": "admin"})["appended"], 1)

    def test_check_reports_every_problem(self):
        problems = check([self.decision(reason=""), self.decision(original_status="PASS")], {"Reviewer 01": "reviewer"},
                         {c["claim_id"]: c for c in load_jsonl(DEV / "claims.jsonl")}, load_jsonl(self.results))
        self.assertEqual(len(problems), 2)


class CorrectionTests(RunCase):
    def test_correction_rechecks_and_records_a_version(self):
        out, record = correct_claim(DEV / "claims.jsonl", AUTH_CLAIM, FIX, actor="Reviewer 01",
                                    reason="Authorization added.", output=self.dir / "corrections", log=self.log)
        self.assertEqual(record["version"], 2)
        self.assertEqual(record["status_changes"], [{"rule_id": "R008", "before": "FAIL", "after": "PASS"},
                                                    {"rule_id": "R009", "before": "UNABLE_TO_ASSESS", "after": "PASS"}])
        self.assertEqual(len(record["results"]), 15)
        last = load_jsonl(self.log)[-1]["event"]
        self.assertEqual((last["event"], last["claim_id"], last["version"]), ("version_created", AUTH_CLAIM, 2))
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["input_hash"], last["input_hash"])

    def test_a_rule_error_is_recorded_and_fails_the_command(self):
        def boom(ctx):
            raise ZeroDivisionError("division by zero")

        changes = self.dir / "fix.json"
        changes.write_text(json.dumps(FIX), encoding="utf-8")
        saved = REGISTRY["R009"]
        REGISTRY["R009"] = boom
        try:
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                code = correct_main(["--claims", str(DEV / "claims.jsonl"), "--claim-id", AUTH_CLAIM,
                                     "--changes", str(changes), "--actor", "Reviewer 01", "--reason", "Authorization added.",
                                     "--output", str(self.dir / "corrections")])
        finally:
            REGISTRY["R009"] = saved
        self.assertEqual(code, 2)
        self.assertIn("R009", printed.getvalue())
        record = json.loads((self.dir / "corrections" / f"{AUTH_CLAIM}.v2.json").read_text(encoding="utf-8"))
        self.assertEqual({(e["rule_id"], e["error"]) for e in record["rule_errors"]}, {("R009", "ZeroDivisionError")})

    def test_a_refused_correction_writes_nothing(self):
        before = self.log.read_bytes()
        for changes in ([], [{"op": "replace", "path": "/claim_id", "value": "CG-X"}]):
            with self.assertRaises(ValueError):
                correct_claim(DEV / "claims.jsonl", AUTH_CLAIM, changes, actor="Reviewer 01", reason="r",
                              output=self.dir / "corrections", log=self.log)
        self.assertEqual(self.log.read_bytes(), before)
        self.assertFalse((self.dir / "corrections").exists())

    def test_the_interface_shows_the_version(self):
        corrections = self.dir / "corrections"
        correct_claim(DEV / "claims.jsonl", AUTH_CLAIM, FIX, actor="Reviewer 01", reason="Authorization added.",
                      output=corrections, log=self.log)
        (corrections / "stale.v2.json").write_text(json.dumps({"claim_id": CLAIM, "parent_hash": "0" * 64}), encoding="utf-8")
        data = build(self.results, DEV / "claims.jsonl", audit_log=self.log, corrections=corrections)
        entry = next(c for c in data["claims"] if c["claim"]["claim_id"] == AUTH_CLAIM)
        [v] = entry["versions"]
        self.assertEqual((v["version"], v["route"]["route"]), (2, "CLEAR"))
        self.assertEqual(v["parent_hash"], entry["input_hash"])
        self.assertEqual([s["file"] for s in data["corrections_skipped"]], ["stale.v2.json"])
        self.assertTrue(data["audit"]["valid"])


if __name__ == "__main__":
    unittest.main()
