"""R015 | Currency matches policy.

currency must equal policy.currency (SAR). A known different currency fails.
Missing currency or unavailable policy leaves UNABLE_TO_ASSESS. No
exchange-rate conversion is performed.
"""
from claimguard._pack import empty
from claimguard.engine.context import RuleContext
from claimguard.engine.findings import Findings, Verdict
from claimguard.engine.registry import rule

NO_POLICY_MESSAGE = "No policy is supplied for this policy_id."


@rule("R015")
def check(ctx: RuleContext) -> Verdict:
    f = Findings(ctx)
    f.cite(ctx.path("policy_id"))

    if ctx.policy is None:
        f.unknown("no matching policy supplied")
        return f.verdict(
            "Currency matches the applicable policy.",
            message=NO_POLICY_MESSAGE,
        )

    p = ctx.path("currency")
    f.cite(p)
    currency = ctx.claim["currency"]
    if empty(currency):
        f.unknown("currency")
    elif currency != ctx.policy["currency"]:
        f.fail("currency does not match policy currency", p)

    return f.verdict("Currency matches the applicable policy.")