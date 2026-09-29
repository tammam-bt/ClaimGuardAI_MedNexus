"""R014 | Submission window (docs/04_Rulebook.md)."""
from claimguard._pack import valid_date
from claimguard.engine.context import RuleContext
from claimguard.engine.findings import Findings, Verdict
from claimguard.engine.registry import rule

from ._common import NO_POLICY_MESSAGE, NOT_APPLICABLE_MESSAGE, PASS_MESSAGE


@rule("R014")
def check(ctx: RuleContext) -> Verdict:
    if ctx.policy is None:
        # Without a window nothing can be proven; the gold cites only /policy_id (DEC-009).
        return Findings(ctx).unknown(NO_POLICY_MESSAGE, ctx.path("policy_id")).verdict(PASS_MESSAGE)

    # Not applicable until the lag is known to be non-negative: a negative lag is R002's.
    f = Findings(ctx, applicable=False)
    f.cite(ctx.path("submission_date"), ctx.path("policy_id"))
    submitted = valid_date(ctx.claim["submission_date"])
    dates = []
    for i, line in ctx.lines():
        f.cite(ctx.path("lines", i, "service_date"))
        dates.append(valid_date(line["service_date"]))

    # Any missing date leaves the latest service date unknown, so even a known
    # date far outside the window proves nothing (DEC-009). No "unless" clause here.
    if submitted is None or None in dates:
        f.unknown("Date missing")
    else:
        lag = (submitted - max(dates)).days
        if lag >= 0:
            f.mark_applicable()
            # Equality passes.
            if lag > ctx.policy["submission_window_days"]:
                f.fail("Submission exceeds fictional window")  # claim-level: no line_id
    return f.verdict(PASS_MESSAGE, not_applicable_message=NOT_APPLICABLE_MESSAGE)
