"""R010 | Required supporting document (docs/04_Rulebook.md)."""
from typing import Any, Iterable, Mapping

from claimguard._pack import valid_date
from claimguard.engine.context import RuleContext
from claimguard.engine.findings import Findings, Verdict
from claimguard.engine.registry import rule

from ._common import NO_POLICY_MESSAGE, NOT_APPLICABLE_MESSAGE, PASS_MESSAGE, unknown_service

FINAL, UNCERTAIN, ABSENT = "final", "uncertain", "absent"


def _document(attachments: Iterable[Mapping[str, Any]], wanted: Mapping[str, Any]) -> str:
    """Best evidence among the attachments for one line (DEC-008).

    Each attachment is compared on the four fields. A field that differs
    rules the attachment out; a null field is an unknown comparison, so the
    attachment might match. FINAL needs all four fields equal and status
    exactly "final". Otherwise any possible or non-final match is UNCERTAIN,
    and no candidate at all is ABSENT. The text field is never read: it is
    untrusted content that cannot change the outcome.
    """
    uncertain = False
    for a in attachments:
        # .get: validate_transport does not check attachment keys.
        observed = {k: a.get(k) for k in wanted}
        observed["service_date"] = valid_date(observed["service_date"])  # day precision
        if any(v is not None and v != wanted[k] for k, v in observed.items()):
            continue
        if None not in observed.values() and a.get("document_status") == "final":
            return FINAL
        uncertain = True
    return UNCERTAIN if uncertain else ABSENT


@rule("R010")
def check(ctx: RuleContext) -> Verdict:
    if ctx.policy is None:
        return Findings(ctx).unknown(NO_POLICY_MESSAGE, ctx.path("policy_id")).verdict(PASS_MESSAGE)

    required = ctx.policy["required_documents"]
    # A non-object entry is unreadable (validate_transport does not check items) and
    # may be the very document looked for, so it can never prove absence (DEC-012).
    readable = [a for a in ctx.claim["attachments"] if isinstance(a, Mapping)]
    unreadable = len(readable) != len(ctx.claim["attachments"])
    f = Findings(ctx, applicable=False)
    f.cite(ctx.path("attachments"))  # a complete inventory: [] means no documents supplied
    for i, line in ctx.lines():
        code = line["service_code"]
        f.cite(ctx.path("lines", i, "service_code"))
        if code in required:
            f.mark_applicable()
            f.cite(ctx.path("lines", i, "service_date"))
            served = valid_date(line["service_date"])
            if served is None:
                f.unknown("Service date required to match document")
                continue
            wanted = {"type": required[code], "patient_id": ctx.claim["patient_id"],
                      "service_code": code, "service_date": served}
            found = _document(readable, wanted)
            if found == ABSENT and unreadable:
                f.unknown("Attachment inventory unreadable")
            elif found == ABSENT:
                f.fail("Matching required document absent", line_id=line["line_id"])
            elif found == UNCERTAIN:
                f.unknown("Only draft or uncertain matching documentation")
        elif unknown_service(ctx.policy, code):
            f.unknown("Unknown service prevents document requirement lookup")
    return f.verdict(PASS_MESSAGE, not_applicable_message=NOT_APPLICABLE_MESSAGE)
