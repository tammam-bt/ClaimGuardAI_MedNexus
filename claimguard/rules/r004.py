"""R004 | Member and beneficiary consistency.

patient_id must equal coverage.beneficiary_patient_id and member_id must equal
coverage.member_id, as exact case-sensitive identifiers. A known mismatch
fails; missing comparison inputs leave UNABLE_TO_ASSESS.
"""
from claimguard._pack import empty, money
from claimguard.engine.context import RuleContext
from claimguard.engine.findings import Findings, Verdict
from claimguard.engine.registry import rule


@rule("R004")
def check(ctx: RuleContext) -> Verdict:
    f = Findings(ctx)

    patient_id = ctx.claim["patient_id"]
    beneficiary_id = ctx.claim["coverage"]["beneficiary_patient_id"]
    p1 = ctx.path("patient_id")
    p2 = ctx.path("coverage", "beneficiary_patient_id")
    f.cite(p1, p2)
    if empty(patient_id) or empty(beneficiary_id):
        f.unknown("patient/beneficiary identifier")
    elif patient_id != beneficiary_id:
        f.fail("patient ID does not match coverage beneficiary", p1, p2)

    member_id = ctx.claim["member_id"]
    coverage_member_id = ctx.claim["coverage"]["member_id"]
    p3 = ctx.path("member_id")
    p4 = ctx.path("coverage", "member_id")
    f.cite(p3, p4)
    if empty(member_id) or empty(coverage_member_id):
        f.unknown("member identifier")
    elif member_id != coverage_member_id:
        f.fail("member ID does not match coverage record", p3, p4)

    return f.verdict("Patient and member identifiers match coverage records.")