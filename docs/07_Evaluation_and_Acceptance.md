# 07 | Evaluation and acceptance

## Evaluation protocol

Develop on the 400 development claims. Freeze a commit before the first validation run. Use the 150 validation claims to assess gaps; once their labels influence development, disclose that the set has become development feedback. The 50 stress cases test robustness and are not a representative prevalence sample. The mentor should keep the 200 held-out inputs and labels private until assessment.

The scorer requires every claim-rule pair exactly once. Missing pairs, extra pairs, duplicate outputs, invalid statuses and mismatched evidence values are rejected. NOT_IMPLEMENTED is a visible incomplete result and counts against accuracy. An empty predictor cannot achieve a passing assessment by omitting claims.

## Metrics

| Metric | Definition / interpretation |
|---|---|
| Issue precision | True predicted FAIL pairs / all predicted FAIL pairs. |
| Issue recall | True predicted FAIL pairs / all expected FAIL pairs. |
| Issue F1 | Harmonic balance of issue precision and recall. |
| False-alarm rate | Predicted FAIL among pairs whose expected status is not FAIL. |
| Status accuracy | Exact agreement across PASS, FAIL, UNABLE_TO_ASSESS and NOT_APPLICABLE. |
| False abstentions | Predicted unable-to-assess when expected status is something else. |
| Missed abstentions | Expected unable-to-assess but predicted a different status. |
| Claim exact match | All 15 rule statuses correct for a claim. |

Undefined precision/recall is reported as null, not 100%. All metrics are at claim-rule level unless explicitly labeled otherwise. Examine per-rule results and confusion counts; overall accuracy can hide rare failures. Evidence-value checks do not prove that the chosen field is relevant to a conclusion.

## Proposed mentor assessment weights

| Area | Weight | Evidence to inspect |
|---|---|---|
| Rule correctness | 35 | Per-rule results; date, amount and authorization edge cases. |
| Grounded AI explanations | 20 | 25 supplied exercise cases plus fresh variants; no unsupported approvals. |
| Human review and usability | 15 | Reviewer can trace, dismiss with reason, request info and trigger recheck. |
| Uncertainty and security | 15 | Unknown data, malicious document text, tool errors and access boundaries. |
| Audit and reproducibility | 10 | Trace hashes/versions, audit history, repeatable installation. |
| Communication | 5 | Concise architecture, limitations and demonstration. |

These weights are proposals for this pack, not official CSTAM criteria. Agree any numerical pass thresholds at kickoff. For a fully implemented deterministic engine, exact status agreement on the supplied fictional rules is an appropriate development goal; high synthetic accuracy is not evidence of production readiness.

## Non-negotiable demonstration checks

- No unimplemented or unknown check is represented as a pass.
- Each flagged issue links to source evidence and the applicable fictional rule.
- A model failure cannot remove a deterministic finding.
- The original input is preserved and a correction is rechecked as a new version.
- No real patient information, exposed credential or live payer submission appears in the demo.

## AI evaluation

Run the baseline with template explanations, then your model-assisted version on the same cases. Manually score each explanation 0/1 for correct finding, correct evidence, correct rule, appropriate action and honest uncertainty. Record unsupported facts separately. Include model identifier, prompt version, parameters, latency, model failures and any measured cost. Report repeat runs if outputs vary; never tune on the hidden labels.
