"""R002 | Service and submission chronology.

Every service_date must be on or before submission_date. Equality passes.
Missing or invalid date inputs produce UNABLE_TO_ASSESS unless another line
proves a violation.
"""
from claimguard._pack import empty, valid_date  
from claimguard.engine.context import RuleContext
from claimguard.engine.findings import Findings, Verdict
from claimguard.engine.registry import rule


@rule("R002")
def check(ctx: RuleContext) -> Verdict:
    f = Findings(ctx)

    submission_path = ctx.path("submission_date")
    f.cite(submission_path)
    submitted = valid_date(ctx.claim.get("submission_date"))
    if submitted is None:
        f.unknown("submission date")

    for i, line in ctx.lines():
        p = ctx.path("lines", i, "service_date")
        f.cite(p)
        d = valid_date(line["service_date"])
        if d is None:
            f.unknown("service date")
        elif submitted is not None and d > submitted:
            f.fail("service date after submission", p, line_id=line["line_id"])

    return f.verdict("All service dates are on or before submission.")