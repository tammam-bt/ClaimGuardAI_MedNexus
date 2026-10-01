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
"""
import argparse
import csv
import json
from pathlib import Path

from .minimize import load_prompt
from .provider import select_provider, timeout_from
from .watchdog import explain_safely

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "exercises" / "llm_explanation_cases.jsonl"
SCORECARD = ROOT / "exercises" / "llm_manual_scorecard.csv"


def run(provider=None, timeout=None):
    """[(case, explanation record, model_failure event or None)]"""
    provider = provider or select_provider()[0]
    timeout = timeout_from() if timeout is None else timeout
    _, prompt_version = load_prompt()
    with open(CASES, encoding="utf-8") as f:
        cases = [json.loads(x) for x in f if x.strip()]
    return [(case, *explain_safely(provider, case["finding"], case["rule"], prompt_version, timeout))
            for case in cases]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--outdir", default="outputs")
    a = p.parse_args(argv)

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
