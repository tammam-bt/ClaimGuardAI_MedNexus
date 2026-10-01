"""Build the review interface for one run.

    python -m claimguard.run --input data/development/claims.jsonl \\
        --output outputs/dev_predictions.jsonl --explain --audit-log outputs/audit.jsonl
    python -m claimguard.ui --results outputs/dev_predictions.jsonl \\
        --claims data/development/claims.jsonl --audit-log outputs/audit.jsonl \\
        --gold data/development/expected_results.jsonl

Writes outputs/claimguard.html: open it in a browser, offline. The manifest
and explanations are found beside --results, as claimguard.run writes them.
--audit-log adds the audit page; --gold adds the evaluation page.
"""
import argparse
import json
from pathlib import Path

from .bundle import build
from .page import render


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--results", required=True, help="the run's --output file")
    p.add_argument("--claims", required=True, help="the claims file the run read")
    p.add_argument("--audit-log", help="the run's hash-chained audit log")
    p.add_argument("--gold", help="expected results, for the evaluation page")
    p.add_argument("--corrections", help="folder written by python -m claimguard.review.correct")
    p.add_argument("--output", default="outputs/claimguard.html")
    a = p.parse_args(argv)

    data = build(a.results, a.claims, audit_log=a.audit_log, gold_path=a.gold, corrections=a.corrections)
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data), encoding="utf-8")
    print(json.dumps({
        "output": str(out),
        "claims": len(data["claims"]),
        "rejected": len(data["rejected"]),
        "audit_events": len(data["audit"]["events"]) if data["audit"] else None,
        "audit_valid": data["audit"]["valid"] if data["audit"] else None,
        "evaluation": data["evaluation"] is not None,
        "versions": sum(len(c["versions"]) for c in data["claims"]),
        "corrections_skipped": len(data["corrections_skipped"]),
        "bytes": out.stat().st_size,
    }, indent=2))


if __name__ == "__main__":
    main()
