"""R001 | Required claim information.

Ported from src/engine_core.py base_check (Block D). Its output is identical
to the baseline's, field for field, on every public claim
(tests/test_baseline_ports.py). A known absence is FAIL, not UNABLE_TO_ASSESS.
"""
from claimguard._pack import empty
from claimguard.engine.context import RuleContext
from claimguard.engine.findings import Findings, Verdict
from claimguard.engine.registry import rule

CLAIM_FIELDS = ("invoice_number", "member_id", "diagnosis_code")
LINE_FIELDS = ("service_date", "service_code", "quantity", "unit_price", "net_amount")
PASS_EVIDENCE = ("/invoice_number", "/member_id", "/diagnosis_code", "/lines")


@rule("R001")
def check(ctx: RuleContext) -> Verdict:
    f = Findings(ctx)
    for field in CLAIM_FIELDS:
        if empty(ctx.claim[field]):
            f.fail(f"{field} is missing", ctx.path(field))
    for i, line in ctx.lines():
        for field in LINE_FIELDS:
            if empty(line[field]):
                f.fail(f"line {field} is missing", ctx.path("lines", i, field), line_id=line["line_id"])
    return f.verdict(
        "Required information is present.",
        message="Required information is missing.",
        fallback_evidence=PASS_EVIDENCE,
    )
