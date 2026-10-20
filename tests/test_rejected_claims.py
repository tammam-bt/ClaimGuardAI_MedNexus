"""A claims file holding malformed claims must not break the review tools.

A held-out set may contain claims that ingestion rejects. The run survives
them (and with --complete gives each 15 UNABLE_TO_ASSESS results, DEC-013),
so the interface and the decision command must survive them too: they show
and accept decisions on the valid claims, and refuse, with a reason, a
decision on a claim that has no valid version to decide on.
"""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from claimguard._pack import load_jsonl
from claimguard.ingest.jsonl import claims_by_id
from claimguard.review.correction import original
from claimguard.run import main as run_main
from claimguard.ui import build
from claimguard.ui.decisions import append_decisions, version_hash

ROOT = Path(__file__).resolve().parents[1]
FIRST_10 = ROOT / "examples" / "first_10_claims.jsonl"
DIRECTORY = {"Reviewer 01": "reviewer"}


def run(*argv):
    with contextlib.redirect_stdout(io.StringIO()):
        return run_main([str(a) for a in argv])


class RejectedClaimTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        lines = FIRST_10.read_text(encoding="utf-8").splitlines()
        bad = json.loads(lines[0])
        bad["unexpected"] = 1                       # an extra envelope key: rejected at ingestion
        broken = json.loads(lines[1])
        broken["lines"] = [None]                    # makes the pack's validate_transport raise TypeError
        self.bad_id, self.broken_id = bad["claim_id"], broken["claim_id"]
        self.claims = self.dir / "claims.jsonl"
        self.claims.write_text("\n".join([json.dumps(bad), json.dumps(broken), "{not json"] + lines[2:]) + "\n",
                               encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def run_and_pick_finding(self, *flags):
        folder = Path(tempfile.mkdtemp(dir=self.dir))  # a fresh audit log per run
        results, log = folder / "pred.jsonl", folder / "audit.jsonl"
        run(*flags, "--input", self.claims, "--output", results, "--audit-log", log)
        rows = load_jsonl(results)
        finding = next(r for r in rows if r["status"] == "FAIL" and r["claim_id"] not in (self.bad_id, self.broken_id))
        return results, log, rows, finding

    def decision(self, finding, claim):
        return {"event": "review_decision", "claim_id": finding["claim_id"], "rule_id": finding["rule_id"],
                "action": "confirm_issue", "actor": "Reviewer 01", "reason": "Seen at the source.",
                "created_at": "2026-10-19T10:00:00Z", "original_status": finding["status"],
                "input_hash": original(claim).input_hash}

    def write(self, events):
        path = Path(tempfile.mkdtemp(dir=self.dir)) / "decisions.jsonl"
        path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
        return path

    def test_reader_keeps_every_object_with_a_claim_id(self):
        claims = claims_by_id(self.claims)
        self.assertEqual(len(claims), 10)  # the "{not json" line is skipped, not fatal
        self.assertEqual(list(claims)[:2], [self.bad_id, self.broken_id])

    def test_version_hash_is_none_for_a_claim_ingestion_rejects(self):
        claims = claims_by_id(self.claims)
        self.assertIsNone(version_hash(claims[self.bad_id]))
        self.assertIsNone(version_hash(claims[self.broken_id]))
        good = next(c for cid, c in claims.items() if cid not in (self.bad_id, self.broken_id))
        self.assertEqual(version_hash(good), original(good).input_hash)

    def test_decisions_on_valid_claims_are_appended(self):
        for flags in ((), ("--complete",)):
            with self.subTest(flags=flags):
                results, log, _, finding = self.run_and_pick_finding(*flags)
                claims = claims_by_id(self.claims)
                summary = append_decisions(self.write([self.decision(finding, claims[finding["claim_id"]])]), log,
                                           claims_path=self.claims, results_path=results,
                                           directory=DIRECTORY)
                self.assertEqual(summary["appended"], 1)

    def test_a_decision_on_a_rejected_claim_is_refused_with_a_reason(self):
        results, log, rows, finding = self.run_and_pick_finding("--complete")
        claims = claims_by_id(self.claims)
        on_rejected = dict(self.decision(finding, claims[finding["claim_id"]]),
                           claim_id=self.bad_id, rule_id="R001", original_status="UNABLE_TO_ASSESS")
        before = log.read_bytes()
        with self.assertRaises(ValueError) as caught:
            append_decisions(self.write([on_rejected]), log, claims_path=self.claims, results_path=results,
                                           directory=DIRECTORY)
        self.assertIn("rejected at ingestion", str(caught.exception))
        self.assertEqual(log.read_bytes(), before)

    def test_interface_builds_and_leaves_rejected_claims_to_the_rejected_list(self):
        for flags in ((), ("--complete",)):
            with self.subTest(flags=flags):
                results, _, _, _ = self.run_and_pick_finding(*flags)
                data = build(results, self.claims)
                shown = [c["claim"]["claim_id"] for c in data["claims"]]
                self.assertEqual(len(shown), 8)
                self.assertNotIn(self.bad_id, shown)
                self.assertNotIn(self.broken_id, shown)
                self.assertEqual(len(data["rejected"]), 3)  # both claims and the unreadable line


if __name__ == "__main__":
    unittest.main()
