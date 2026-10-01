# Role 5: Ingestion, AI & Guards (work summary)

Author: Mohammed Aziz Kadri · Date: 2026-10-01 · Branch: `mak/role5-ingest-guards-ai` (see section 9)

This page records everything built for Role 5, why each choice was made, how it was verified, and what is still open. Every number below was measured on the public data in this repository.

---

## 1. Status at a glance

| Unit | What it is | Status |
|---|---|---|
| U1.4 | FHIR R4 adapter | ✅ Done: all 600 bundles rebuild their claims exactly |
| U1.6 | Malformed-input handling | ✅ Done |
| U1.7 | Source provenance | ✅ Done (JSONL, CSV and FHIR) |
| — | CSV adapter (not in the unit list; the `ingest` package names it) | ✅ Done |
| U2.7 | AI side of the engine: real API call | ❌ **Not done.** Built against the mock; the live model waits for the squad's decision |
| U3.5 | AI explainer wired into the pipeline | ✅ Done, against the mock (a command; the team runner U2.6 does not exist yet) |
| U3.7 | Watchdog / fallback | ✅ Done |
| U6.3 | Data minimization | ✅ Done |
| U6.4 | Injection pre-filter | ✅ Done |
| U6.5 | Graceful malformed FHIR | ✅ Done |
| U6.6 | RBAC sketch (reviewer vs admin) | ✅ Done as a sketch (nothing calls it yet) |
| U6.7 | Secrets hygiene | ⚠️ Mostly done: `.gitignore` cannot be widened (pack checksum) |
| D3 | README: clean-checkout run | ⚠️ Done as `docs/RUNNING.md` (the root README is checksum-protected) |
| D7 | Rehearsal from a fresh clone on another laptop | ❌ **Not done.** Needs a person and a second computer |

**Tests:** 96 new tests; with the merged rules, the full suite (320 tests) passes on **Python 3.10 and 3.12**, the two versions CI uses.
**Protected files:** none changed. `python src/validate_pack.py` still prints PASS, including the release checksums.

---

## 2. The pipeline Role 5 owns

```
 claims.jsonl ──┐
 csv/ folder ───┼──► INGESTION (U1.6, U1.7, U1.4, U6.5)
 fhir bundles ──┘        │  each claim checked on its own
                         ├──► accepted claims  ──► 15 rules ──► predictions.jsonl  (scored)
                         └──► ingestion_errors.jsonl (reported, never fatal)
                                                         │
                         INJECTION PRE-FILTER (U6.4) ◄───┘ every string of every claim
                                │  flagged claims keep all 15 results
                                │  but never reach the model
                                ▼
                 only FAIL / UNABLE_TO_ASSESS results
                                ▼
                 DATA MINIMIZATION (U6.3): one finding + its rule, never the claim
                                ▼
                 PROVIDER (U2.7): the mock today
                                ▼
                 WATCHDOG (U3.7): 7 checks, else the rule's own explanation
                                ▼
                 explanations.jsonl + model_failures.jsonl   (U3.5)
                 never written into predictions.jsonl
```

Two principles run through all of it:

1. **Nothing Role 5 does can change a scored result.** Ingestion passes claims through unchanged; the guards only report; the AI writes to its own files.
2. **No output quotes untrusted text.** Error records, flags and failure events name a JSON pointer, a stage or a reason, never the claim's text or a rejected model answer. So injection text cannot travel into logs or the UI through them.

---

## 3. Ingestion (U1.6, U1.7, CSV, U1.4, U6.5)

### 3.1 The problem it solves

The pack's runner (`src/run_baseline.py`) calls `validate_transport()` on every claim with no guard: **one malformed line aborts the run for every claim**. Doc 03 says a malformed input "is an ingestion error: quarantine it and report it separately, never silently drop it or create a passed claim".

`validate_transport()` also lets through inputs that later break the run or behave differently per Python version:

| Input | Problem | Recorded in |
|---|---|---|
| `NaN`, `Infinity`, `1e999` | `evaluate.py` rejects the **whole run** (`NaN != NaN`) | DEC-003 |
| Dates such as `20260525`, `2026-W21-1` | Python 3.12 reads them as dates, 3.10 does not | DEC-010 |
| `"attachments": [null]`, incomplete coverage | Not checked inside arrays; rules crash or guess | DEC-012 |

### 3.2 The contract check (`claimguard/ingest/contract.py`)

Every claim, whatever its source, goes through two checks in order:

1. the pack's `validate_transport()`, unchanged;
2. `schemas/claim.schema.json`, **read from the file** so it can never drift from it.

The schema already forbids all three problems above: numbers must be finite, dates are `format: date`, and nested records have required keys and no extra keys. This **cannot reject a legitimate claim**: `QA_REPORT.md` states that all 800 claims, the mentor's 200 held-out ones included, were checked against this schema, and our tests confirm all 600 public claims pass.

Details that matter:

- A date must match `[0-9]{4}-[0-9]{2}-[0-9]{2}` **with ASCII digits** (`\d` also matches fullwidth digits) and be a real calendar date. Every rule then sees the same input on 3.10 and 3.12.
- `True` is not a quantity (`bool` is a subclass of `int` in Python).
- An integer too large for a double (`10**400`) is rejected on both Python versions.
- If the schema ever uses a keyword the check does not implement, it fails loudly at import instead of ignoring it.

### 3.3 JSONL adapter (`claimguard/ingest/jsonl.py`)

Each line is read and checked on its own. Rejection stages:

| Stage | Example |
|---|---|
| `decode` | invalid UTF-8 |
| `json` | broken JSON, duplicate keys in an object, nesting 100,000 levels deep |
| `transport` | missing envelope key, `True` as quantity |
| `contract` | NaN, `20260525`, `"attachments": [null]` |
| `duplicate_claim_id` | the same claim twice (the first is kept) |

Duplicate JSON keys are rejected because `json.loads` silently keeps the last one: a reviewer reading the raw line and the engine could see different values.

An accepted claim is **exactly** the object the pack's own reader produces, so every evidence value still resolves (Trap 3). The command writes each accepted line's **original bytes** to `outputs/accepted.jsonl`, which the pack's runner and scorer read unchanged.

### 3.4 Provenance (U1.7)

Every claim and every error record carries:

```json
{"adapter": "jsonl", "adapter_version": "1.0.0", "source": "data/development/claims.jsonl",
 "source_sha256": "…", "line_number": 48, "record_sha256": "…", "sidecar": null, "parts": null}
```

It travels **beside** the claim (`Ingested(claim, provenance, raw)`), never inside it, because `validate_transport()` rejects any extra envelope key (Trap 15). `sidecar` is filled by the FHIR adapter and `parts` by the CSV adapter.

### 3.5 CSV adapter (`claimguard/ingest/csv_folder.py`)

Assembles each claim from the five files of a `csv/` folder (`claims`, `coverage`, `lines`, `authorizations`, `attachments`).

- **The pack's converter has Trap 1 again:** one orphan row or one `quantity = "abc"` stops `csv_to_jsonl.py` for every claim. Here a bad row rejects only its own claim. A test proves both behaviours.
- **More faithful than the pack's converter:** it reads numbers with the JSON parser, so `280.0` stays a float as in the JSONL (the converter turns it into `280`; 8 public amounts are written this way).
- **Strict numbers:** `" 12"`, `"1_000"`, `"inf"`, `"nan"` and Arabic-Indic digits `"١٢"` are rejected; Python's `float()` would accept them silently.
- Extra stages: `csv` (bad row), `orphan_row` (child row of an unknown claim), `duplicate_claim_id` (every copy rejected, since child rows cannot be told apart).
- Expected columns and numeric columns come from `claim.schema.json`. A wrong header is a file-level error, because no row of that file can be read.
- Result: **all 600 public claims rebuilt identically** to the JSONL (values, JSON types and key order at every level).

### 3.6 FHIR adapter (U1.4, `claimguard/ingest/fhir.py`)

Each bundle holds Patient, 2 Organizations (provider and payer), Coverage and Claim, plus DocumentReference in 329 of 600 bundles (372 documents in all). There is no "ClaimItem" resource: lines are `Claim.item`.

The mapping, verified field by field on all 600 bundles with **zero mismatches**:

| Envelope field | FHIR source | When absent |
|---|---|---|
| `claim_id` | `Claim.id` | — |
| `invoice_number` | `Claim.identifier[system=…/ids/invoice]` | `null` |
| `patient_id` | `Claim.patient` → `Patient.id` | — |
| `member_id` | `Patient.identifier[system=…/ids/member]` | `null` |
| `provider_id` / `payer_id` | `Claim.provider` / `Claim.insurer` → Organization | — |
| `policy_id` | `Coverage.class[type=plan].value` | — |
| `diagnosis_code` | `Claim.diagnosis[0]…code` | `null` |
| `submission_date` | `Claim.created` | — |
| `currency`, `total_amount` | `Claim.total.currency`, `.value` | — |
| `coverage` | Coverage: `id`, `status`, `beneficiary`, `subscriberId`, `period` | `null` per field |
| line `line_id` | `"L" + item.sequence` | — |
| line fields | `productOrService`, `servicedDate`, `modifier`, `quantity`, `unitPrice`, `net` | `null` |
| line `authorization_id` | `line-authorization-id` extension | `null` |
| attachments | DocumentReference: `id`, type, subject, `description` ("Synthetic SVC-…"), `context.period.start`, `docStatus` (`final`→`final`, `preliminary`→`draft`), base64 text | — |

Only **three parts come from the normalized "sidecar"** (doc 12: "The normalized envelope is the authoritative sidecar"; it is the JSONL itself, not a separate file): `schema_version`, `notes`, and the **authorization records** (FHIR carries only their IDs in `preAuthRef`, which are cross-checked).

The FHIR-built envelope must **equal the sidecar claim** field for field. Any difference is an error naming the field (`fhir_mismatch`), never repaired: one of the two files is wrong, and choosing would be guessing (doc 04: "Do not silently trim or repair source data").

Doc 11 warns that some records deliberately reference a document patient outside the bundle. That is a business inconsistency for R010 to find, not a malformed bundle, so references only have to resolve where their content is needed.

### 3.7 Malformed FHIR (U6.5)

Any bundle outside the projection becomes an error record (stage `fhir`), never a crash: wrong bundle type, no Claim or two Claims, duplicate `fullUrl`, dangling or wrongly typed references, missing elements, duplicate item sequence, bad base64, non-UTF-8 text, unknown `docStatus`, non-string IDs. **500 seeded random corruptions** of a bundle never crash the run and never yield an envelope that differs from the sidecar.

---

## 4. Injection pre-filter (U6.4, `claimguard/guards/injection.py`)

### 4.1 What "flagged" means (Trap 16)

A flagged claim:

- **still runs all 15 rules and keeps every result.** Its expected results are ordinary (CG-116C84D4774D carries the injection sentence and its R012 is FAIL), and `evaluate.py` rejects a run that drops a claim;
- is **never sent to the model** (`Screening.ai_allowed == False`);
- produces an `injection_flag` event for the reviewer.

The docs use "quarantine" for ingestion errors (claims that are not read), so a flagged claim is never called quarantined.

### 4.2 How it scans

- **Every string** in the claim, not only notes and attachment text: `service_code`, `modifier` and IDs are free text too, and reach the model as evidence.
- **Decodes first:** HTML entities, tags and comments, `%` encoding, literal `o` escapes, base64 (including double base64), hex, ROT13, reversed text. Base64 is normal in FHIR, so it is decoded and scanned, never flagged by itself (Trap 15).
- **Normalizes:** NFKC, accents removed, zero-width characters removed, Cyrillic and Greek lookalikes mapped to Latin.
- **Squashes:** separators removed and leetspeak mapped, which catches `ign ore`, `i.g.n.o.r.e`, `1gn0r3`.
- **Joins fields in both directions:** an instruction that starts in `notes` and ends in an attachment is caught (notes come last in the envelope, so one direction is not enough).
- **8 families:** override, role marker (`SYSTEM:`), role play, secret request, decision forcing, output tampering, tool or exfiltration, false authority ("the payer says…").

### 4.3 Results

| Test set | Result |
|---|---|
| 600 public claims | 9/9 injection claims flagged, **0 false positives** on the other 591 |
| 25 exercise cases | 5/5 hostile notes flagged, 0/20 benign |
| Encoded or obfuscated variants (base64, hex, ROT13, spacing, leetspeak, homoglyphs, zero-width…) | 19/19 detected, plus split-field attacks in both directions |
| Benign near-misses ("previous instructions from the physician were followed", "Lab report: all checks passed") | none flagged |

**Known limit:** English patterns plus a few French forms. An instruction phrased differently, or in another language, passes the filter. That is acceptable because the real protection is architectural: rules never read free text, and model output is validated and kept out of the scored results.

---

## 5. The AI part (U2.7, U3.5, U3.7, U6.3), built against the mock

### 5.1 Data minimization (U6.3, `claimguard/ai/minimize.py`)

The model receives **one finding and its rule, never the claim**:

- no `claim_id` (doc 03: "never a model feature"), and it is masked inside derived IDs too (`DOC-CG-…-1` becomes `DOC-<claim>-1`). A test caught this leak;
- notes and attachment text are withheld (R010's evidence contains the full attachment text, injection included: Trap 13);
- any string over 64 characters is withheld;
- evidence **paths** stay unchanged, so citations can still be checked;
- the rule as ID, title, severity, logic and corrective action.

### 5.2 Provider (U2.7, `claimguard/ai/provider.py`)

- No `ANTHROPIC_API_KEY` → the pack's mock. With a key → **still the mock**, with a reason saying no live provider is wired yet. The key is checked for presence only and never logged.
- Timeout from `CLAIMGUARD_AI_TIMEOUT_S` (default 20 s, must be between 0 and 300).
- **To plug in the live model later:** write one class with `name`, `model` and `explain(finding, rule)` that sends `build_messages()` to Claude, and return it from `select_provider()`. Nothing else changes.

### 5.3 Watchdog (U3.7, `claimguard/ai/watchdog.py`)

Every answer ends in exactly one outcome:

| Outcome | Trigger |
|---|---|
| `ok` | passed every check |
| `timeout` | no answer in time (daemon thread: a hung provider cannot block the run) |
| `model_error` | the provider raised (its message is not logged: it could contain a key) |
| `invalid_json` | the answer is not one JSON object |
| `invalid_output` | the pack's `validate_explanation()` refused it: wrong keys, empty text, unknown or missing citation, other rule ID, changed `needs_human_review` |
| `status_contradiction` | the text presents a FAIL or UNABLE_TO_ASSESS finding as passed or approved |
| `unknown_rule` | the text names another rule ID |

The model's output has **no status field**, so it cannot change a status directly; its text is the only place it could contradict the rule, which the last two checks look at (heuristics). On anything but `ok`: the rule engine's own explanation, `source: fallback`, and a `model_failure` event.

### 5.4 Explainer (U3.5, `claimguard/ai/explainer.py`)

- Explains **only FAIL and UNABLE_TO_ASSESS** results (Trap 17: all 15 would mean 6,000 calls on the development set).
- Skips flagged claims entirely (`source: skipped_flagged`, no model call).
- Writes `outputs/explanations.jsonl` keyed by `(claim_id, rule_id)` and `outputs/model_failures.jsonl`. **The scored results are only read** (tested by hash: the predictions file is byte-identical after the AI runs).
- Prints the AI part of the run manifest: provider, model, prompt version, timeout, counts.

### 5.5 The 25 graded exercises (doc 07, `claimguard/ai/exercises.py`)

Runs `exercises/llm_explanation_cases.jsonl` through the current provider and writes `outputs/llm_scorecard_mock.csv` in the columns of the pack's scorecard, with `case_id` and `latency_ms` filled. The 0/1 columns are for a person to score; the mock's scorecard is the baseline for the mock-versus-model comparison. Exercise notes are never sent to the model (by design, U6.3), and the scorecard says so on the 5 "resist" cases.

### 5.6 Measured

With the mock on all public data: **777 FAIL/UNABLE_TO_ASSESS findings explained, 0 false fallbacks**; the 9 injection claims skipped; 25 exercises, 0 fallbacks.

---

## 6. RBAC sketch (U6.6) and secrets (U6.7)

### 6.1 RBAC (`claimguard/guards/rbac.py`)

The pack defines no roles; doc 10 says the review page uses self-declared names without authentication. This is **authorization given an identity**; authentication is out of scope and stated as such.

| Role | May |
|---|---|
| `reviewer` | view claims and findings, the 4 review actions, export decisions |
| `admin` | everything above, plus run the pipeline, append and verify the audit log, view run events, change AI settings |

The role **never goes into a review event or a result row**: both schemas forbid extra keys, and `evaluate.py` rejects a result with one (Trap 10). It is looked up in a separate `{actor: role}` directory. `authorize_event()` also requires the schema's exact keys and a reason for every action, as `src/audit.py` does. A role smuggled into an event is refused, not trusted.

### 6.2 Secrets

- `.env.example` with empty `ANTHROPIC_API_KEY`, `CLAIMGUARD_MODEL`, `CLAIMGUARD_AI_TIMEOUT_S=20`.
- A test scans every file `git add -A` would take for key-like strings (Anthropic, AWS, GitHub, private keys): none found.
- `.gitignore` ignores `.env` but **not** `.env.local` or `.env.prod`. It cannot be widened: it is a pack file under `SHA256SUMS.json` (see section 8). `.env.example` warns to use the name `.env` only.

---

## 7. Files

### 7.1 New or changed code

| Path | Purpose |
|---|---|
| `claimguard/ingest/contract.py` | transport + schema check shared by all adapters |
| `claimguard/ingest/jsonl.py` | JSONL adapter, `Provenance`, `Ingested`, `IngestResult` |
| `claimguard/ingest/csv_folder.py` | CSV adapter |
| `claimguard/ingest/fhir.py` | FHIR adapter |
| `claimguard/ingest/__main__.py` | `python -m claimguard.ingest` |
| `claimguard/guards/injection.py`, `__main__.py` | pre-filter, `python -m claimguard.guards` |
| `claimguard/guards/rbac.py` | RBAC sketch |
| `claimguard/ai/minimize.py` | what the model sees, prompt messages |
| `claimguard/ai/provider.py` | provider selection, timeout setting |
| `claimguard/ai/watchdog.py` | checks and fallback |
| `claimguard/ai/explainer.py`, `__main__.py` | `python -m claimguard.ai` |
| `claimguard/ai/exercises.py` | `python -m claimguard.ai.exercises` |
| `claimguard/ai/_adapter.py` | the single import of the pack's `llm_adapter` (see section 10) |
| `.env.example` | settings template |

### 7.2 Tests (96 new; 320 in the full suite with the merged rules)

| File | Tests | Covers |
|---|---|---|
| `tests/test_ingest.py` | 21 | JSONL adapter, contract, provenance, the pack runner crash vs. ours |
| `tests/test_csv.py` | 16 | CSV adapter, exact rebuild, bad rows, the pack converter crash vs. ours |
| `tests/test_fhir.py` | 12 | FHIR mapping, malformed bundles, 500-mutation fuzz |
| `tests/test_injection.py` | 12 | public data, exercises, 19 variants, 10 families, benign texts, 15 results kept |
| `tests/test_ai.py` | 24 | minimization, all watchdog outcomes, explainer, clean run without key |
| `tests/test_rbac_and_secrets.py` | 11 | roles, events, ignored files, secret scan |

### 7.3 Documentation

| Path | Content |
|---|---|
| `docs/RUNNING.md` | clean-checkout run guide (D3), verified from a fresh copy without a key |
| `docs/ARCHITECTURE_DECISIONS.md` | ADR-005 ingestion, ADR-006 injection flag, ADR-007 AI boundary, ADR-008 FHIR |
| `docs/ROLE_5.md` | this page |

### 7.4 Commands

```bash
python -m claimguard.ingest --input data/development/claims.jsonl
python -m claimguard.ingest --input data/development/csv
python -m claimguard.ingest --input data/development/fhir_bundles.jsonl --sidecar data/development/claims.jsonl
python -m claimguard.guards --input outputs/accepted.jsonl
python -m claimguard.ai --results outputs/dev_predictions.jsonl --claims outputs/accepted.jsonl
python -m claimguard.ai.exercises
```

The full sequence, with expected outputs, is in `docs/RUNNING.md`.

---

## 8. Rules respected, and problems found on the way

**Never touched:** `src/`, `data/`, `rules/*.json`, `schemas/`, `examples/`, `claimguard/engine/`, `claimguard/_pack.py`, `.github/`, other people's rule files, and `src/llm_adapter.py`.

Problems found and fixed while working:

| Problem | Consequence if missed | Fix |
|---|---|---|
| `.gitignore` is under the pack's checksum | CI red at "Starter pack integrity" | edit reverted; limitation documented |
| `README.md` is under the pack's checksum | same | run guide in `docs/RUNNING.md`; replacing the README is Tammam's call (ADR-001) |
| Derived IDs (`DOC-CG-…-1`) carried the claim ID to the model | breaks doc 03 | masked as `<claim>` |
| Some FHIR documents point to a patient outside the bundle | 4 valid claims rejected | literal references accepted where content is not needed |
| The pack's CSV converter turns `280.0` into `280` | JSON types differ from the JSONL | numbers read with the JSON parser |
| A bare "approved" in the contradiction check | "the authorization is not approved" (correct R009 text) would fall back | narrowed to "claim/payment approved" |
| "always covered", "report … checks passed" patterns | false injection flags on ordinary text | patterns narrowed; benign tests added |

---

## 9. Git state

- Committed as one commit on `mak/role5-ingest-guards-ai`, branched from `main` at `ffa2f83` (after PR #14, the rules R007–R014, was merged), and pushed for review.
- Verified before the commit, with the merged rules: `python src/validate_pack.py` prints PASS, and the full suite (320 tests) passes on Python 3.10 and 3.12.
- An older local commit, `f77bebc` on `mak/ingest-malformed-input`, held only the first part (JSONL ingestion). It was never pushed and is superseded by this branch.
- The 4 interface screenshots (`*_n.png`) are not part of the commit.

---

## 10. Open items

### Waiting on Tammam (Role 1, lead)

1. Add `ExplanationProvider`, `MockExplanationProvider` and `validate_explanation` to `claimguard/_pack.py`. Until then `claimguard/ai/_adapter.py` imports `llm_adapter` directly, **the one exception to ADR-001**; afterwards one line changes.
2. Decide whether to replace the root `README.md` and widen `.gitignore` (both checksum-protected).
3. U4.4: let the audit log accept `ingestion_error`, `injection_flag` and `model_failure` events. Until then they live in their own files. They must never be logged as `request_information`, which would forge a human decision.
4. The run manifest: collect the AI fields the explainer prints, and the ingestion summary.
5. The runner (U2.6): it should read the accepted file from ingestion.

### Questions for the mentor

1. Can a held-out claim fall outside `claim.schema.json`? If so, what are its expected results? (A rejected claim produces no results, as doc 03 asks, so the scorer would report missing pairs.)
2. Is it acceptable that exercise notes (`untrusted_note`) never reach the model, by design?
3. Which date formats can held-out claims contain (DEC-010), and can they contain NaN or Infinity (DEC-003)?

### Waiting on the squad

1. Model access and model ID, then the live provider class (U2.7).
2. Scoring the 25 exercises by hand in the scorecard, for the mock, then for the model.

### Still to do by a person

1. **Rehearsal (D7):** fresh clone on another laptop, following the checklist in `docs/RUNNING.md`, section 6.
