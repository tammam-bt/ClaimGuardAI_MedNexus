"""R006 | Possible duplicate service lines.

Ported from src/engine_core.py base_check (Block D); identical output on every
public claim (tests/test_baseline_ports.py). Repeated (service_code,
service_date, modifier) within one claim; a null modifier counts as "".
FAIL means a possible duplicate for human review, never fraud.
"""
from claimguard._pack import empty, valid_date
from claimguard.engine.context import RuleContext
from claimguard.engine.findings import Findings, Verdict
from claimguard.engine.registry import rule

KEY_FIELDS = ("service_code", "service_date", "modifier")


@rule("R006")
def check(ctx: RuleContext) -> Verdict:
    f = Findings(ctx)
    seen, duplicates, missing = {}, [], False
    for i, line in ctx.lines():
        if empty(line["service_code"]) or not valid_date(line["service_date"]):
            missing = True
            continue
        key = (line["service_code"], line["service_date"], line["modifier"] or "")
        if key in seen:
            duplicates.extend([seen[key], i])
        else:
            seen[key] = i
    for i in sorted(set(duplicates)):
        f.fail(
            "possible duplicate line",
            *(ctx.path("lines", i, k) for k in KEY_FIELDS),
            line_id=ctx.claim["lines"][i]["line_id"],
        )
    if missing:
        f.unknown("missing inputs")
    if duplicates:
        text = "Possible duplicate lines require review." + (" Additional lines have missing inputs." if missing else "")
    else:
        text = "Missing inputs prevent a complete duplicate check."
    return f.verdict(
        "No duplicate service/date/modifier combinations.",
        message=text,
        fallback_evidence=("/lines",),
    )
