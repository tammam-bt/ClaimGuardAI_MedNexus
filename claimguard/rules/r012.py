"""R012 | Claim total equals line amounts (docs/04_Rulebook.md)."""
from decimal import Decimal, localcontext

from claimguard._pack import money
from claimguard.engine.context import RuleContext
from claimguard.engine.findings import Findings, Verdict
from claimguard.engine.registry import rule

from ._common import EXACT, PASS_MESSAGE, TOLERANCE, dec, missing


@rule("R012")
def check(ctx: RuleContext) -> Verdict:
    f = Findings(ctx)
    total = ctx.claim["total_amount"]
    f.cite(ctx.path("total_amount"))
    nets = []
    for i, line in ctx.lines():
        f.cite(ctx.path("lines", i, "net_amount"))
        nets.append(line["net_amount"])
    if missing(total) or any(missing(n) for n in nets):
        f.unknown("Amount input missing")
        return f.verdict(PASS_MESSAGE)
    # Sums the SUBMITTED net_amount values; whether those are correct is R007's question.
    with localcontext(EXACT):  # exact at any magnitude: 28 digits would round the sum (DEC-012)
        differs = abs(dec(total) - money(sum((dec(n) for n in nets), Decimal(0)))) > TOLERANCE
    if differs:
        # Claim-level defect: no line_id, matching the gold labels.
        f.fail("Claim total differs from submitted line amounts")
    return f.verdict(PASS_MESSAGE)
