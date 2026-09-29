"""Tests for U5.6 correction -> new version -> recheck (claimguard.review.correction, DEC-011)."""
import copy
import hashlib
import json
import unittest
from pathlib import Path

from claimguard._pack import config, load_jsonl
from claimguard.engine.registry import REGISTRY
from claimguard.review.correction import ClaimVersion, correct, original, recheck, rule_engine

ROOT = Path(__file__).resolve().parents[1]
RULES = [r["rule_id"] for r in config(ROOT)["rules"]]
WHO = {"actor": "reviewer-1", "reason": "Verified against the source bill."}


def canonical_hash(claim):
    return hashlib.sha256(json.dumps(claim, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


class CorrectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dev = {c["claim_id"]: c for c in load_jsonl(ROOT / "data/development/claims.jsonl")}
        cls.base = json.loads((ROOT / "examples/worked_cases.json").read_text(encoding="utf-8"))[0]["claim"]
        cls.engine = staticmethod(rule_engine())  # a plain function, not bound to the test instance

    def status(self, run, rule_id):
        return next(r["status"] for r in run.results if r["rule_id"] == rule_id)

    # The version record

    def test_original_is_version_one(self):
        v1 = original(self.base)
        self.assertEqual((v1.claim_id, v1.version, v1.parent_hash), (self.base["claim_id"], 1, None))
        self.assertEqual(v1.input_hash, canonical_hash(self.base))
        self.assertEqual(v1.claim, self.base)

    def test_original_rejects_a_malformed_claim(self):
        bad = copy.deepcopy(self.base)
        bad["version"] = 2  # the version must never live inside the claim
        with self.assertRaises(ValueError):
            original(bad)

    def test_versions_cannot_be_mutated(self):
        source = copy.deepcopy(self.base)
        v1 = original(source)
        source["total_amount"] = 0  # the caller's dict is not the stored version
        v1.claim["total_amount"] = 0  # nor is a copy handed out
        self.assertEqual(v1.claim, self.base)
        with self.assertRaises(AttributeError):
            v1.version = 7

    def test_correction_creates_a_linked_version_and_keeps_the_original(self):
        v1 = original(self.base)
        v2 = correct(v1, [{"op": "replace", "path": "/total_amount", "value": 331}], **WHO)
        v3 = correct(v2, [{"op": "replace", "path": "/total_amount", "value": 330.5}], **WHO)
        self.assertEqual([v.version for v in (v1, v2, v3)], [1, 2, 3])
        self.assertEqual((v2.parent_hash, v3.parent_hash), (v1.input_hash, v2.input_hash))
        self.assertEqual(v1.claim["total_amount"], 330)
        self.assertEqual((v2.claim["total_amount"], v3.claim["total_amount"]), (331, 330.5))
        self.assertEqual(v2.changes, ({"op": "replace", "path": "/total_amount", "value": 331},))
        self.assertEqual((v2.actor, v2.reason), (WHO["actor"], WHO["reason"]))

    def test_record_is_the_lineage_without_the_claim(self):
        v2 = correct(original(self.base), [{"op": "replace", "path": "/total_amount", "value": 331}], **WHO)
        record = v2.record()
        self.assertEqual(set(record), {"claim_id", "version", "input_hash", "parent_hash", "actor", "reason", "changes"})
        json.dumps(record)  # serialisable for the audit trail

    # What a correction may not do

    def test_refuses_blank_actor_or_reason(self):
        v1 = original(self.base)
        change = [{"op": "replace", "path": "/total_amount", "value": 331}]
        for who in ({"actor": "", "reason": "x"}, {"actor": "a", "reason": "  "}, {"actor": None, "reason": "x"}):
            with self.subTest(**who):
                with self.assertRaises(ValueError):
                    correct(v1, change, **who)

    def test_refuses_a_correction_that_changes_nothing(self):
        v1 = original(self.base)
        for changes in ([], [{"op": "replace", "path": "/total_amount", "value": 330}]):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(ValueError, "changes nothing"):
                    correct(v1, changes, **WHO)

    def test_refuses_a_malformed_result(self):
        v1 = original(self.base)
        with self.assertRaises(ValueError):
            correct(v1, [{"op": "replace", "path": "/lines/0/quantity", "value": "two"}], **WHO)
        with self.assertRaises(ValueError):
            correct(v1, [{"op": "remove", "path": "/lines/0"}, {"op": "remove", "path": "/lines/0"}], **WHO)  # no lines left
        self.assertEqual(v1.claim, self.base)

    def test_refuses_editing_identifiers(self):
        v1 = original(self.base)
        for path in ("/claim_id", "/schema_version", "/lines/0/line_id"):
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "cannot be corrected"):
                    correct(v1, [{"op": "replace", "path": path, "value": "X"}], **WHO)

    def test_refuses_bad_operations_and_pointers(self):
        v1 = original(self.base)
        for op in ({"op": "replace", "path": "/lines/-1/quantity", "value": 2},
                   {"op": "replace", "path": "/lines/2/quantity", "value": 2},
                   {"op": "replace", "path": "/lines/01/quantity", "value": 2},
                   {"op": "replace", "path": "/no_such_field", "value": 2},
                   {"op": "remove", "path": "/member_id"},
                   {"op": "add", "path": "/nickname", "value": "x"},
                   {"op": "move", "from": "/lines/0", "path": "/lines/1"},
                   {"op": "replace", "path": "total_amount", "value": 2},
                   {"path": "/total_amount", "value": 2}):
            with self.subTest(op=op):
                with self.assertRaises(ValueError):
                    correct(v1, [op], **WHO)

    # The recheck

    def test_recheck_reruns_every_rule_in_order(self):
        run = recheck(original(self.base), [{"op": "replace", "path": "/total_amount", "value": 331}], engine=self.engine, **WHO)
        self.assertEqual([r["rule_id"] for r in run.results], RULES)
        self.assertEqual({r["claim_id"] for r in run.results}, {self.base["claim_id"]})
        for r in run.results:
            if r["rule_id"] not in REGISTRY:
                self.assertEqual(r["status"], "NOT_IMPLEMENTED", r["rule_id"])  # never shown as PASS

    def test_deleted_line_recomputes_the_total(self):
        """The board's own example: R012 re-evaluates itself, nothing is patched."""
        run = recheck(original(self.base), [{"op": "remove", "path": "/lines/1"}], engine=self.engine, **WHO)
        self.assertEqual(self.status(run, "R012"), "FAIL")  # 330 declared, 140 left
        self.assertIn({"rule_id": "R012", "before": "PASS", "after": "FAIL"}, run.status_changes)
        fixed = recheck(run.version, [{"op": "replace", "path": "/total_amount", "value": 140}], engine=self.engine, **WHO)
        self.assertEqual(self.status(fixed, "R012"), "PASS")
        self.assertEqual(fixed.version.version, 3)

    def test_correcting_the_total_fixes_r012_only(self):
        v1 = original(self.dev["CG-7E43D173774D"])  # declared 2375, lines sum to 2350
        run = recheck(v1, [{"op": "replace", "path": "/total_amount", "value": 2350}], engine=self.engine, **WHO)
        self.assertEqual(run.status_changes, [{"rule_id": "R012", "before": "FAIL", "after": "PASS"}])

    def test_authorization_correction_cascades_from_r008_to_r009(self):
        claim = self.dev["CG-B39790AC3604"]  # L1 SVC-IMAGE, no reference and no record
        line = claim["lines"][0]
        record = {"authorization_id": "AUTH-FIX-1", "patient_id": claim["patient_id"], "service_code": "SVC-IMAGE",
                  "status": "approved", "valid_from": line["service_date"], "valid_to": line["service_date"], "max_quantity": 1}
        run = recheck(original(claim), [{"op": "add", "path": "/authorizations/-", "value": record},
                                        {"op": "replace", "path": "/lines/0/authorization_id", "value": "AUTH-FIX-1"}],
                      engine=self.engine, **WHO)
        self.assertEqual(run.status_changes, [{"rule_id": "R008", "before": "FAIL", "after": "PASS"},
                                              {"rule_id": "R009", "before": "UNABLE_TO_ASSESS", "after": "PASS"}])

    def test_adding_the_missing_document_fixes_r010(self):
        claim = self.dev["CG-610536BBB38B"]  # SVC-DENTAL, attachments []
        line = claim["lines"][0]
        note = {"attachment_id": "ATT-FIX-1", "type": "service-note", "patient_id": claim["patient_id"], "service_code": "SVC-DENTAL",
                "service_date": line["service_date"], "document_status": "final", "text": "SYNTHETIC: service note."}
        run = recheck(original(claim), [{"op": "add", "path": "/attachments/0", "value": note}], engine=self.engine, **WHO)
        self.assertIn({"rule_id": "R010", "before": "FAIL", "after": "PASS"}, run.status_changes)

    def test_a_draft_does_not_turn_a_failure_into_a_pass(self):
        claim = self.dev["CG-610536BBB38B"]
        note = {"attachment_id": "ATT-FIX-1", "type": "service-note", "patient_id": claim["patient_id"], "service_code": "SVC-DENTAL",
                "service_date": claim["lines"][0]["service_date"], "document_status": "draft", "text": "SYNTHETIC: draft."}
        run = recheck(original(claim), [{"op": "add", "path": "/attachments/-", "value": note}], engine=self.engine, **WHO)
        self.assertEqual(self.status(run, "R010"), "UNABLE_TO_ASSESS")

    def test_recheck_never_touches_the_parent(self):
        v1 = original(self.base)
        recheck(v1, [{"op": "remove", "path": "/lines/1"}], engine=self.engine, **WHO)
        self.assertEqual(v1.claim, self.base)
        self.assertEqual(v1.input_hash, canonical_hash(self.base))


if __name__ == "__main__":
    unittest.main()
