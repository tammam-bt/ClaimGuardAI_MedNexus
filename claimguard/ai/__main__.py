"""Explain the flagged results of a run.

    python -m claimguard.ai --results outputs/dev_predictions.jsonl \\
        --claims data/development/claims.jsonl

Writes outputs/explanations.jsonl (one record per FAIL or UNABLE_TO_ASSESS
result) and outputs/model_failures.jsonl (one event per fallback), and prints
the AI part of the run manifest. The results file is only read.
"""
import argparse
import json
from pathlib import Path

from claimguard._pack import config, load_jsonl

from .explainer import explain_run

ROOT = Path(__file__).resolve().parents[2]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--results", required=True)
    p.add_argument("--claims", required=True)
    p.add_argument("--output", default="outputs/explanations.jsonl")
    p.add_argument("--events", default="outputs/model_failures.jsonl")
    a = p.parse_args(argv)

    claims = {c["claim_id"]: c for c in load_jsonl(a.claims)}
    rules = {r["rule_id"]: r for r in config(ROOT)["rules"]}
    records, events, summary = explain_run(load_jsonl(a.results), claims, rules)
    for path, rows in ((a.output, records), (a.events, events)):
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
