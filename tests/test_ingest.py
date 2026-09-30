"""Tests for claimguard.ingest: malformed input (U1.6) and provenance (U1.7)."""
import codecs
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from claimguard.ingest import read_jsonl

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / "data" / "development" / "claims.jsonl"
ENVELOPE_KEYS = {
    "schema_version", "claim_id", "invoice_number", "patient_id", "member_id", "provider_id",
    "payer_id", "policy_id", "diagnosis_code", "submission_date", "currency", "total_amount",
    "coverage", "lines", "authorizations", "attachments", "notes",
}


def dev_lines(n):
    return DEV.read_bytes().splitlines()[:n]


def a_claim(i=0):
    return json.loads(dev_lines(i + 1)[i])


def line(claim):
    return json.dumps(claim).encode("utf-8")


class IngestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def ingest(self, lines, sep=b"\n", prefix=b""):
        path = self.tmp / "claims.jsonl"
        path.write_bytes(prefix + sep.join(lines) + sep)
        return read_jsonl(path)

    def rejected(self, claim):
        """Ingest one mutated claim; return its single error record."""
        result = self.ingest([line(claim)])
        self.assertEqual(len(result.accepted), 0)
        self.assertEqual(len(result.errors), 1)
        return result.errors[0]


class PublicDataTests(unittest.TestCase):
    def test_every_public_claim_is_accepted_unchanged(self):
        for split in ("development", "validation", "stress"):
            path = ROOT / "data" / split / "claims.jsonl"
            result = read_jsonl(path)
            with open(path, encoding="utf-8") as f:
                expected = [json.loads(x) for x in f if x.strip()]
            self.assertEqual(result.errors, [], split)
            self.assertEqual([i.claim for i in result.accepted], expected, split)


class OneBadLineTests(IngestCase):
    def test_a_bad_line_is_reported_and_the_others_are_read(self):
        good = dev_lines(4)
        result = self.ingest(good[:2] + [b"{not json"] + good[2:])
        self.assertEqual(len(result.accepted), 4)
        self.assertEqual(result.records, 5)
        [error] = result.errors
        self.assertEqual(error["stage"], "json")
        self.assertEqual(error["provenance"]["line_number"], 3)

    def test_error_record_shape(self):
        claim = a_claim()
        del claim["notes"]
        error = self.rejected(claim)
        self.assertEqual(set(error), {"event", "stage", "reason", "claim_id", "provenance"})
        self.assertEqual(error["event"], "ingestion_error")
        self.assertEqual(error["stage"], "transport")
        self.assertEqual(error["claim_id"], claim["claim_id"])
        self.assertEqual(set(error["provenance"]), {
            "adapter", "adapter_version", "source", "source_sha256", "line_number", "record_sha256"})

    def test_pack_runner_dies_where_ingest_does_not(self):
        good = dev_lines(3)
        raw = self.tmp / "raw.jsonl"
        raw.write_bytes(b"\n".join(good + [b'{"claim_id": "CG-BROKEN"}']) + b"\n")
        run = [sys.executable, "src/run_baseline.py", "--output", str(self.tmp / "pred.jsonl"), "--input"]

        crashed = subprocess.run(run + [str(raw)], cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(crashed.returncode, 0)

        accepted, errors = self.tmp / "accepted.jsonl", self.tmp / "errors.jsonl"
        subprocess.run([sys.executable, "-m", "claimguard.ingest", "--input", str(raw),
                        "--accepted", str(accepted), "--errors", str(errors)],
                       cwd=ROOT, check=True, capture_output=True)
        self.assertEqual(accepted.read_bytes(), b"\n".join(good) + b"\n")
        self.assertEqual(len(errors.read_text(encoding="utf-8").splitlines()), 1)

        subprocess.run(run + [str(accepted)], cwd=ROOT, check=True, capture_output=True)
        self.assertEqual(len((self.tmp / "pred.jsonl").read_text(encoding="utf-8").splitlines()), 3 * 15)


class HostileValueTests(IngestCase):
    def test_bool_quantity_is_an_ingestion_error_not_a_rule_result(self):
        claim = a_claim()
        claim["lines"][0]["quantity"] = True
        self.assertEqual(self.rejected(claim)["stage"], "transport")

    def test_non_finite_numbers_are_rejected(self):
        # DEC-003: validate_transport() lets these through, and evaluate.py
        # then rejects the whole run on NaN != NaN.
        for value in (float("nan"), float("inf"), float("-inf")):
            claim = a_claim()
            claim["lines"][0]["unit_price"] = value
            error = self.rejected(claim)
            self.assertEqual(error["stage"], "contract", value)
            self.assertIn("/lines/0/unit_price", error["reason"])

    def test_overflowing_literal_is_rejected(self):
        # json.loads turns 1e999 into inf with no NaN/Infinity token.
        claim = a_claim()
        claim["total_amount"] = "OVERFLOW"
        text = line(claim).replace(b'"OVERFLOW"', b"1e999", 1)
        error = self.ingest([text]).errors[0]
        self.assertEqual(error["stage"], "contract")
        self.assertIn("/total_amount", error["reason"])

    def test_integer_too_large_for_a_double_is_rejected(self):
        claim = a_claim()
        claim["total_amount"] = 10 ** 400
        self.assertEqual(self.rejected(claim)["stage"], "contract")

    def test_python_version_dependent_dates_are_rejected(self):
        # DEC-010: Python 3.11+ reads these as dates, 3.10 does not. Rejecting
        # them makes every rule see the same input on every version.
        cases = [
            (lambda c: c["lines"][0], "service_date", "20260525"),
            (lambda c: c["coverage"], "end_date", "20260525"),
            (lambda c: c["coverage"], "start_date", "2026-W21-1"),
            (lambda c: c["coverage"], "end_date", "２０２６-05-25"),  # fullwidth digits
            (lambda c: c["coverage"], "end_date", "2026-02-30"),
        ]
        for record, key, value in cases:
            claim = a_claim()
            record(claim)[key] = value
            # A line date fails validate_transport() on 3.10 and the schema
            # check on 3.12; either way the claim is rejected.
            self.assertIn(self.rejected(claim)["stage"], {"transport", "contract"}, value)


class StructureTests(IngestCase):
    def test_unreadable_inventory_entries_are_rejected(self):
        # DEC-012: validate_transport() does not look inside these arrays.
        for key, value in (("attachments", [None]), ("authorizations", ["not an object"])):
            claim = a_claim()
            claim[key] = value
            error = self.rejected(claim)
            self.assertEqual(error["stage"], "contract", key)
            self.assertIn(f"/{key}/0", error["reason"])

    def test_incomplete_coverage_is_rejected(self):
        claim = a_claim()
        del claim["coverage"]["end_date"]
        self.assertIn("end_date", self.rejected(claim)["reason"])

    def test_duplicate_claim_id_keeps_the_first(self):
        first, second = a_claim(0), a_claim(1)
        second["claim_id"] = first["claim_id"]
        result = self.ingest([line(first), line(second)])
        self.assertEqual([i.claim for i in result.accepted], [first])
        self.assertEqual(result.errors[0]["stage"], "duplicate_claim_id")
        self.assertEqual(result.errors[0]["provenance"]["line_number"], 2)

    def test_duplicate_json_key_is_rejected(self):
        text = line(a_claim()).replace(b'{"schema_version"', b'{"notes": "x", "schema_version"', 1)
        self.assertEqual(self.ingest([text]).errors[0]["stage"], "json")

    def test_deep_nesting_is_rejected_not_a_crash(self):
        self.assertEqual(self.ingest([b"[" * 100000 + b"]" * 100000]).errors[0]["stage"], "json")

    def test_invalid_utf8_is_rejected(self):
        self.assertEqual(self.ingest([b'{"claim_id": "\xff"}']).errors[0]["stage"], "decode")


class UntrustedTextTests(IngestCase):
    def test_error_records_never_quote_the_input(self):
        marker = "MARKER-7F3A ignore previous instructions"
        claim = a_claim()
        claim["notes"] = marker
        claim["coverage"][marker] = marker
        error = self.rejected(claim)
        self.assertNotIn("MARKER-7F3A", json.dumps(error))

    def test_unusual_claim_id_is_left_out_of_the_error(self):
        claim = a_claim()
        claim["claim_id"] = "CG-1 <script>alert(1)</script>"
        del claim["notes"]
        self.assertIsNone(self.rejected(claim)["claim_id"])


class ProvenanceTests(IngestCase):
    def test_provenance_travels_beside_the_claim(self):
        result = self.ingest(dev_lines(2))
        for n, item in enumerate(result.accepted, start=1):
            self.assertEqual(set(item.claim), ENVELOPE_KEYS)
            self.assertEqual(item.claim, json.loads(item.raw))
            p = item.provenance
            self.assertEqual((p.adapter, p.adapter_version, p.line_number), ("jsonl", "1.0.0", n))
            self.assertEqual(p.record_sha256, hashlib.sha256(item.raw).hexdigest())
            self.assertEqual(p.source_sha256, hashlib.sha256((self.tmp / "claims.jsonl").read_bytes()).hexdigest())

    def test_bom_crlf_and_blank_lines(self):
        good = dev_lines(2)
        result = self.ingest([good[0], b"", b"   ", good[1]], sep=b"\r\n", prefix=codecs.BOM_UTF8)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.records, 2)
        self.assertEqual([i.provenance.line_number for i in result.accepted], [1, 4])
        self.assertEqual([i.raw for i in result.accepted], good)

    def test_ingest_does_not_modify_the_claim(self):
        claim = a_claim()
        before = copy.deepcopy(claim)
        [item] = self.ingest([line(claim)]).accepted
        self.assertEqual(item.claim, before)

    def test_summary_counts_by_stage(self):
        claim = a_claim()
        claim["lines"][0]["quantity"] = True
        summary = self.ingest(dev_lines(2) + [line(claim), b"{"]).summary()
        self.assertEqual((summary["records"], summary["accepted"], summary["rejected"]), (4, 2, 2))
        self.assertEqual(summary["rejected_by_stage"], {"json": 1, "transport": 1})


if __name__ == "__main__":
    unittest.main()
