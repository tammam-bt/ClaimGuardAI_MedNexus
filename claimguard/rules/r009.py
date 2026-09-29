"""R009 | Authorization record matches service (docs/04_Rulebook.md).

Wordings the gold never shows: DEC-005. Aggregate quantity: DEC-006.
Dependency on R008 through the shared predicates in _auth.py: DEC-007.
"""
from decimal import Decimal, localcontext
from typing import Dict, List, Mapping

from claimguard._pack import valid_date
from claimguard.engine.context import RuleContext
from claimguard.engine.findings import Findings, Verdict
from claimguard.engine.registry import rule

from ._auth import REQUIRED, UNKNOWN, UNKNOWN_SERVICE_MESSAGE, missing_reference, requirement
from ._common import EXACT, NO_POLICY_MESSAGE, NOT_APPLICABLE_MESSAGE, PASS_MESSAGE, dec, is_number, missing


@rule("R009")
def check(ctx: RuleContext) -> Verdict:
    if ctx.policy is None:
        return Findings(ctx).unknown(NO_POLICY_MESSAGE, ctx.path("policy_id")).verdict(PASS_MESSAGE)

    records = ctx.claim["authorizations"]  # the complete list for this claim
    by_id: Dict[str, List[int]] = {}
    unreadable = False  # a non-object entry: validate_transport does not check items (DEC-012)
    for j, a in enumerate(records):
        if isinstance(a, Mapping):
            by_id.setdefault(a.get("authorization_id"), []).append(j)
        else:
            unreadable = True

    f = Findings(ctx, applicable=False)
    resolved: Dict[str, int] = {}  # authorization_id -> record index, in first-use order
    for i, line in ctx.lines():
        f.cite(ctx.path("lines", i, "service_code"), ctx.path("lines", i, "authorization_id"))
        need = requirement(ctx.policy, line)
        if need == UNKNOWN:
            f.unknown(UNKNOWN_SERVICE_MESSAGE)
            continue
        if need != REQUIRED:
            continue
        f.mark_applicable()
        if missing_reference(line):
            # R008 fails this line; R009 cannot inspect a record it has no ID for.
            f.unknown("Cannot inspect authorization without an ID")
            continue

        line_id, ref = line["line_id"], line["authorization_id"]
        base = (ctx.path("lines", i, "service_date"), ctx.path("lines"))
        matches = by_id.get(ref, [])
        if not matches and unreadable:
            # The unreadable entry may be this very record: absence is not proven.
            f.unknown("Authorization inventory unreadable", ctx.path("authorizations"), *base)
            continue
        if not matches:
            f.fail("Authorization record not found", *base, line_id=line_id)
            continue
        if len(matches) > 1:
            f.unknown("Authorization record ambiguous", *(ctx.path("authorizations", j) for j in matches), *base)
            continue

        j = matches[0]
        a, record = records[j], ctx.path("authorizations", j)
        f.cite(record)
        # Exact, case-sensitive comparisons; a null record field is an unknown, not a mismatch.
        if a.get("patient_id") is None or a.get("service_code") is None or a.get("status") is None:
            f.unknown("Authorization input missing")
        if a.get("patient_id") is not None and a["patient_id"] != ctx.claim["patient_id"]:
            f.fail("Authorization patient mismatch", ctx.path("patient_id"), f"{record}/patient_id", line_id=line_id)
        if a.get("service_code") is not None and a["service_code"] != line["service_code"]:
            f.fail("Authorization service mismatch", f"{record}/service_code", line_id=line_id)
        if a.get("status") is not None and a["status"] != "approved":
            f.fail("Authorization status mismatch", f"{record}/status", line_id=line_id)

        served, start, end = valid_date(line["service_date"]), valid_date(a.get("valid_from")), valid_date(a.get("valid_to"))
        if served is None or start is None or end is None:
            f.unknown("Authorization date input missing")
        elif not start <= served <= end:  # inclusive
            f.fail("Service date outside authorization validity", f"{record}/valid_from", f"{record}/valid_to", line_id=line_id)
        f.cite(*base)
        resolved.setdefault(ref, j)

    # Once per authorization, over every line that shares its reference (DEC-006).
    for ref, j in resolved.items():
        sharing = [line for _, line in ctx.lines() if line["authorization_id"] == ref]
        limit = records[j].get("max_quantity")
        quantities = [line["quantity"] for line in sharing]
        if any(missing(q) or not is_number(q) for q in quantities + [limit]):
            f.unknown("Authorization quantity input missing")
            continue
        with localcontext(EXACT):  # 28 digits could round an excess away (DEC-012)
            exceeds = sum((dec(q) for q in quantities), Decimal(0)) > dec(limit)
        if exceeds:
            for line in sharing:
                f.fail("Aggregate quantity exceeds authorization", line_id=line["line_id"])
    return f.verdict(PASS_MESSAGE, not_applicable_message=NOT_APPLICABLE_MESSAGE)
