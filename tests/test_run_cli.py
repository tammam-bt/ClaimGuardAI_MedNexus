"""Tests for python -m claimguard.run, the one pipeline command."""
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from claimguard._pack import load_jsonl
from claimguard.guards import screen
from claimguard.run import main

ROOT = Path(__file__).resolve().parents[1]
FIRST_10 = ROOT / "examples" / "first_10_claims.jsonl"
STRESS = ROOT / "data" / "stress"
RULE_IDS = [f"R{i:03}" for i in range(1, 16)]


def run(*argv):
    with redirect_stdout(io.StringIO()):
        return main([str(a) for a in argv])


def manifest_of(output):
    return json.loads(Path(f"{output}.manifest.json").read_text(encoding="utf-8"))


class RunCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_writes_results_and_manifest(self):
        out = self.dir / "nested" / "pred.jsonl"
        self.assertEqual(run("--strict", "--input", FIRST_10, "--output", out), 0)
        claims = load_jsonl(FIRST_10)
        self.assertEqual(len(load_jsonl(out)), 15 * len(claims))
        m = manifest_of(out)
        self.assertEqual(m["input"]["source_sha256"], hashlib.sha256(FIRST_10.read_bytes()).hexdigest())
        first_line = FIRST_10.read_bytes().splitlines()[0]
        self.assertEqual(m["claims"][0]["claim_id"], claims[0]["claim_id"])
        self.assertEqual(m["claims"][0]["record_sha256"], hashlib.sha256(first_line).hexdigest())
        self.assertEqual(sorted(m["rules"]), RULE_IDS)
        self.assertTrue(all(r["implemented"] for r in m["rules"].values()))
        self.assertEqual((m["results"], sum(m["statuses"].values())), (150, 150))
        self.assertEqual((m["ingestion_errors"], m["rule_errors"], m["ai"]), ([], [], None))

    def test_output_is_deterministic(self):
        a, b = self.dir / "a.jsonl", self.dir / "b.jsonl"
        run("--input", FIRST_10, "--output", a)
        run("--input", FIRST_10, "--output", b)
        self.assertEqual(a.read_bytes(), b.read_bytes())

    def test_bad_lines_are_ingestion_errors_not_crashes(self):
        good = FIRST_10.read_text(encoding="utf-8").splitlines()[0]
        broken = json.loads(good)
        broken.pop("currency")
        source = self.dir / "in.jsonl"
        source.write_text("\n".join([good, "{not json", json.dumps(broken), "", good]) + "\n", encoding="utf-8")
        out = self.dir / "p.jsonl"
        self.assertEqual(run("--input", source, "--output", out), 2)
        self.assertEqual(len(load_jsonl(out)), 15)
        errors = manifest_of(out)["ingestion_errors"]
        self.assertEqual([(e["provenance"]["line_number"], e["stage"]) for e in errors],
                         [(2, "json"), (3, "transport"), (5, "duplicate_claim_id")])

    def test_empty_input_gives_empty_output(self):
        source = self.dir / "empty.jsonl"
        source.write_text("", encoding="utf-8")
        out = self.dir / "p.jsonl"
        self.assertEqual(run("--input", source, "--output", out), 0)
        self.assertEqual(out.read_text(encoding="utf-8"), "")
        self.assertEqual(manifest_of(out)["input"]["records"], 0)

    def test_csv_and_fhir_inputs_give_the_same_results(self):
        a, b, c = self.dir / "j.jsonl", self.dir / "c.jsonl", self.dir / "f.jsonl"
        run("--strict", "--input", STRESS / "claims.jsonl", "--output", a)
        run("--strict", "--input", STRESS / "csv", "--output", b)
        run("--strict", "--input", STRESS / "fhir_bundles.jsonl", "--sidecar", STRESS / "claims.jsonl", "--output", c)
        self.assertEqual(load_jsonl(a), load_jsonl(b))
        self.assertEqual(load_jsonl(a), load_jsonl(c))
        self.assertEqual({manifest_of(p)["input"]["adapter"] for p in (a, b, c)}, {"jsonl", "csv", "fhir"})

    def test_injection_flags_recorded_and_flagged_claims_still_checked(self):
        out = self.dir / "s.jsonl"
        run("--strict", "--input", STRESS / "claims.jsonl", "--output", out)
        claims = load_jsonl(STRESS / "claims.jsonl")
        expected = [s.as_event() for s in map(screen, claims) if s.flagged]
        self.assertTrue(expected)
        self.assertEqual(manifest_of(out)["injection_flags"], expected)
        self.assertEqual(len(load_jsonl(out)), 15 * len(claims))

    def test_explain_writes_beside_results_and_never_changes_them(self):
        plain, explained = self.dir / "plain.jsonl", self.dir / "explained.jsonl"
        run("--input", FIRST_10, "--output", plain)
        run("--input", FIRST_10, "--output", explained, "--explain")
        self.assertEqual(plain.read_bytes(), explained.read_bytes())
        flagged = [r for r in load_jsonl(explained) if r["status"] in ("FAIL", "UNABLE_TO_ASSESS")]
        records = load_jsonl(f"{explained}.explanations.jsonl")
        self.assertEqual(len(records), len(flagged))
        ai = manifest_of(explained)["ai"]
        self.assertEqual((ai["summary"]["provider"], ai["model_failures"]), ("mock", []))


if __name__ == "__main__":
    unittest.main()
