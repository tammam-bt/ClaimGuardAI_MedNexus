"""Copy this file to rNNN.py to implement a rule. It is never registered:
modules whose names start with an underscore are skipped by discovery.

Checklist before you open the PR:
  [ ] tests in tests/test_rNNN.py cover a PASS, a FAIL and an UNABLE_TO_ASSESS
      (and NOT_APPLICABLE if the rule can be not applicable)
  [ ] boundaries tested: inclusive dates, the inclusive 0.01 SAR tolerance
  [ ] no policy -> UNABLE_TO_ASSESS, unless a policy-free check proves a FAIL
  [ ] nothing reads expected_results.jsonl
  [ ] never reads the current date or time; use the claim's own dates
  [ ] per-rule accuracy from evaluate.py pasted in the PR description
"""
from claimguard._pack import empty, money, valid_date  # noqa: F401
from claimguard.engine.context import RuleContext
from claimguard.engine.findings import Findings, Verdict
from claimguard.engine.registry import rule


# @rule("RNNN")            <- uncomment in your copy, with your rule ID
def check(ctx: RuleContext) -> Verdict:
    f = Findings(ctx)                      # Findings(ctx, applicable=False) for R008-R010

    # 1. A missing policy is an unknown, not a reason to stop. Record it and
    #    keep checking anything that does not need the policy: the rulebook
    #    says "unless another line proves a violation". Example: R013 can
    #    still FAIL a negative quantity when no policy was supplied.
    #    if ctx.policy is None:
    #        f.unknown("no matching policy supplied", ctx.path("policy_id"))

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
