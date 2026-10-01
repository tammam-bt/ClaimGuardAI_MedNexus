# ClaimGuard AI · team MedNexus

A pre-validation copilot for synthetic healthcare claims. CSTAM 3.0 · challenge CSTAM-VELODOC · mentor Dr. Wael Hilali (Velodoc).

It checks a claim against a 15-rule fictional payer rulebook before submission, reports every finding with the exact evidence it rests on, keeps instruction-like text away from the AI, explains findings in plain language under a watchdog, routes the claim to a human reviewer, and records what happened in a tamper-evident log. All data is synthetic; nothing here is a payment decision.

How it fits together, with trust boundaries and data flow: [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).

## Status

| | |
|---|---|
| Rules implemented | 15 / 15 |
| Status accuracy · development (400 claims) | 1.00 |
| Status accuracy · validation (150) | 1.00 |
| Status accuracy · stress (50) | 1.00 |
| False alarms | 0 |
| Input formats | JSONL · CSV export · FHIR R4 bundles |

Measured with the starter pack's own scorer, `src/evaluate.py`, on public synthetic data. It shows the rules match the fictional rulebook, not that the system is production-ready.

## Install

Python 3.10 or later. No third-party packages, no API key, no network.

```bash
git clone https://github.com/tammam-bt/ClaimGuardAI_MedNexus.git
cd ClaimGuardAI_MedNexus
uv venv --python 3.12
source .venv/bin/activate          # Windows: .venv\Scripts\activate
uv pip install -e .                # must be -e: claimguard reads the pack in src/
python src/validate_pack.py        # ends with PASS
python -m unittest discover -s tests   # ends with OK
```

## Run

One command does the whole pipeline:

```bash
python -m claimguard.run --input data/development/claims.jsonl --output outputs/dev_predictions.jsonl \
  --explain --audit-log outputs/audit.jsonl
```

| Input | Flag |
|---|---|
| normalized JSONL | `--input data/development/claims.jsonl` |
| CSV export (a folder) | `--input data/development/csv` |
| FHIR R4 bundles | `--input data/development/fhir_bundles.jsonl --sidecar data/development/claims.jsonl` |

Exit code 0 when every record was ingested and every rule ran; 2 when something was rejected or a rule failed (each is listed in the manifest). A rejected claim is never fatal and never silently dropped.

Then:

```bash
# Score with the pack's official scorer
python src/evaluate.py --gold data/development/expected_results.jsonl \
  --pred outputs/dev_predictions.jsonl --claims data/development/claims.jsonl --output outputs/dev_metrics.json

# Per-rule confusion matrices and every mismatch
python -m claimguard.evaluation.confusion --gold data/development/expected_results.jsonl \
  --pred outputs/dev_predictions.jsonl --claims data/development/claims.jsonl \
  --output outputs/dev_confusion.json --markdown outputs/dev_confusion.md

# Route each claim: ESCALATE, REVIEW or CLEAR
python -m claimguard.review.routing --input outputs/dev_predictions.jsonl --output outputs/dev_routing.jsonl

# Review page (from the starter pack)
python src/make_review.py --input outputs/dev_predictions.jsonl --output outputs/review.html

# Verify the audit log, against its anchored head; the pack's verifier accepts it too
python -m claimguard.audit.chain --log outputs/audit.jsonl
python src/audit.py --verify --log outputs/audit.jsonl
```

## What each output is

| File | One line per | Read by |
|---|---|---|
| `dev_predictions.jsonl` | claim × rule result (the scored file) | `evaluate.py`, routing, review page; never written by the AI |
| `dev_predictions.jsonl.manifest.json` | the run: input and record hashes, provenance, rule and policy versions, ingestion errors, rule errors, injection flags, AI summary | a reviewer, the audit log |
| `dev_predictions.jsonl.explanations.jsonl` | FAIL / UNABLE_TO_ASSESS result: `source` = `provider`, `fallback` or `skipped_flagged` | the reviewer |
| `audit.jsonl`, `audit.head.json` | event in the hash chain; the anchored head | `claimguard.audit.chain`, `src/audit.py` |

No output quotes untrusted text from a claim or a rejected model answer.

## Settings

Copy `.env.example` to a file named exactly `.env` (the only name `.gitignore` covers). claimguard reads the environment, not the file.

| Variable | Effect | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | noticed, but not used until a live provider is wired | unset: the pack's mock explains |
| `CLAIMGUARD_MODEL` | model ID for the live provider | unset |
| `CLAIMGUARD_AI_TIMEOUT_S` | seconds before a model call falls back; 0 < value ≤ 300 | 20 |

## Team

| Member | Role |
|---|---|
| Tammam BenBettaieb | Role 1 · spine and audit · team lead |
| Malak Ben Othmane | Role 2 · identity and catalogue rules (R002, R004, R005, R011, R015) |
| Mohammed Aziz Kadri | Role 3 · money rules (R007, R012, R013), routing, evaluation |
| Aymen Zahmoul | Role 4 · authorization and document rules (R008, R009, R010, R014), correction workflow |
| Kacem Barhoumi | Role 5 · ingestion, guards, AI explainer |

Roles 4 and 5 were committed from Mohammed Aziz Kadri's account (PRs #14 and #15).

## Where things are

| Path | What |
|---|---|
| `claimguard/` | Our code: `engine/`, `rules/`, `ingest/`, `guards/`, `ai/`, `review/`, `evaluation/`, `audit/`, `run.py` |
| `src/`, `data/`, `rules/`, `schemas/`, … | The starter pack, byte-identical to tag `pack-v1.0.0` (the root `README.md` is the pack's) |
| `docs/ARCHITECTURE.md` | Architecture, trust boundaries, data flow, limitations |
| `docs/ARCHITECTURE_DECISIONS.md` · `docs/DECISIONS.md` | Engineering decisions · rule clarifications and open mentor questions |
| `CONTRIBUTING.md` | How the team works |
