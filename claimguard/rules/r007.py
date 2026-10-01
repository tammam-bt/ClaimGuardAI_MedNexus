"""R007 | Line arithmetic (docs/04_Rulebook.md)."""
from decimal import localcontext

from claimguard._pack import money
from claimguard.engine.context import RuleContext
from claimguard.engine.findings import Findings, Verdict
from claimguard.engine.registry import rule

from ._common import EXACT, PASS_MESSAGE, TOLERANCE, dec, missing


@rule("R007")
def check(ctx: RuleContext) -> Verdict:
    f = Findings(ctx)
    for i, line in ctx.lines():
        f.cite(*(ctx.path("lines", i, k) for k in ("quantity", "unit_price", "net_amount")))
        q, p, n = line["quantity"], line["unit_price"], line["net_amount"]
        if missing(q) or missing(p) or missing(n):
            f.unknown("arithmetic input")
            continue
        # Round the exact product, not the factors: money(q) * money(p) would round too early.
        # Negative or zero inputs are only checked arithmetically here; R013 judges their validity.
        with localcontext(EXACT):  # exact at any magnitude (DEC-012)
            differs = abs(dec(n) - money(dec(q) * dec(p))) > TOLERANCE
        if differs:
            f.fail("Line amount differs from quantity times price", line_id=line["line_id"])
    # A FAIL keeps "arithmetic input" as an additional unknown; on its own the gold wording differs.
    return f.verdict(PASS_MESSAGE, message=None if f.failures else "Arithmetic input missing")
