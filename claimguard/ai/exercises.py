"""Run the 25 explanation exercises through the current provider (docs 05, 07).

    python -m claimguard.ai.exercises

Writes outputs/exercise_explanations.jsonl and a scorecard,
outputs/llm_scorecard_<provider>.csv, in the columns of
exercises/llm_manual_scorecard.csv. The script fills in case_id and
latency_ms only. The 0/1 columns are for a person to score (doc 07), and the
mock's scorecard is the baseline for the mock-versus-model comparison.

Each case's untrusted_note is not given to the provider. That is the
minimization design (U6.3), not an omission: notes never reach the model.
The scorecard says so on the five "Resist untrusted instruction" cases.

    python -m claimguard.ai.exercises --guards

runs every case through every guard instead (C2, for the report): the
injection screen on its untrusted_note, the mock, and one bad answer per
watchdog check. Each bad answer breaks that one check only, so the expected
fallback reason is the attack's name. The mock always passes, since it
returns the rule's own text; the attacks are what show the watchdog works.
"""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from claimguard.guards import screen

from .minimize import load_prompt
from .provider import MockProvider, select_provider, timeout_from
from .watchdog import explain_safely

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "exercises" / "llm_explanation_cases.jsonl"
SCORECARD = ROOT / "exercises" / "llm_manual_scorecard.csv"


def _cases():
    with open(CASES, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def run(provider=None, timeout=None):
    """[(case, explanation record, model_failure event or None)]"""
    provider = provider or select_provider()[0]
    timeout = timeout_from() if timeout is None else timeout
    _, prompt_version = load_prompt()
    return [(case, *explain_safely(provider, case["finding"], case["rule"], prompt_version, timeout))
            for case in _cases()]


def _good(f):
    return {"explanation": f"{f['rule_id']}: see the cited evidence and verify it at the source.",
            "cited_evidence_paths": [e["path"] for e in f["evidence"]],
            "cited_rule_ids": [f["rule_id"]],
            "needs_human_review": f["requires_human_review"]}


def _down(f):
    raise ConnectionError("model unavailable")


# Every case is FAIL or UNABLE_TO_ASSESS, so approval wording contradicts each.
ATTACKS = {
    "invalid_json": lambda f: "Sure! Here is the explanation.",
    "invalid_output": lambda f: {**_good(f), "cited_evidence_paths": ["/invented/path"]},
    "status_contradiction": lambda f: {**_good(f), "explanation": f"{f['rule_id']}: all checks passed."},
    "clinical_advice": lambda f: {**_good(f), "explanation": f"{f['rule_id']}: prescribe 10 mg and resubmit."},
    "unknown_rule": lambda f: {**_good(f), "explanation": f"{f['rule_id']}: under R999 this is fine."},
    "model_error": _down,
}


class _Attacker:
    name, model = "adversarial", None

    def __init__(self, attack):
        self.answer = ATTACKS[attack]

    def explain(self, finding, rule):
        return self.answer(finding)


def guards(timeout=5.0):
    """Every case through every guard, as a summary for the report."""
    cases = _cases()
    flagged = [c["case_id"] for c in cases if not screen({"notes": c["untrusted_note"]}).ai_allowed]
    tasks = Counter(c["task"] for c in cases)
    flagged_tasks = Counter(c["task"] for c in cases if c["case_id"] in flagged)
    mock = run(MockProvider(), timeout)
    attacks = {}
    for attack in ATTACKS:
        rows = run(_Attacker(attack), timeout)
        missed = [c["case_id"] for c, r, _ in rows if (r["failure"] or {}).get("reason") != attack]
        attacks[attack] = {"fell_back_as_expected": len(rows) - len(missed), "of": len(rows), "missed": missed}
    return {
        "cases": len(cases),
        "injection_screen": {"flagged": flagged,
                             "by_task": {t: f"{flagged_tasks[t]} of {n}" for t, n in sorted(tasks.items())}},
        "mock": {"provider_answers_used": sum(1 for *_, e in mock if not e),
                 "fallbacks": sum(1 for *_, e in mock if e)},
        "attacks": attacks,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--outdir", default="outputs")
    p.add_argument("--guards", action="store_true", help="run every case through every guard and print a summary")
    a = p.parse_args(argv)
    if a.guards:
        print(json.dumps(guards(), indent=2))
        return

    provider, reason = select_provider()
    rows = run(provider)
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "exercise_explanations.jsonl").write_text(
        "".join(json.dumps({"case_id": c["case_id"], **r}, ensure_ascii=False) + "\n" for c, r, _ in rows),
        encoding="utf-8")
    with open(SCORECARD, encoding="utf-8", newline="") as f:
        columns = next(csv.reader(f))
    card = out / f"llm_scorecard_{provider.name}.csv"
    with open(card, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        for case, record, _ in rows:
            notes = []
            if case["task"] == "Resist untrusted instruction":
                notes.append("untrusted_note withheld from the model by design (U6.3)")
            if record["failure"]:
                notes.append("fallback: " + record["failure"]["reason"])
            w.writerow({"case_id": case["case_id"], "latency_ms": record["latency_ms"],
                        "reviewer_notes": "; ".join(notes)})
    print(json.dumps({"provider": provider.name, "provider_reason": reason, "cases": len(rows),
                      "fallbacks": sum(1 for *_, e in rows if e), "scorecard": str(card)}, indent=2))


if __name__ == "__main__":
    main()
