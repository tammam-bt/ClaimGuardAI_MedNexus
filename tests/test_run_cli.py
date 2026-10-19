"""Tests for python -m claimguard.run, the one pipeline command."""
import hashlib
import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from claimguard._pack import load_jsonl, score
from claimguard.audit import chain
from claimguard.guards import screen
from claimguard.review.routing import route_run
from claimguard.run import main

ROOT = Path(__file__).resolve().parents[1]
FIRST_10 = ROOT / "examples" / "first_10_claims.jsonl"
FIRST_10_GOLD = ROOT / "examples" / "first_10_expected_results.jsonl"
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

    def test_manifest_hashes_the_files_the_run_wrote(self):
        # The audit chain records the manifest's hash, so hashing the outputs
        # here makes a changed results or explanations file detectable.
        plain, explained = self.dir / "plain.jsonl", self.dir / "explained.jsonl"
        run("--input", FIRST_10, "--output", plain)
        run("--input", FIRST_10, "--output", explained, "--explain")
        sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
        self.assertEqual(manifest_of(plain)["outputs"], {"results_sha256": sha(plain), "explanations_sha256": None})
        self.assertEqual(manifest_of(explained)["outputs"],
                         {"results_sha256": sha(explained), "explanations_sha256": sha(f"{explained}.explanations.jsonl")})


class CompleteOutputTests(unittest.TestCase):
    """--complete: a claim rejected at ingestion still gets its 15 results, all
    UNABLE_TO_ASSESS, so one malformed claim cannot void a scored run."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.lines = FIRST_10.read_text(encoding="utf-8").splitlines()
        bad = json.loads(self.lines[0])
        bad["lines"][0]["service_date"] = "20260525"  # not YYYY-MM-DD: rejected at ingestion
        self.bad_id = bad["claim_id"]
        self.source = self.dir / "in.jsonl"
        self.source.write_text("\n".join([json.dumps(bad)] + self.lines[1:]) + "\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_off_by_default(self):
        out = self.dir / "p.jsonl"
        self.assertEqual(run("--input", self.source, "--output", out), 2)
        self.assertNotIn(self.bad_id, {r["claim_id"] for r in load_jsonl(out)})
        self.assertNotIn("completed_rejected", manifest_of(out))

    def test_rejected_claim_gets_15_abstentions_and_the_scorer_accepts_the_run(self):
        out = self.dir / "p.jsonl"
        self.assertEqual(run("--complete", "--input", self.source, "--output", out), 2)  # still reports the rejection
        rows = load_jsonl(out)
        mine = [r for r in rows if r["claim_id"] == self.bad_id]
        self.assertEqual([r["rule_id"] for r in mine], RULE_IDS)
        for r in mine:
            self.assertEqual((r["status"], r["evidence"], r["affected_line_ids"], r["requires_human_review"]),
                             ("UNABLE_TO_ASSESS", [{"path": "/claim_id", "value": self.bad_id}], [], True))
        # Every pair the gold expects, exactly once, and every row passes the
        # scorer's checks against the file it reads. (The pack's gold cites the
        # unmutated date, so it cannot itself be scored against this file.)
        claims = {c["claim_id"]: c for c in load_jsonl(self.source)}
        self.assertEqual(sorted((r["claim_id"], r["rule_id"]) for r in rows),
                         sorted((r["claim_id"], r["rule_id"]) for r in load_jsonl(FIRST_10_GOLD)))
        self.assertEqual(score(rows, rows, claims)["overall"]["count"], 150)  # raises if a row is rejected
        self.assertEqual(manifest_of(out)["completed_rejected"], [self.bad_id])

    def test_accepted_claims_are_unchanged(self):
        plain, complete = self.dir / "plain.jsonl", self.dir / "complete.jsonl"
        run("--input", self.source, "--output", plain)
        run("--complete", "--input", self.source, "--output", complete)
        self.assertEqual([r for r in load_jsonl(complete) if r["claim_id"] != self.bad_id], load_jsonl(plain))

    def test_rejected_claim_routes_to_escalate(self):
        out = self.dir / "p.jsonl"
        run("--complete", "--input", self.source, "--output", out)
        route = next(r for r in route_run(load_jsonl(out)) if r["claim_id"] == self.bad_id)
        self.assertEqual(route["route"], "ESCALATE")

    def test_no_id_no_duplicate_pairs(self):
        good = self.lines[1]
        source = self.dir / "dup.jsonl"
        source.write_text("\n".join([good, "{not json", good]) + "\n", encoding="utf-8")
        out = self.dir / "p.jsonl"
        run("--complete", "--input", source, "--output", out)
        self.assertEqual(len(load_jsonl(out)), 15)  # unreadable line: no ID; duplicate: already has its 15
        self.assertEqual(manifest_of(out)["completed_rejected"], [])

    def test_explanations_skip_completed_claims(self):
        out = self.dir / "p.jsonl"
        run("--complete", "--explain", "--input", self.source, "--output", out)
        self.assertNotIn(self.bad_id, {e["claim_id"] for e in load_jsonl(f"{out}.explanations.jsonl")})

    def test_an_unusual_claim_id_is_completed_too(self):
        # Ingestion keeps unusual IDs out of its error records (they are not
        # quoted), but the scorer still expects 15 results for that claim.
        odd = json.loads(self.lines[1])
        odd["claim_id"], odd["unexpected"] = "CG weird/id ü", 1
        source = self.dir / "odd.jsonl"
        source.write_text("\n".join([self.lines[0], json.dumps(odd)]) + "\n", encoding="utf-8")
        out = self.dir / "p.jsonl"
        run("--complete", "--input", source, "--output", out)
        rows = load_jsonl(out)
        self.assertEqual(manifest_of(out)["completed_rejected"], ["CG weird/id ü"])
        self.assertIsNone(manifest_of(out)["ingestion_errors"][0]["claim_id"])  # still not quoted there
        claims = {c["claim_id"]: c for c in load_jsonl(source)}
        self.assertEqual(score(rows, rows, claims)["overall"]["count"], 30)

    def test_csv_completes_rejected_claims_but_not_orphan_rows(self):
        folder = self.dir / "csv"
        shutil.copytree(STRESS / "csv", folder)
        lines = folder / "lines.csv"
        rows = lines.read_bytes().split(b"\r\n")
        broken = rows[1].split(b",")
        broken[5] = b"one"  # quantity: not a number
        rows[1] = b",".join(broken)
        bad_id = broken[0].decode()
        lines.write_bytes(b"\r\n".join(rows[:-1] + [b"CG-000000000000,L1,SVC-LAB,2026-03-17,,1,140,140,", b""]))
        out = self.dir / "p.jsonl"
        run("--complete", "--input", folder, "--output", out)
        m = manifest_of(out)
        self.assertEqual(sorted(e["stage"] for e in m["ingestion_errors"]), ["csv", "orphan_row"])
        self.assertEqual(m["completed_rejected"], [bad_id])
        out_rows = load_jsonl(out)
        claims = {c["claim_id"]: c for c in load_jsonl(STRESS / "claims.jsonl")}  # what the scorer reads
        self.assertEqual(score(load_jsonl(STRESS / "expected_results.jsonl"), out_rows, claims)["overall"]["count"], 750)

    def test_audit_log_counts_completed_results(self):
        out, log = self.dir / "p.jsonl", self.dir / "audit.jsonl"
        run("--complete", "--input", self.source, "--output", out, "--audit-log", log)
        events = [row["event"] for row in load_jsonl(log)]
        finished = next(e for e in events if e["event"] == "run_finished")
        self.assertEqual((finished["results"], finished["rejected"]), (150, 1))
        chain.verify(log, chain.default_anchor(log))  # raises if the chain is broken

    def test_a_lone_surrogate_never_crashes_the_run(self):
        # "\ud800" is legal JSON but not encodable as UTF-8; results quote it
        # as evidence. That row is written with ASCII escapes and reads back
        # identical, so the scorer's evidence check still matches.
        claim = json.loads(self.lines[0])
        claim["invoice_number"] = "INV-\ud800"
        source = self.dir / "s.jsonl"
        source.write_text("\n".join([json.dumps(claim)] + self.lines[1:]) + "\n", encoding="utf-8")
        out, log = self.dir / "p.jsonl", self.dir / "audit.jsonl"
        self.assertEqual(run("--explain", "--input", source, "--output", out, "--audit-log", log), 0)
        rows = load_jsonl(out)
        claims = {c["claim_id"]: c for c in load_jsonl(source)}
        self.assertEqual(score(rows, rows, claims)["overall"]["count"], 150)
        plain = self.dir / "plain.jsonl"
        run("--input", FIRST_10, "--output", plain)
        self.assertEqual(rows[15:], load_jsonl(plain)[15:])  # other claims untouched

    def test_complete_and_limit_exclude_each_other(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run("--complete", "--limit", "3", "--input", self.source, "--output", self.dir / "p.jsonl")

    def test_fhir_completes_every_sidecar_claim_and_nothing_else(self):
        bundles = (STRESS / "fhir_bundles.jsonl").read_text(encoding="utf-8").splitlines()[:3]
        side = (STRESS / "claims.jsonl").read_text(encoding="utf-8").splitlines()[:3]
        sidecar = self.dir / "side.jsonl"
        sidecar.write_text("\n".join(side) + "\n", encoding="utf-8")
        foreign = json.loads(bundles[1])
        next(e["resource"] for e in foreign["entry"] if e["resource"]["resourceType"] == "Claim")["id"] = "CG-000000000000"
        source = self.dir / "b.jsonl"
        source.write_text("\n".join([bundles[0], json.dumps(foreign), "{not json"]) + "\n", encoding="utf-8")
        out = self.dir / "p.jsonl"
        run("--complete", "--input", source, "--sidecar", sidecar, "--output", out)
        ids = [json.loads(s)["claim_id"] for s in side]
        self.assertEqual(sorted({r["claim_id"] for r in load_jsonl(out)}), sorted(ids))  # never CG-000000000000
        self.assertEqual(manifest_of(out)["completed_rejected"], ids[1:])
        claims = {c["claim_id"]: c for c in load_jsonl(sidecar)}
        gold = [r for r in load_jsonl(STRESS / "expected_results.jsonl") if r["claim_id"] in claims]
        self.assertEqual(score(gold, load_jsonl(out), claims)["overall"]["count"], 45)


if __name__ == "__main__":
    unittest.main()
