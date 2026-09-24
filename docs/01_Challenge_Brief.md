# 01 | Challenge brief

**ClaimGuard AI: Trustworthy Agentic Copilot for Healthcare Claim Pre-Validation**

Challenge reference: CSTAM-VELODOC. Context: CSTAM 3.0. Mentor: Dr. Wael Hilali, CTO & Co-Founder, Velodoc / Amazit. Pack version: 1.0.0, 17 September 2026.

## Your mission

Build a usable copilot for a claims officer who checks a claim before submission. The officer needs to see what is wrong, which evidence supports the finding, what to review or correct, and which questions remain unresolved. The officer must be able to record a decision without overwriting the original evidence.

The supplied baseline implements three checks. Your work is to implement the remaining rules, add bounded AI assistance, design human review, measure the results and explain the limitations. This is a student challenge package prepared from the previously agreed scope; the suggested schedule and grading weights in this pack are mentor proposals, not an official organizer timetable.

## Required MVP behaviour

1. Ingest the normalized JSONL teaching data; CSV import is supplied. Demonstrate one FHIR mapping example.
2. Evaluate all 15 documented fictional rules, including uncertainty and not-applicable outcomes.
3. Report Claim ID, Rule ID/version, severity, affected lines, evidence, explanation and corrective action.
4. Show a review queue with filters, original values and clear unresolved-check counts.
5. Support confirm, dismiss with reason, request information, and corrected-for-recheck decisions.
6. Add one bounded AI capability, such as a plain-language explanation or a reviewer handover grounded in validated findings. Show tool boundaries, schema checks and a safe fallback. Do not relabel deterministic failures through an LLM.
7. Record checks and human actions with source/rule/model versions. Demonstrate a tamper-evident audit prototype and explain the additional storage/access controls needed for immutable production logging.
8. Evaluate on the provided data, then on a mentor-held set. Report false alarms, missed issues and uncertainty handling separately.

## Scope boundaries

Use synthetic records and fictional policy information only. No clinical diagnosis, medical-necessity judgment, fraud accusation, automatic claim approval, live payer submission or EHR integration is required. Services and diagnoses use invented educational codes. The pack is not a real reimbursement decision system.

## Submission checklist

- Reproducible repository with README, dependencies, configuration example and launch commands.
- Architecture and data-flow diagram with trust boundaries and tool permissions.
- Working review interface, recorded demo and concise pitch presentation.
- Technical report covering implementation, decisions, tests and limitations.
- Evaluation report with dataset split, rule metrics, false positives/negatives and AI ablations.
- Privacy/security note and auditable sample run. Keep secrets out of the repository.
- A contribution log explaining team roles and the use of AI coding tools.

Success means a reviewer can understand and verify the findings, and the team can show where the system succeeds or abstains. Visual polish alone is insufficient.
