"""Apply downloaded decisions in one step: append them, judge every claim,
rebuild the page (M9).

    python -m claimguard.ui.apply --decisions review_decisions_d8c76c1c.jsonl \\
        --log outputs/audit.jsonl --directory actors.json \\
        --results outputs/dev_predictions.jsonl --claims data/development/claims.jsonl \\
        [--corrections outputs/corrections] [--gold data/development/expected_results.jsonl]

The same three steps, with the same checks and the same result, as running
in order

    python -m claimguard.ui.decisions ...   append, after checking every decision
    python -m claimguard.review.gate ...    judge what may proceed
    python -m claimguard.ui ...             rebuild the page

except that the append_performed event names this command. With
--expect-count and --expect-head, the log is checked against the head
recorded outside this machine before anything is appended. It ends with the
count and head to record outside.

Exit code 0: every claim is ready. 1: some are blocked, as the gate says.
2: stopped, and the page was not rebuilt: a decision was refused (nothing
appended), or the chain or the run's files cannot be trusted.
"""
import argparse
from pathlib import Path

from claimguard.audit import chain
from claimguard.guards.rbac import load_directory
from claimguard.review.gate import GateError, judge, verdict, write_rows
from claimguard.ui.bundle import build
from claimguard.ui.decisions import append_decisions
from claimguard.ui.page import render

COMMAND = "claimguard.ui.apply"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--decisions", required=True, help="the file downloaded from the interface")
    p.add_argument("--log", required=True, help="the run's audit log")
    p.add_argument("--anchor", help="chain-head anchor (default: beside the log)")
    p.add_argument("--directory", required=True, help="JSON {actor: role}, e.g. actors.example.json")
    p.add_argument("--claims", required=True, help="the claims file the run read")
    p.add_argument("--results", required=True, help="the run's results")
    p.add_argument("--corrections", help="folder written by python -m claimguard.review.correct")
    p.add_argument("--gold", help="expected results, for the evaluation page")
    p.add_argument("--output", default="outputs/claimguard.html", help="the page to rebuild")
    p.add_argument("--gate-output", help="also write the gate's row per claim to this file")
    chain.add_expect_arguments(p)
    a = p.parse_args(argv)
    expect = chain.expected(p, a)
    anchor = a.anchor or chain.default_anchor(a.log)
    try:
        directory = load_directory(a.directory)
        if expect:
            chain.verify(a.log, anchor, expect)
        summary = append_decisions(a.decisions, a.log, anchor=anchor, directory=directory, claims_path=a.claims,
                                   results_path=a.results, corrections=a.corrections, command=COMMAND)
    except (ValueError, chain.AuditError) as e:  # AuditError is a ValueError
        print(f"Nothing appended: {e}")
        if isinstance(e, chain.MissingAnchor):
            print(chain.RESTORE_HINT)
        return 2
    print(f"{summary['appended']} decision(s) appended, {summary['already_in_chain']} already in the audit log.")
    try:
        rows = judge(a.results, a.claims, a.log, directory, anchor=anchor, corrections=a.corrections, expect=expect)
    except (GateError, ValueError) as e:
        print(f"Gate cannot judge, so the page was not rebuilt: {e}")
        return 2
    if a.gate_output:
        write_rows(a.gate_output, rows)
    print(verdict(rows))
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(build(a.results, a.claims, audit_log=a.log, gold_path=a.gold, corrections=a.corrections,
                                anchor=anchor)), encoding="utf-8")
    print(f"Page rebuilt: {out}")
    if summary["events_in_chain"]:
        print(chain.record_hint(summary["events_in_chain"], summary["head"]))
    return 1 if any(not r["ready"] for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
