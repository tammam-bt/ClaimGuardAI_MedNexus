"""Tests for the autonomy gate (claimguard.review.gate, D2).

The gate is the one place explicit human approval is enforced: it reads only
the verified audit chain and the actor directory, and exits non-zero while
any claim is blocked.
"""
import contextlib
import io
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from claimguard._pack import load_jsonl
from claimguard.audit import chain
from claimguard.review.correct import correct_claim, latest_version
from claimguard.review.correction import original
from claimguard.review.gate import GateError, judge, main
from claimguard.run import main as run_main
from claimguard.ui.decisions import append_decisions

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / "data" / "development"
AUTH_CLAIM = "CG-B39790AC3604"  # R008 FAIL, R009 UNABLE_TO_ASSESS: no authorization
FIX = [{"op": "replace", "path": "/lines/0/authorization_id", "value": "AUTH-CG-B39790AC3604-1"},
       {"op": "add", "path": "/authorizations/0", "value": {
           "authorization_id": "AUTH-CG-B39790AC3604-1", "patient_id": "PAT-64397DF099", "service_code": "SVC-IMAGE",
           "status": "approved", "valid_from": "2026-03-01", "valid_to": "2026-04-30", "max_quantity": 5}}]
NOTE = [{"op": "replace", "path": "/notes", "value": "Called the provider."}]
DIRECTORY = {"Reviewer 01": "reviewer"}


def quietly(fn, *args, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kw)


class GateCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def run_claims(self, lines):
        self.claims = self.dir / "claims.jsonl"
        self.claims.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
        self.results, self.log = self.dir / "pred.jsonl", self.dir / "audit.jsonl"
        quietly(run_main, ["--input", str(self.claims), "--output", str(self.results), "--audit-log", str(self.log)])
        self.directory = self.dir / "actors.json"
        self.directory.write_text(json.dumps(DIRECTORY), encoding="utf-8")

    def gate(self, *extra):
        return quietly(main, ["--results", str(self.results), "--claims", str(self.claims), "--log", str(self.log),
                              "--directory", str(self.directory), *extra])

    def states(self, **kw):
        rows = judge(self.results, self.claims, self.log, DIRECTORY, **kw)
        return {r["claim_id"]: r["state"] for r in rows}


class DevelopmentTests(GateCase):
    def test_matches_the_dashboard_with_no_decisions(self):
        # The page's dashboard says "136 ready · 264 open" for this run.
        self.run_claims((DEV / "claims.jsonl").read_text(encoding="utf-8").splitlines())
        rows = judge(self.results, self.claims, self.log, DIRECTORY)
        self.assertEqual(Counter(r["ready"] for r in rows), {True: 136, False: 264})
        self.assertEqual({r["state"] for r in rows if not r["ready"]}, {"to_review"})
        self.assertEqual(self.gate(), 1)


class ScenarioTests(GateCase):
    def setUp(self):
        super().setUp()
        lines = {json.loads(l)["claim_id"]: l for l in (DEV / "claims.jsonl").read_text(encoding="utf-8").splitlines()}
        gold = load_jsonl(DEV / "expected_results.jsonl")
        flagged = {r["claim_id"] for r in gold if r["status"] not in ("PASS", "NOT_APPLICABLE")}
        self.clean = next(cid for cid in lines if cid not in flagged)
        self.run_claims([lines[AUTH_CLAIM], lines[self.clean]])
        self.hash = original(json.loads(lines[AUTH_CLAIM])).input_hash

    def decide(self, action, rules=("R008", "R009"), actor="Reviewer 01", input_hash=None, corrections=None):
        status = {r["rule_id"]: r["status"] for r in load_jsonl(self.results) if r["claim_id"] == AUTH_CLAIM}
        events = [{"event": "review_decision", "claim_id": AUTH_CLAIM, "rule_id": rule, "action": action,
                   "actor": actor, "reason": "Checked at the source.", "created_at": "2026-10-19T10:00:00Z",
                   "original_status": status[rule], "input_hash": input_hash or self.hash} for rule in rules]
        path = self.dir / f"decisions_{action}_{len(rules)}.jsonl"
        path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
        append_decisions(path, self.log, claims_path=self.claims, results_path=self.results,
                         directory={actor: "reviewer"}, corrections=corrections)

    def correct(self, changes):
        correct_claim(self.claims, AUTH_CLAIM, changes, actor="Reviewer 01", directory=DIRECTORY, reason="r",
                      output=self.dir / "corrections", log=self.log)

    def test_blocked_until_every_finding_is_dismissed_then_again_after_a_correction(self):
        corrections = ["--corrections", str(self.dir / "corrections")]
        self.assertEqual(self.states(), {AUTH_CLAIM: "to_review", self.clean: "ready"})
        self.assertEqual(self.gate(), 1)

        self.decide("dismiss_with_reason", rules=("R008",))
        self.assertEqual(self.states()[AUTH_CLAIM], "in_review")  # R009 still pending
        self.assertEqual(self.gate(), 1)

        self.decide("dismiss_with_reason", rules=("R009",))
        self.assertEqual(self.states()[AUTH_CLAIM], "ready")
        self.assertEqual(self.gate(), 0)

        self.correct(NOTE)  # version 2 still has both findings: earlier dismissals no longer count
        self.assertEqual(self.states(corrections=self.dir / "corrections")[AUTH_CLAIM], "rechecked")
        self.assertEqual(self.gate(*corrections), 1)

        self.correct(FIX)  # version 3: the authorization is supplied, nothing is flagged
        rows = judge(self.results, self.claims, self.log, DIRECTORY, corrections=self.dir / "corrections")
        auth = next(r for r in rows if r["claim_id"] == AUTH_CLAIM)
        self.assertEqual((auth["state"], auth["version"], auth["route"]), ("ready", 3, "CLEAR"))
        self.assertEqual(self.gate(*corrections), 0)

    def test_a_corrected_version_that_still_flags_is_decided_on_that_version(self):
        folder = self.dir / "corrections"
        self.correct(NOTE)  # version 2: both findings remain
        v2 = latest_version(json.loads(self.claims.read_text(encoding="utf-8").splitlines()[0]), folder)
        self.assertEqual(self.states(corrections=folder)[AUTH_CLAIM], "rechecked")

        # A decision on the claim as received is refused once v2 exists ...
        with self.assertRaisesRegex(ValueError, "another version"):
            self.decide("dismiss_with_reason", corrections=folder)
        # ... and one on v2 is accepted and counts.
        self.decide("dismiss_with_reason", rules=("R008",), input_hash=v2.input_hash, corrections=folder)
        self.assertEqual(self.states(corrections=folder)[AUTH_CLAIM], "in_review")
        self.decide("dismiss_with_reason", rules=("R009",), input_hash=v2.input_hash, corrections=folder)
        rows = judge(self.results, self.claims, self.log, DIRECTORY, corrections=folder)
        auth = next(r for r in rows if r["claim_id"] == AUTH_CLAIM)
        self.assertEqual((auth["state"], auth["version"], auth["pending"]), ("ready", 2, []))
        self.assertEqual(self.gate("--corrections", str(folder)), 0)
        # Without the corrections folder the gate judges v1, where nothing was dismissed.
        self.assertEqual(self.states()[AUTH_CLAIM], "to_review")

    def test_states_follow_the_latest_decision(self):
        for action, state in (("confirm_issue", "correction_needed"), ("request_information", "waiting_information"),
                              ("mark_corrected_for_recheck", "awaiting_recheck")):
            with self.subTest(action=action):
                self.decide(action)
                self.assertEqual(self.states()[AUTH_CLAIM], state)

    def test_only_actors_in_todays_directory_count(self):
        self.decide("dismiss_with_reason")
        self.assertEqual(self.states()[AUTH_CLAIM], "ready")
        rows = judge(self.results, self.claims, self.log, {"Someone else": "reviewer"})
        auth = next(r for r in rows if r["claim_id"] == AUTH_CLAIM)
        self.assertEqual(auth["state"], "to_review")  # the reviewer was removed: their dismissals stop counting
        self.assertEqual([p["rule_id"] for p in auth["pending"]], ["R008", "R009"])

    def test_pending_findings_carry_their_triggers(self):
        auth = next(r for r in judge(self.results, self.claims, self.log, DIRECTORY) if r["claim_id"] == AUTH_CLAIM)
        self.assertEqual({p["rule_id"]: p["triggers"] for p in auth["pending"]},
                         {"R008": ["high_severity", "issue"], "R009": ["low_confidence", "high_severity"]})

    def test_a_tampered_chain_judges_nothing(self):
        self.decide("dismiss_with_reason")
        self.log.write_text(self.log.read_text(encoding="utf-8").replace("Checked at the source.", "Approved."),
                            encoding="utf-8")
        with self.assertRaises(GateError):
            judge(self.results, self.claims, self.log, DIRECTORY)
        self.assertEqual(self.gate(), 2)

    def test_writes_one_row_per_claim(self):
        out = self.dir / "gate.jsonl"
        self.assertEqual(self.gate("--output", str(out)), 1)
        rows = load_jsonl(out)
        self.assertEqual([r["claim_id"] for r in rows], [AUTH_CLAIM, self.clean])
        self.assertEqual(set(rows[0]), {"claim_id", "version", "input_hash", "route", "state", "ready", "pending",
                                        "gate_version"})


class BadInputTests(GateCase):
    def test_rejected_and_unchecked_claims_are_blocked(self):
        lines = (ROOT / "examples" / "first_10_claims.jsonl").read_text(encoding="utf-8").splitlines()
        bad = json.loads(lines[0])
        bad["unexpected"] = 1
        self.run_claims([json.dumps(bad)] + lines[1:])
        states = self.states()
        self.assertEqual(states[bad["claim_id"]], "rejected")
        self.assertEqual(len(states), 10)
        self.assertEqual(self.gate(), 1)

    def test_the_directory_is_required(self):
        self.run_claims((ROOT / "examples" / "first_10_claims.jsonl").read_text(encoding="utf-8").splitlines())
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(["--results", str(self.results), "--claims", str(self.claims), "--log", str(self.log)])


if __name__ == "__main__":
    unittest.main()
