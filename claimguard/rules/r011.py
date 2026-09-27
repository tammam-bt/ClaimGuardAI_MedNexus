"""R011 | Service code in fictional catalogue.

Each nonempty service_code must occur in rules/services.json. An unknown code
fails; a missing code leaves UNABLE_TO_ASSESS. No real CPT/ICD coding
decisions are implied.
"""
from claimguard._pack import empty, money, valid_date  # noqa: F401
from claimguard.engine.context import RuleContext
from claimguard.engine.findings import Findings, Verdict
from claimguard.engine.registry import rule


@rule("R011")
def check(ctx: RuleContext) -> Verdict:
    f = Findings(ctx)

    for i, line in ctx.lines():
        p = ctx.path("lines", i, "service_code")
        f.cite(p)
        code = line["service_code"]
        if empty(code):
            f.unknown("service code")
        elif code not in ctx.services:
            f.fail("service code not in catalogue", p, line_id=line["line_id"])

    return f.verdict("All service codes are in the fictional catalogue.")