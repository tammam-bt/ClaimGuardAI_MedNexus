"""Watchdog and fallback (U3.7): a model answer is used only if it is safe.

prompts/explain_findings.md: "fall back to the deterministic explanation on
invalid JSON, unknown citations, timeout or model failure." Docs 07 and 10:
a model failure cannot remove a deterministic finding, and invalid output
never enters the authoritative results.

Each call ends in exactly one of these:

  ok                    the answer passed every check below
  timeout               no answer within the timeout
  model_error           the provider raised
  invalid_json          the answer is text that is not one JSON object
  invalid_output        validate_explanation() refused it: wrong keys, empty
                        explanation, unknown or missing evidence citation,
                        rule ID other than the finding's, or a changed
                        needs_human_review
  status_contradiction  the text presents a FAIL or UNABLE_TO_ASSESS finding
                        as passed or approved
  clinical_advice       the text gives clinical advice or judgment: prescribing,
                        a dose, administering a drug, surgery, stopping a
                        medication, or medical necessity (doc 05: the model
                        must not "infer clinical necessity")
  unknown_rule          the text names a rule ID other than the finding's

The model's output has no status field, so it cannot change a status. Its
text is the only place it could contradict the rule or step outside billing,
which is what the last three checks look at. They are heuristics: they catch
the plain forms, not every paraphrase. The clinical check runs on the text
normalized as the injection pre-filter does (NFKC, zero-width characters and
lookalikes), so a zero-width space inside "prescribe" or full-width letters
do not slip past.

The clinical check leaves out words the rules and reference data use for
billing: diagnosis, procedure, therapy (SVC-THERAPY), clinic, clinical,
unit and quantity. "units" counts only with a schedule or a drug ("units
daily", "units of insulin"), since "billed 5 units, maximum 2" is a correct
R013 explanation. It is not negation-aware: "this check does not assess
medical necessity" also falls back. That is deliberate; a fallback only
costs wording, never a finding.

On anything but ok, the explanation is the rule engine's own, with every
evidence path cited, and a model_failure event records why. Neither the
explanation record nor the event quotes the model's output.
"""
import json
import re
import threading
import time

from claimguard._pack import validate_explanation
from claimguard.guards.injection import _normalize
from .minimize import minimize

_APPROVAL = re.compile(
    # Not a bare "approved": "the authorization is not approved" is a correct
    # R009 explanation.
    r"\b(?:(?:claim|payment) (?:is |has been |was )?approved|can be (?:paid|approved|submitted)|"
    r"ready (?:for|to) (?:payment|submit)|"
    r"all (?:checks|rules) (?:passed|pass)|(?:check|rule) passed|passes (?:the|this|all)|"
    r"no (?:issues?|problems?) (?:found|detected)|nothing to (?:fix|correct|review))\b",
    re.IGNORECASE,
)
_DRUG = r"(?:drugs?|medications?|medicines?|insulin|injections?|antibiotics?|treatment)"
# Matched against _normalize(text), which is casefolded: "µg" arrives as "μg".
_CLINICAL = re.compile(
    r"\b(?:prescrib(?:e|es|ed|ing)|dos(?:e|es|age|ages|ing)|"
    r"administer(?:s|ed|ing)? (?:(?:the|a|an|this) )?(?:\d+|" + _DRUG + r")|"
    r"surgery|surgeries|surgical|"
    r"(?:medically|clinically) (?:necessary|unnecessary|indicated|appropriate|justified)|"
    r"medical necessity|"
    r"stop taking|(?:stop using|discontinue) (?:(?:the|this|your|their) )?" + _DRUG + r"|"
    r"(?:patient|member) (?:should|must|needs to) (?:take|undergo)|"
    r"\d+(?:[.,]\d+)? ?(?:mg|mcg|μg|ml|iu)|"
    r"units? (?:daily|per day|a day|twice|once|every|of " + _DRUG + r"))\b"
)
_RULE_ID = re.compile(r"\bR\d{3}\b")


class _Failure(Exception):
    def __init__(self, reason, detail=""):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


def _call(provider, finding_view, rule_view, timeout):
    box = {}

    def run():
        try:
            box["out"] = provider.explain(finding_view, rule_view)
        except Exception as e:  # any provider failure is a fallback, never a crash
            box["err"] = type(e).__name__

    # A daemon thread: a provider that never returns cannot hold up the run or
    # the interpreter's exit.
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise _Failure("timeout", f"no answer within {timeout:g} s")
    if "err" in box:
        raise _Failure("model_error", box["err"])
    return box["out"]


def _checked(output, finding):
    if isinstance(output, (str, bytes)):
        try:
            output = json.loads(output)
        except (ValueError, RecursionError):
            raise _Failure("invalid_json", "not a JSON object") from None
    try:
        validate_explanation(output, finding)
    except (ValueError, TypeError, KeyError) as e:
        raise _Failure("invalid_output", str(e) if isinstance(e, ValueError) else type(e).__name__) from None
    text = output["explanation"]
    if finding["status"] in ("FAIL", "UNABLE_TO_ASSESS") and _APPROVAL.search(text):
        raise _Failure("status_contradiction", f"text presents a {finding['status']} finding as passed")
    if _CLINICAL.search(_normalize(text)):
        raise _Failure("clinical_advice", "text gives clinical advice")
    if set(_RULE_ID.findall(text)) - {finding["rule_id"]}:
        raise _Failure("unknown_rule", "text names another rule ID")
    return output


def _record(finding, provider, prompt_version, source, output, latency_ms, failure):
    return {
        "claim_id": finding["claim_id"],
        "rule_id": finding["rule_id"],
        "status": finding["status"],
        "source": source,
        "provider": provider.name,
        "model": provider.model,
        "prompt_version": prompt_version,
        "latency_ms": latency_ms,
        "explanation": output["explanation"],
        "cited_evidence_paths": list(output["cited_evidence_paths"]),
        "cited_rule_ids": list(output["cited_rule_ids"]),
        "needs_human_review": output["needs_human_review"],
        "failure": failure,
    }


def deterministic(finding):
    """The rule engine's own explanation, in the provider's output shape."""
    return {
        "explanation": finding["explanation"],
        "cited_evidence_paths": [e["path"] for e in finding["evidence"]],
        "cited_rule_ids": [finding["rule_id"]],
        "needs_human_review": finding["requires_human_review"],
    }


def skipped(finding, provider, prompt_version, why):
    """A finding the model must not see, e.g. on a claim flagged by the
    injection pre-filter. Not a model failure: no event."""
    return _record(finding, provider, prompt_version, why, deterministic(finding), None, None)


def explain_safely(provider, finding, rule, prompt_version, timeout):
    """(explanation record, model_failure event or None). Never raises for
    anything the provider does."""
    finding_view, rule_view = minimize(finding, rule)
    start = time.monotonic()
    try:
        output = _checked(_call(provider, finding_view, rule_view, timeout), finding)
    except _Failure as f:
        latency_ms = round((time.monotonic() - start) * 1000)
        failure = {"reason": f.reason, "detail": f.detail}
        event = {"event": "model_failure", "claim_id": finding["claim_id"], "rule_id": finding["rule_id"],
                 "provider": provider.name, "model": provider.model, "prompt_version": prompt_version,
                 "latency_ms": latency_ms, **failure}
        return _record(finding, provider, prompt_version, "fallback", deterministic(finding),
                       latency_ms, failure), event
    latency_ms = round((time.monotonic() - start) * 1000)
    return _record(finding, provider, prompt_version, "provider", output, latency_ms, None), None
