# Running ClaimGuard from a clean checkout

Every command below was run on 2026-10-01 from a fresh copy of the repository, in a new virtual environment, with **no API key, no network access after install, and no extra package**. The expected output is what that run printed for the development split.

The root `README.md` is the pack's and is protected by `SHA256SUMS.json` (`src/validate_pack.py` fails if it changes), as is `.gitignore`. Replacing the README is a team decision recorded in ADR-001; until then, this page is the run guide.

## 1. Setup, once

```bash
git clone https://github.com/tammam-bt/ClaimGuardAI_MedNexus.git
cd ClaimGuardAI_MedNexus
uv venv --python 3.12
source .venv/bin/activate          # Windows: .venv\Scripts\activate
uv pip install -e .                # must be -e: claimguard reads the pack in src/
```

Python 3.10 or later. On Windows use `py` if `python` is not found.

## 2. Check the pack and the code

```bash
python src/validate_pack.py            # ends with PASS ... release checksums
python -m unittest discover -s tests   # ends with OK
```

The three secrets tests are skipped outside a git checkout; everything else runs.

## 3. Run the pipeline

| # | Command | Produces | Expected (development) |
|---|---|---|---|
| 1 | `python -m claimguard.ingest --input data/development/claims.jsonl` | `outputs/accepted.jsonl`, `outputs/ingestion_errors.jsonl` | 400 accepted, 0 rejected |
| 2 | `python -m claimguard.ingest --input data/development/fhir_bundles.jsonl --sidecar data/development/claims.jsonl --accepted outputs/fhir_accepted.jsonl --errors outputs/fhir_errors.jsonl` | the same 400 envelopes, built from FHIR | 400 accepted, 0 rejected |
| 2b | `python -m claimguard.ingest --input data/development/csv --accepted outputs/csv_accepted.jsonl --errors outputs/csv_errors.jsonl` | the same 400 envelopes, built from the CSV export | 400 accepted, 0 rejected |
| 3 | `python -m claimguard.guards --input outputs/accepted.jsonl` | `outputs/injection_flags.jsonl` | 4 claims flagged |
| 4 | `python src/run_baseline.py --input outputs/accepted.jsonl --output outputs/dev_predictions.jsonl` | 15 results per claim | 400 claims processed |
| 5 | `python src/evaluate.py --gold data/development/expected_results.jsonl --pred outputs/dev_predictions.jsonl --claims outputs/accepted.jsonl --output outputs/dev_metrics.json` | `outputs/dev_metrics.json` | status_accuracy 0.2 with the pack baseline |
| 6 | `python -m claimguard.ai --results outputs/dev_predictions.jsonl --claims outputs/accepted.jsonl` | `outputs/explanations.jsonl`, `outputs/model_failures.jsonl` | provider `mock`, 0 failures |
| 7 | `python -m claimguard.ai.exercises` | `outputs/exercise_explanations.jsonl`, `outputs/llm_scorecard_mock.csv` | 25 cases, 0 fallbacks |

Step 4 runs the pack's three-rule baseline until the team's runner exists (U2.6, Role 1); the runner takes the same accepted file. Step 5 scores against `outputs/accepted.jsonl`, the claims that passed ingestion: a rejected claim produces no results (doc 03: "quarantine it and report it separately").

Every command exits 0 when individual claims are rejected or flagged. They are reported in their own files, never dropped silently and never fatal to the run.

## 4. What each output file is

| File | One line per | Read by |
|---|---|---|
| `accepted.jsonl` | accepted claim, original bytes | the rules and the scorer |
| `ingestion_errors.jsonl` | rejected line: `stage`, `reason`, `claim_id`, `provenance` | a reviewer; the audit log once U4.4 accepts these events |
| `injection_flags.jsonl` | flagged claim: JSON pointer, family, decoding layer | the review queue; the AI explainer skips these claims |
| `dev_predictions.jsonl` | claim × rule result (scored) | `evaluate.py`; never written by the AI |
| `explanations.jsonl` | FAIL / UNABLE_TO_ASSESS result: `source` = `provider`, `fallback` or `skipped_flagged` | the review page |
| `model_failures.jsonl` | fallback: `reason` (timeout, model_error, invalid_json, invalid_output, status_contradiction, unknown_rule) | the audit log once U4.4 accepts these events |
| `llm_scorecard_mock.csv` | exercise case, for manual 0/1 scoring (doc 07) | the AI evaluation report |

No output file quotes untrusted text from a claim or a rejected model answer.

## 5. Settings

Copy `.env.example` to a file named exactly `.env` (the only name `.gitignore` covers). claimguard reads the environment, not the file: export the variables or use a tool that loads `.env`.

| Variable | Effect | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | noticed but not used until a live provider is wired (team decision) | unset: mock |
| `CLAIMGUARD_MODEL` | model ID for the live provider | unset |
| `CLAIMGUARD_AI_TIMEOUT_S` | seconds before a model call falls back; 0 < value ≤ 300 | 20 |

## 6. Rehearsal checklist (another laptop)

- [ ] Fresh clone, setup as in section 1, no `.env` present.
- [ ] `validate_pack.py` prints PASS; the test suite prints OK.
- [ ] Steps 1 to 7 give the expected column above.
- [ ] `outputs/explanations.jsonl` shows `"provider": "mock"`; `model_failures.jsonl` is empty.
- [ ] `git status` shows nothing to commit except `outputs/` being ignored (no `.env`, no key).
- [ ] Repeat on Python 3.10 if available: CI runs 3.10 and 3.12.
