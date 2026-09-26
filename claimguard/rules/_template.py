"""Copy this file to rNNN.py to implement a rule. It is never registered:
modules whose names start with an underscore are skipped by discovery.

Checklist before you open the PR:
  [ ] tests in tests/test_rNNN.py cover a PASS, a FAIL and an UNABLE_TO_ASSESS
      (and NOT_APPLICABLE if the rule can be not applicable)
  [ ] boundaries tested: inclusive dates, the inclusive 0.01 SAR tolerance
  [ ] EDU-NO-POLICY claims give UNABLE_TO_ASSESS if the rule reads policy
  [ ] nothing reads expected_results.jsonl
  [ ] no date.today() / datetime.now()
  [ ] per-rule accuracy from evaluate.py pasted in the PR description
"""
from claimguard._pack import empty, money, valid_date  # noqa: F401
from claimguard.engine.context import RuleContext
from claimguard.engine.findings import Findings, Verdict
from claimguard.engine.registry import rule


# @rule("RNNN")            <- uncomment in your copy, with your rule ID
def check(ctx: RuleContext) -> Verdict:
    f = Findings(ctx)                      # Findings(ctx, applicable=False) for R008-R010

    # 1. If the rule needs policy and there is none, say so and stop looking.
    #    if ctx.policy is None:
    #        return f.unknown("no matching policy supplied", ctx.path("policy_id")) \
    #                .verdict("unused")

    # 2. Inspect the claim. Cite what you look at. Record what you find.
    #    for i, line in ctx.lines():
    #        p = ctx.path("lines", i, "service_code")
    #        f.cite(p)
    #        if empty(line["service_code"]):
    #            f.unknown("service code")
    #        elif <violation>:
    #            f.fail("<short reason>", p, line_id=line["line_id"])

    # 3. Let Findings decide the status, message and evidence.
    return f.verdict("<what a PASS means for this rule>")
