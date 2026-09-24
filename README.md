# ClaimGuard AI | Student starter pack

**Start here.** Build a trustworthy copilot that pre-validates synthetic healthcare claims and supports human review.

Version 1.0.0 | CSTAM-VELODOC | Mentor: Dr. Wael Hilali

## Your first 30 minutes

1. Read docs/01_Challenge_Brief.md and docs/02_Claims_Primer.md.
2. Open examples/review_demo.html in a browser to see the review workflow.
3. Read one case in docs/13_Worked_Examples.md and its full input in examples/worked_cases.json.
4. Follow docs/06_Setup_and_First_Run.md. No paid account or extra Python packages are needed.
5. Agree team roles and the first three tasks with your mentor.

## What is included

- 600 unique public claims: 400 development, 150 validation, 50 stress.
- Normalized JSONL, relational CSV and educational FHIR R4-style projections.
- 15 fictional payer rules, two policy profiles, six service codes, public expected results.
- Ten worked examples and 25 bounded-AI explanation exercises.
- A runnable three-rule baseline, strict evaluator, CSV converter, local review page and audit prototype.
- Input/output schemas, prompt template, model-neutral mock adapter, tests and validation checks.
- Full handbook, workshop labs, roadmap, editable reporting templates and security guidance.

## Quick run (from this folder)

```bash
python src/validate_pack.py
python -m unittest discover -s tests -v
python src/run_baseline.py --input data/development/claims.jsonl --output outputs/dev_predictions.jsonl
python src/evaluate.py --gold data/development/expected_results.jsonl --pred outputs/dev_predictions.jsonl --claims data/development/claims.jsonl --output outputs/dev_metrics.json
python src/make_review.py --input outputs/dev_predictions.jsonl --output outputs/review.html
```

Open outputs/review.html. On Windows use py, or on macOS/Linux python3, if python is unavailable. See docs/06 for details.

## Read in this order

01 brief; 02 domain; 03 data contract; 04 rulebook; 06 setup; 13 examples; 05 architecture/AI; 07 evaluation; 08 workshop; 09 work plan; 10 security; 11 FHIR; 12 troubleshooting; 14 sources.

## Scope and honesty

All records and policies are synthetic. The baseline covers only R001/R003/R006; other checks are explicitly NOT_IMPLEMENTED. The mock adapter is not an LLM. The local hash chain is tamper-evident, not immutable storage. FHIR examples are educational mappings without full HL7/profile validation. Passing these fictional rules is not payer approval or evidence of production readiness.

Ask the mentor for model access before the AI milestone. Never place credentials or real patient records in this repository. Follow organizer instructions if they differ from suggested schedules or grading weights here.
