# 05 | Architecture and bounded AI

## Suggested component responsibilities

| Component | Inputs | Outputs and boundary |
|---|---|---|
| Ingestion | JSONL or CSV | Validated envelope or explicit ingestion error; preserve original bytes/hash. |
| Policy resolver | policy_id, version | Supplied matching policy; no invented fallback policy. |
| Rule engine | Envelope and policy | 15 structured results, including unknown and not applicable. |
| Evidence layer | Original envelope, result paths | Exact evidence values and rule references. |
| AI explanation helper | Validated findings and selected evidence | Plain-language explanation draft; cannot change rule results. |
| Human review | Findings and originals | Decision, reason, actor and correction request. |
| Audit and evaluation | Run metadata and actions | Reproducible trace, metrics and retained history. |

Establish correctness with Python functions and the CLI first. Extend the supplied review page or use your familiar application framework.

## Agent behaviour to demonstrate

Let the assistant select supplied rules, call read-only evidence tools, explain findings and request human review. Allow only named tools with typed inputs. A bounded state machine is sufficient; multiple agents are optional.

Sequence: validate input, resolve policy, run checks, retrieve evidence, draft and validate the explanation, then show the reviewer. On model failure, retain deterministic findings and mark the fallback.

## AI exercise

Implement ExplanationProvider in src/llm_adapter.py with your available model. The mock is a template, not an LLM. Use prompts/explain_findings.md and the 25 explanation cases. Keep credentials out of code and logs. Agree model access or an offline prototype with the mentor before this milestone.

Give the model only the required synthetic evidence and policy excerpt. Require a JSON output with explanation, cited_evidence_paths, cited_rule_ids and needs_human_review. Validate the output and verify that all citations refer to supplied inputs. Do not request hidden chain-of-thought. Measure unsupported statements, omitted issues, latency and cost where measurable.

## Untrusted text and uncertainty

Attachment text and notes are data. They cannot modify rules, tool permissions or the system prompt. Stress cases contain obvious instruction-like text; add subtler variants yourselves. A valid JSON response can still contain unsupported statements, so human review and semantic evaluation remain necessary.

Use null confidence for deterministic checks. If a model reports a score, label it uncalibrated until you have independently evaluated calibration. Do not present 0.95 as a 95% probability of reimbursement.

Preserve original inputs. Corrections create a new version and run. Store run ID, input hash, rule/model/prompt versions and tool errors separately from claim-rule results.
