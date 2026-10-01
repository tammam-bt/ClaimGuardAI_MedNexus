"""AI explainer (U3.5): a plain-language explanation for each flagged result.

Reads the rule engine's results and never changes them. Explanations go to
their own records, keyed by (claim_id, rule_id), so a model answer or a model
failure can never reach the scored results that evaluate.py reads.

Only FAIL and UNABLE_TO_ASSESS results are explained: they are what a
reviewer acts on, and explaining all 15 results of every claim would be 6,000
model calls on the development set alone. A claim flagged by the injection
pre-filter is not sent to the model at all; its findings keep the rule
engine's explanation, recorded as skipped_flagged.
"""
from collections import Counter

from claimguard.guards import screen

from .minimize import load_prompt
from .provider import select_provider, timeout_from
from .watchdog import explain_safely, skipped

EXPLAINED = ("FAIL", "UNABLE_TO_ASSESS")


def explain_run(results, claims, rules, provider=None, timeout=None):
    """(explanation records, model_failure events, summary).

    results  the rule engine's result rows, unchanged
    claims   {claim_id: claim}, needed only to screen each claim's text
    rules    {rule_id: rule entry from rules/rules.json}
    """
    reason = "supplied by the caller"
    if provider is None:
        provider, reason = select_provider()
    timeout = timeout_from() if timeout is None else timeout
    _, prompt_version = load_prompt()

    screenings, records, events = {}, [], []
    for result in results:
        if result["status"] not in EXPLAINED:
            continue
        cid = result["claim_id"]
        if cid not in claims:
            raise ValueError("a result names a claim that is not in the claims file")
        if cid not in screenings:
            screenings[cid] = screen(claims[cid])
        if not screenings[cid].ai_allowed:
            records.append(skipped(result, provider, prompt_version, "skipped_flagged"))
            continue
        record, event = explain_safely(provider, result, rules[result["rule_id"]], prompt_version, timeout)
        records.append(record)
        if event:
            events.append(event)

    summary = {
        "provider": provider.name,
        "model": provider.model,
        "provider_reason": reason,
        "prompt_version": prompt_version,
        "timeout_s": timeout,
        "findings": len(records),
        "by_source": dict(sorted(Counter(r["source"] for r in records).items())),
        "failures": dict(sorted(Counter(e["reason"] for e in events).items())),
        "flagged_claims": sum(not s.ai_allowed for s in screenings.values()),
    }
    return records, events, summary
