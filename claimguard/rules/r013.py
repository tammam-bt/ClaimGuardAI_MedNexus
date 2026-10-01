"""R013 | Quantity and price limits (docs/04_Rulebook.md)."""
from typing import Any

from claimguard.engine.context import RuleContext
from claimguard.engine.findings import Findings, Verdict
from claimguard.engine.registry import rule

from ._common import NO_POLICY_MESSAGE, PASS_MESSAGE, dec, is_number, missing


def positive_integer(q: Any) -> bool:
    """DEC-001: 2.0 counts as an integer value, as csv_to_jsonl.number() does. DEC-002: bool is not a number."""
    return is_number(q) and q > 0 and dec(q) == dec(q).to_integral_value()


@rule("R013")
def check(ctx: RuleContext) -> Verdict:
    f = Findings(ctx)
    policy = ctx.policy
    for i, line in ctx.lines():
        f.cite(*(ctx.path("lines", i, k) for k in ("quantity", "unit_price", "service_code")))
        q, p, code, line_id = line["quantity"], line["unit_price"], line["service_code"], line["line_id"]
        # These two checks need no policy, so they can prove a violation even when the policy is unknown.
        q_known, p_known = not missing(q), not missing(p)
        if q_known and not positive_integer(q):
            f.fail("Quantity must be a positive integer", line_id=line_id)
        if p_known and (not is_number(p) or dec(p) <= 0):
            f.fail("Unit price must be greater than zero", line_id=line_id)
        if not (q_known and p_known):
            f.unknown("Quantity or price missing")
        if policy is None:
            continue
        if code not in policy["max_unit_price"] or code not in policy["max_quantity_per_line"]:
            f.unknown("Unknown service limits")
            continue
        # Equality at the maximum passes.
        if p_known and is_number(p) and dec(p) > dec(policy["max_unit_price"][code]):
            f.fail("Price exceeds fictional maximum", line_id=line_id)
        if q_known and is_number(q) and dec(q) > dec(policy["max_quantity_per_line"][code]):
            f.fail("Quantity exceeds fictional maximum", line_id=line_id)
    if policy is None:
        if not f.failures:
            # With no policy and no proven violation, the gold result cites only /policy_id.
            return Findings(ctx).unknown(NO_POLICY_MESSAGE, ctx.path("policy_id")).verdict(PASS_MESSAGE)
        f.unknown("policy", ctx.path("policy_id"))
    return f.verdict(PASS_MESSAGE)
