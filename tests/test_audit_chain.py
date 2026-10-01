"""Tests for the audit chain (claimguard.audit.chain)."""
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from claimguard._pack import config, load_jsonl
from claimguard.ai.watchdog import explain_safely
from claimguard.audit.chain import AuditError, append, default_anchor, verify
from claimguard.engine.runner import Engine
from claimguard.guards import screen
from claimguard.ingest import read_jsonl
from claimguard.review.correction import correct, original
from claimguard.run import main as run_main

ROOT = Path(__file__).resolve().parents[1]
STRESS = ROOT / "data" / "stress" / "claims.jsonl"


def pack_audit():
    spec = importlib.util.spec_from_file_location("pack_audit_for_test", ROOT / "src" / "audit.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def review(**overrides):
    event = {"event": "review_decision", "claim_id": "CG-1", "rule_id": "R001", "action": "confirm_issue",
             "actor": "reviewer-1", "reason": "Invoice number missing on the source bill.",
             "created_at": "2026-10-01T10:00:00+00:00", "original_status": "FAIL", "input_hash": "0" * 64}
    event.update(overrides)
    return event


class ChainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "audit.jsonl"
        self.anchor = default_anchor(self.log)

    def tearDown(self):
        self.tmp.cleanup()

    def three(self):
        append(self.log, [review(claim_id=f"CG-{i}") for i in range(3)], self.anchor)

    def test_default_anchor_sits_beside_the_log(self):
        self.assertEqual(Path(self.anchor).name, "audit.head.json")

    def test_append_then_verify(self):
        head, _ = append(self.log, [review()], self.anchor)
        self.assertEqual(verify(self.log, self.anchor), (head, 1))

    def test_the_packs_own_verifier_accepts_our_log(self):
        self.three()
        self.assertEqual(pack_audit().verify(self.log)[1], 3)

    def test_edited_event_detected(self):
        self.three()
        self.log.write_text(self.log.read_text(encoding="utf-8").replace("CG-1", "CG-9"), encoding="utf-8")
        with self.assertRaisesRegex(AuditError, "event 2"):
            verify(self.log)

    def test_truncation_detected_with_anchor(self):
        self.three()
        lines = self.log.read_text(encoding="utf-8").splitlines()
        self.log.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
        self.assertEqual(verify(self.log)[1], 2)  # without the anchor: the pack's documented gap
        with self.assertRaisesRegex(AuditError, "removed"):
            verify(self.log, self.anchor)

    def test_deleted_log_detected_with_anchor(self):
        self.three()
        self.log.unlink()
        with self.assertRaisesRegex(AuditError, "removed"):
            verify(self.log, self.anchor)

    def test_wholesale_rewrite_detected_with_anchor(self):
        self.three()
        saved = Path(self.anchor).read_text(encoding="utf-8")
        self.log.unlink()
        append(self.log, [review(claim_id=f"CG-X{i}") for i in range(3)])  # a fresh, internally valid chain
        Path(self.anchor).write_text(saved, encoding="utf-8")
        with self.assertRaisesRegex(AuditError, "rewritten"):
            verify(self.log, self.anchor)

    def test_invalid_events_rejected_and_nothing_written(self):
        for bad in ({"event": "made_up"}, {"event": "run_started", "run_id": "r"},
                    review(reason="   "), review(action="approve_payment"), {"type": "review_decision"}):
            with self.subTest(bad=bad), self.assertRaises(AuditError):
                append(self.log, [review(), bad], self.anchor)
        self.assertFalse(self.log.exists())

    def test_cannot_append_to_a_broken_chain(self):
        self.three()
        self.log.write_text(self.log.read_text(encoding="utf-8").replace("CG-1", "CG-9"), encoding="utf-8")
        with self.assertRaises(AuditError):
            append(self.log, [review()], self.anchor)

    def test_correction_version_is_a_lineage_event(self):
        claim = load_jsonl(ROOT / "examples" / "first_10_claims.jsonl")[0]
        v2 = correct(original(claim), [{"op": "replace", "path": "/total_amount", "value": claim["total_amount"] + 1}],
                     actor="reviewer-1", reason="Total re-read from the source bill.")
        self.assertEqual(append(self.log, [{"event": "version_created", **v2.record()}], self.anchor)[1], 1)

    def test_the_teams_own_records_go_in_unchanged(self):
        bad_file = Path(self.tmp.name) / "bad.jsonl"
        bad_file.write_text("{nope\n", encoding="utf-8")
        ingestion_error = read_jsonl(bad_file).errors[0]
        claims = load_jsonl(STRESS)
        injection_flag = next(s.as_event() for s in map(screen, claims) if s.flagged)

        class Broken:
            name, model = "broken", None

            def explain(self, finding, rule):
                raise RuntimeError("down")

        finding = next(r for c in claims for r in Engine(ROOT).evaluate_claim(c) if r["status"] == "FAIL")
        rule = {r["rule_id"]: r for r in config(ROOT)["rules"]}[finding["rule_id"]]
        _, model_failure = explain_safely(Broken(), finding, rule, "1.0.0", 1.0)
        _, count = append(self.log, [ingestion_error, injection_flag, model_failure], self.anchor)
        self.assertEqual(count, 3)


class RunWritesAuditTests(unittest.TestCase):
    def test_run_records_start_flags_and_finish(self):
        with tempfile.TemporaryDirectory() as d:
            out, log = Path(d) / "p.jsonl", Path(d) / "audit.jsonl"
            with redirect_stdout(io.StringIO()):
                code = run_main(["--strict", "--input", str(STRESS), "--output", str(out), "--audit-log", str(log)])
            self.assertEqual(code, 0)
            events = [json.loads(l)["event"] for l in log.read_text(encoding="utf-8").splitlines()]
            kinds = [e["event"] for e in events]
            self.assertEqual((kinds[0], kinds[-1]), ("run_started", "run_finished"))
            self.assertTrue(kinds.count("injection_flag") >= 1)
            self.assertEqual(len({e["run_id"] for e in events}), 1)
            manifest = Path(f"{out}.manifest.json")
            self.assertEqual(events[-1]["manifest_sha256"], hashlib.sha256(manifest.read_bytes()).hexdigest())
            self.assertEqual(verify(log, default_anchor(log))[1], len(events))


if __name__ == "__main__":
    unittest.main()
