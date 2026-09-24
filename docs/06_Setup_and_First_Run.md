# 06 | Setup and first run

## Before starting

Extract the student ZIP into a writable folder. Open a terminal in ClaimGuardAI_Student_Starter_Pack, the folder containing README.md. Use Python 3.10 or later. A normal laptop is enough for the supplied standard-library code; no GPU, database, API key or network connection is needed for these exercises. A local LLM has separate hardware requirements and is optional.

On Windows, use py in place of python if that is your installed launcher. On macOS/Linux, use python3 if python is not available. Commands below assume python is available. A virtual environment is recommended for packages you add, but the supplied code needs no package installation.

```bash
python --version
python src/validate_pack.py
python -m unittest discover -s tests -v
python src/run_baseline.py --input data/development/claims.jsonl --output outputs/dev_predictions.jsonl
python src/evaluate.py --gold data/development/expected_results.jsonl --pred outputs/dev_predictions.jsonl --claims data/development/claims.jsonl --output outputs/dev_metrics.json
python src/make_review.py --input outputs/dev_predictions.jsonl --output outputs/review.html
```

Open outputs/review.html in your browser. Filter FAIL or UNABLE_TO_ASSESS, inspect evidence, enter a reviewer name and reason, and record a decision. Download review_decisions.jsonl and move it into outputs/ before the next command. Decisions stay only in the browser tab until downloaded.

```bash
python src/audit.py --events outputs/review_decisions.jsonl --log outputs/audit.jsonl
python src/audit.py --verify --log outputs/audit.jsonl
```

The audit is a local hash-chain demonstration. Anyone who controls the file can rewrite the chain or remove events; externally anchor the head and use restricted append-only/WORM storage for a stronger design. The starter does not implement production immutability, authentication or concurrent writes.

## Optional CSV exercise

```bash
python src/csv_to_jsonl.py --folder data/development/csv --output outputs/from_csv.jsonl
```

The rebuilt records should equal the authoritative JSONL, including nulls and child arrays. validate_pack.py checks this for all public splits.

## What to expect

The baseline implements R001, R003 and R006. It returns NOT_IMPLEMENTED for the other 12 rules, so its overall score is intentionally incomplete. Do not replace those statuses with PASS. Implement your next rule in engine_core.py, add tests and rerun evaluation. Human explanation quality is not determined by the numerical score.

## First success checkpoint

You can load a claim, explain its fields, run the baseline, locate a flagged field in the source, record a review decision and reproduce your results. Save a screenshot and a short team note explaining one correct finding and one limitation.
