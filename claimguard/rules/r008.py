"""R008 | Required authorization reference (docs/04_Rulebook.md)."""
from claimguard.engine.context import RuleContext
from claimguard.engine.findings import Findings, Verdict
from claimguard.engine.registry import rule

from ._auth import REQUIRED, UNKNOWN, UNKNOWN_SERVICE_MESSAGE, missing_reference, requirement
from ._common import NO_POLICY_MESSAGE, NOT_APPLICABLE_MESSAGE, PASS_MESSAGE


@rule("R008")
def check(ctx: RuleContext) -> Verdict:
    if ctx.policy is None:
        # Which services need authorization is policy data: without it nothing
        # can be proven, and the gold cites only /policy_id.
        return Findings(ctx).unknown(NO_POLICY_MESSAGE, ctx.path("policy_id")).verdict(PASS_MESSAGE)

    f = Findings(ctx, applicable=False)
    for i, line in ctx.lines():
        f.cite(ctx.path("lines", i, "service_code"), ctx.path("lines", i, "authorization_id"))
        need = requirement(ctx.policy, line)
        if need == REQUIRED:
            f.mark_applicable()
            # Presence only; whether the reference resolves is R009's question.
            if missing_reference(line):
                f.fail("Required authorization ID missing", line_id=line["line_id"])
        elif need == UNKNOWN:
            f.unknown(UNKNOWN_SERVICE_MESSAGE)
    return f.verdict(PASS_MESSAGE, not_applicable_message=NOT_APPLICABLE_MESSAGE)
