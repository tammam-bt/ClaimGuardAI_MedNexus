"""R003 | Coverage active on service date.

Ported from src/engine_core.py base_check (Block D); identical output on every
public claim (tests/test_baseline_ports.py). Start and end dates are inclusive.
"""
from claimguard._pack import empty, valid_date
from claimguard.engine.context import RuleContext
from claimguard.engine.findings import Findings, Verdict
from claimguard.engine.registry import rule


@rule("R003")
def check(ctx: RuleContext) -> Verdict:
    coverage = ctx.claim["coverage"]
    start, end = valid_date(coverage["start_date"]), valid_date(coverage["end_date"])
    f = Findings(ctx).cite(
        ctx.path("coverage", "status"), ctx.path("coverage", "start_date"), ctx.path("coverage", "end_date"),
    )
    if empty(coverage["status"]):
        f.unknown("coverage status")
    elif coverage["status"] != "active":
        f.fail("coverage status is not active")
    if not start or not end:
        f.unknown("coverage period")
    for i, line in ctx.lines():
        f.cite(ctx.path("lines", i, "service_date"))
        served = valid_date(line["service_date"])
        if not served:
            f.unknown("service date")
            continue
        if (start and served < start) or (end and served > end):
            f.fail("service outside coverage period", line_id=line["line_id"])
    return f.verdict("All service dates are within active coverage, including boundaries.")
