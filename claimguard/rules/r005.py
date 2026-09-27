"""R005 | Provider in the supplied network."""
from claimguard._pack import empty, money
from claimguard.engine.context import RuleContext
from claimguard.engine.findings import Findings, Verdict
from claimguard.engine.registry import rule

NO_POLICY_MESSAGE = "No policy is supplied for this policy_id."


@rule("R005")
def check(ctx: RuleContext) -> Verdict:
    f = Findings(ctx)
    f.cite(ctx.path("policy_id"))

    if ctx.policy is None:
        f.unknown("no matching policy supplied")
        return f.verdict(
            "Provider is listed in the applicable network.",
            message=NO_POLICY_MESSAGE,
        )

    p = ctx.path("provider_id")
    f.cite(p)
    provider_id = ctx.claim["provider_id"]
    if empty(provider_id):
        f.unknown("provider identifier")
    elif provider_id not in ctx.policy["allowed_providers"]:
        f.fail("provider absent from supplied network", p)

    return f.verdict("Provider is listed in the applicable network.")