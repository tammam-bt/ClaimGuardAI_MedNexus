"""Model-neutral seam. The mock is a template, not a real LLM."""
from typing import Protocol
class ExplanationProvider(Protocol):
    def explain(self, finding: dict, rule: dict) -> dict: ...
class MockExplanationProvider:
    def explain(self, finding, rule):
        return {"explanation": finding["explanation"], "cited_evidence_paths": [e["path"] for e in finding["evidence"]], "cited_rule_ids": [finding["rule_id"]], "needs_human_review": finding["requires_human_review"]}
def validate_explanation(output, finding):
    expected={"explanation","cited_evidence_paths","cited_rule_ids","needs_human_review"}
    if not isinstance(output,dict) or set(output)!=expected: raise ValueError("Invalid explanation keys")
    if not isinstance(output["explanation"],str) or not output["explanation"].strip(): raise ValueError("Explanation required")
    for k in ("cited_evidence_paths","cited_rule_ids"):
        if not isinstance(output[k],list) or any(not isinstance(x,str) for x in output[k]): raise ValueError("Citation list required")
    allowed={e["path"] for e in finding["evidence"]}
    if not output["cited_evidence_paths"] or not set(output["cited_evidence_paths"])<=allowed: raise ValueError("Missing or unknown evidence citation")
    if output["cited_rule_ids"]!=[finding["rule_id"]]: raise ValueError("Unknown rule citation")
    if output["needs_human_review"] is not finding["requires_human_review"]: raise ValueError("Review boundary changed")
    return output
