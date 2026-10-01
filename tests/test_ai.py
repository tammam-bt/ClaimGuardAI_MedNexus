"""Tests for the bounded AI: minimization (U6.3), provider (U2.7),
watchdog (U3.7) and explainer (U3.5). Built against the mock."""
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from claimguard._pack import config
from claimguard.ai import (
    build_messages, deterministic, explain_run, explain_safely, load_prompt, minimize,
    select_provider, timeout_from,
)
from claimguard.ai import exercises
from claimguard.ai.provider import MockProvider

ROOT = Path(__file__).resolve().parents[1]
RULES = {r["rule_id"]: r for r in config(ROOT)["rules"]}
INJECTED = "CG-116C84D4774D"  # its attachment carries the pack's injection sentence


def jsonl(path):
    with open(ROOT / path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


CASES = {c["case_id"]: c for c in jsonl("exercises/llm_explanation_cases.jsonl")}
FINDING, RULE = CASES["EX-01"]["finding"], CASES["EX-01"]["rule"]  # R001 FAIL


class Fake:
    name, model = "fake", "fake-1"

    def __init__(self, answer):
        self.answer = answer
        self.calls = 0

    def explain(self, finding, rule):
        self.calls += 1
        return self.answer(finding, rule)


def good(finding, rule):
    return {"explanation": f"{finding['rule_id']}: the unit price on line L1 is missing.",
            "cited_evidence_paths": [e["path"] for e in finding["evidence"]],
            "cited_rule_ids": [finding["rule_id"]],
            "needs_human_review": finding["requires_human_review"]}


def answering(**changes):
    return Fake(lambda f, r: {**good(f, r), **changes})


def explain(provider, finding=FINDING, rule=RULE, timeout=5.0):
    return explain_safely(provider, finding, rule, "1.0.0", timeout)


class MinimizeTests(unittest.TestCase):
    def setUp(self):
        self.r010 = next(r for r in jsonl("data/development/expected_results.jsonl")
                         if r["claim_id"] == INJECTED and r["rule_id"] == "R010")

    def test_model_never_sees_the_claim_id_or_free_text(self):
        self.assertIn("SYNTHETIC UNTRUSTED", json.dumps(self.r010["evidence"]))
        finding_view, rule_view = minimize(self.r010, RULES["R010"])
        system, user = build_messages(finding_view, rule_view)
        for text in (json.dumps(finding_view), user):
            self.assertNotIn(INJECTED, text)
            self.assertNotIn("SYNTHETIC UNTRUSTED", text)
            self.assertIn("untrusted text withheld", text)
        self.assertEqual([e["path"] for e in finding_view["evidence"]],
                         [e["path"] for e in self.r010["evidence"]])

    def test_short_codes_are_kept_and_long_strings_withheld(self):
        finding = copy.deepcopy(FINDING)
        finding["evidence"] = [{"path": "/lines/0/service_code", "value": "SVC-IMAGE"},
                               {"path": "/lines/0/modifier", "value": "x" * 65}]
        values = [e["value"] for e in minimize(finding, RULE)[0]["evidence"]]
        self.assertEqual(values[0], "SVC-IMAGE")
        self.assertIn("withheld", values[1])

    def test_minimize_does_not_modify_its_input(self):
        before = copy.deepcopy(self.r010)
        minimize(self.r010, RULES["R010"])
        self.assertEqual(self.r010, before)

    def test_prompt_and_version(self):
        system, version = load_prompt()
        self.assertEqual(version, "1.0.0")
        self.assertEqual(system, (ROOT / "prompts" / "explain_findings.md").read_text(encoding="utf-8"))


class WatchdogTests(unittest.TestCase):
    def assertFallback(self, provider, reason, **kw):
        record, event = explain(provider, **kw)
        self.assertEqual(record["source"], "fallback")
        self.assertEqual(record["failure"]["reason"], reason)
        self.assertEqual(event["reason"], reason)
        self.assertEqual(event["event"], "model_failure")
        for k, v in deterministic(kw.get("finding", FINDING)).items():
            self.assertEqual(record[k], v)
        return record, event

    def test_mock_answer_is_used(self):
        record, event = explain(MockProvider())
        self.assertEqual((record["source"], record["failure"], event), ("provider", None, None))
        self.assertEqual(record["explanation"], FINDING["explanation"])

    def test_answer_as_json_text_is_parsed(self):
        record, _ = explain(Fake(lambda f, r: json.dumps(good(f, r))))
        self.assertEqual(record["source"], "provider")

    def test_invalid_json(self):
        self.assertFallback(Fake(lambda f, r: "Sure! Here is the explanation: ..."), "invalid_json")

    def test_invalid_output(self):
        for provider in (
            answering(extra="x"),
            answering(cited_evidence_paths=["/invented/path"]),
            answering(cited_evidence_paths=[]),
            answering(cited_rule_ids=["R999"]),
            answering(needs_human_review=False),
            answering(explanation="  "),
            Fake(lambda f, r: ["not", "an", "object"]),
        ):
            self.assertFallback(provider, "invalid_output")

    def test_model_error_does_not_leak_its_message(self):
        def boom(f, r):
            raise RuntimeError("upstream said: key sk-ant-SECRET")
        record, event = self.assertFallback(Fake(boom), "model_error")
        self.assertNotIn("SECRET", json.dumps([record, event]))

    def test_timeout(self):
        start = time.monotonic()
        self.assertFallback(Fake(lambda f, r: time.sleep(2) or good(f, r)), "timeout", timeout=0.05)
        self.assertLess(time.monotonic() - start, 1.0)

    def test_text_that_contradicts_the_status(self):
        for text in ("All checks passed; the claim can be paid.", "No issues found.",
                     "The claim is approved."):
            self.assertFallback(answering(explanation=text), "status_contradiction")

    def test_text_naming_another_rule(self):
        self.assertFallback(answering(explanation="Under R999 this line is fine to ignore."), "unknown_rule")

    def test_ordinary_wording_is_not_a_contradiction(self):
        record, _ = explain(answering(explanation="R001: the authorization is not approved; "
                                                  "verify it before submission."))
        self.assertEqual(record["source"], "provider")

    def test_records_never_quote_a_rejected_answer(self):
        record, event = self.assertFallback(answering(explanation="LEAK-MARKER all checks passed"),
                                            "status_contradiction")
        self.assertNotIn("LEAK-MARKER", json.dumps([record, event]))

    def test_every_public_finding_passes_the_watchdog_with_the_mock(self):
        # A false alarm here would replace a correct explanation by a fallback.
        for split in ("development", "validation", "stress"):
            claims = {c["claim_id"]: c for c in jsonl(f"data/{split}/claims.jsonl")}
            _, events, summary = explain_run(jsonl(f"data/{split}/expected_results.jsonl"), claims, RULES,
                                             provider=MockProvider(), timeout=5.0)
            self.assertEqual(events, [], split)
            self.assertEqual(summary["failures"], {}, split)


class ExplainerTests(unittest.TestCase):
    def setUp(self):
        self.claims = {c["claim_id"]: c for c in jsonl("data/development/claims.jsonl")}
        self.results = jsonl("data/development/expected_results.jsonl")[:600]  # 40 claims

    def test_only_fail_and_unknown_are_explained_and_results_are_untouched(self):
        before = copy.deepcopy(self.results)
        records, _, summary = explain_run(self.results, self.claims, RULES, provider=MockProvider(), timeout=5.0)
        self.assertEqual(self.results, before)
        flagged = [r for r in self.results if r["status"] in ("FAIL", "UNABLE_TO_ASSESS")]
        self.assertEqual([(r["claim_id"], r["rule_id"]) for r in records],
                         [(r["claim_id"], r["rule_id"]) for r in flagged])
        self.assertEqual(summary["findings"], len(flagged))
        self.assertEqual(set(records[0]), {
            "claim_id", "rule_id", "status", "source", "provider", "model", "prompt_version", "latency_ms",
            "explanation", "cited_evidence_paths", "cited_rule_ids", "needs_human_review", "failure"})

    def test_flagged_claim_is_never_sent_to_the_model(self):
        rows = [r for r in jsonl("data/development/expected_results.jsonl") if r["claim_id"] == INJECTED]
        spy = Fake(good)
        records, events, summary = explain_run(rows, self.claims, RULES, provider=spy, timeout=5.0)
        self.assertEqual(spy.calls, 0)
        self.assertTrue(records)
        self.assertEqual({r["source"] for r in records}, {"skipped_flagged"})
        self.assertEqual((events, summary["flagged_claims"]), ([], 1))

    def test_model_failure_never_removes_a_finding(self):
        def down(f, r):
            raise ConnectionError("model unavailable")
        records, events, _ = explain_run(self.results, self.claims, RULES, provider=Fake(down), timeout=5.0)
        explained = [r for r in records if r["source"] != "skipped_flagged"]
        self.assertTrue(explained)
        self.assertEqual(len(events), len(explained))
        for r in explained:
            self.assertEqual(r["source"], "fallback")
            self.assertTrue(r["explanation"])

    def test_result_for_an_unknown_claim_is_an_error(self):
        row = dict(self.results[0], claim_id="CG-NOT-IN-FILE", status="FAIL")
        with self.assertRaises(ValueError):
            explain_run([row], self.claims, RULES, provider=MockProvider(), timeout=5.0)


class ProviderTests(unittest.TestCase):
    def test_no_key_uses_the_mock(self):
        provider, reason = select_provider({})
        self.assertEqual((provider.name, provider.model), ("mock", None))
        self.assertIn("no ANTHROPIC_API_KEY", reason)

    def test_a_key_is_never_echoed(self):
        provider, reason = select_provider({"ANTHROPIC_API_KEY": "sk-ant-SECRET"})
        self.assertEqual(provider.name, "mock")
        self.assertNotIn("SECRET", reason)

    def test_timeout_setting(self):
        self.assertEqual(timeout_from({}), 20.0)
        self.assertEqual(timeout_from({"CLAIMGUARD_AI_TIMEOUT_S": "5"}), 5.0)
        for bad in ("0", "-1", "301", "soon"):
            with self.assertRaises(ValueError, msg=bad):
                timeout_from({"CLAIMGUARD_AI_TIMEOUT_S": bad})


class CleanCheckoutTests(unittest.TestCase):
    def test_run_without_a_key_completes_with_the_mock_and_leaves_results_alone(self):
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with tempfile.TemporaryDirectory() as tmp:
            pred, expl, fail = (Path(tmp) / n for n in ("pred.jsonl", "expl.jsonl", "fail.jsonl"))
            subprocess.run([sys.executable, "src/run_baseline.py", "--input", "data/stress/claims.jsonl",
                            "--output", str(pred)], cwd=ROOT, env=env, check=True, capture_output=True)
            digest = hashlib.sha256(pred.read_bytes()).hexdigest()
            done = subprocess.run([sys.executable, "-m", "claimguard.ai", "--results", str(pred),
                                   "--claims", "data/stress/claims.jsonl", "--output", str(expl),
                                   "--events", str(fail)],
                                  cwd=ROOT, env=env, check=True, capture_output=True, text=True)
            summary = json.loads(done.stdout)
            self.assertEqual(summary["provider"], "mock")
            self.assertEqual(hashlib.sha256(pred.read_bytes()).hexdigest(), digest)
            flagged = [r for r in map(json.loads, pred.read_text(encoding="utf-8").splitlines())
                       if r["status"] in ("FAIL", "UNABLE_TO_ASSESS")]
            self.assertEqual(len(expl.read_text(encoding="utf-8").splitlines()), len(flagged))


class ExerciseTests(unittest.TestCase):
    def test_all_25_cases_run_with_the_mock(self):
        rows = exercises.run(MockProvider(), timeout=5.0)
        self.assertEqual(len(rows), 25)
        self.assertEqual([e for *_, e in rows if e], [])
        for case, record, _ in rows:
            self.assertEqual(record["cited_rule_ids"], [case["finding"]["rule_id"]])


if __name__ == "__main__":
    unittest.main()
