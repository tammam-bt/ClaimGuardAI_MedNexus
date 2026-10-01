# Architecture decision log

Team MedNexus | CSTAM-VELODOC ClaimGuard AI

## ADR-001 | Our code lives beside the pack, not inside it

Date / authors / commit: 2026-09-26 / Tammam BenBettaieb / branch `tb/spine-skeleton`

**Context and constraint:** The starter pack ships 15 rules of which 3 are implemented, all inside one function (`base_check`) in one file (`src/engine_core.py`). Doc 06 suggests implementing further rules there. Five people must write the remaining 12 rules within one week.

**Options considered:**
1. Extend `base_check` in place, as doc 06 suggests. Simplest, matches the setup instructions, and a mentor reading the repo finds rules where his own doc says they will be.
2. A separate `claimguard/` package that imports the pack's helpers and replaces only its dispatch.
3. A separate repository for our code. Rejected immediately: `validate_pack.py` resolves its root as `parents[1]` and `config()` reads `<root>/rules`, so splitting the tree breaks both.

**Decision and rationale:** Option 2. `base_check` is a single `if`-chain; twelve rules written by four people inside it is a merge conflict per day on a seven-day budget. The pack's `src/` stays byte-identical, so `validate_pack.py` keeps verifying data integrity and release checksums, and `git diff pack-v1.0.0..HEAD` remains exact evidence of our own work.

**Data and tool permissions:** `claimguard/_pack.py` is the only module that touches `src/`. It inserts `src/` on `sys.path` once and re-exports `make_result`, `pointer`, `money`, `valid_date`, `empty`, `load_jsonl`, `config`, `validate_transport` and `STATUSES`. No other module imports from the pack. No rule mutates the claim it is given.

**Failure behaviour:** If the pack moves or is replaced, exactly one file changes. `claimguard` must be installed editable (`uv pip install -e .`): a regular install copies the package into site-packages, away from `src/`, so `_pack.py` checks for `src/engine_core.py` and raises a clear `ImportError` instead of failing obscurely. `src/` is appended to `sys.path`, not inserted first, so its generic module names (`evaluate`, `audit`) cannot shadow installed packages. `make_result` stays authoritative for result construction: it resolves every evidence pointer against the original claim, so an evidence value can never disagree with the source and `evaluate.py`'s "Evidence value mismatch" cannot fire.

**Consequences and known limitations:** We deviate from doc 06's suggestion to implement rules in `engine_core.py`. This is a suggestion, not a rule, and `validate_pack.py`'s own checksum message anticipates intentional edits. Our README lives at `.github/README.md`, which GitHub displays in preference to the root file. Replacing the root `README.md`, or widening the pack's `.gitignore`, would break `validate_pack.py`, which stops at the first checksum mismatch and so would leave every later pack file unchecked; `.env.example` documents the one ignored name instead. No existing pack file is modified; new files are added under the pack's `tests/` directory. Anyone reading the pack's docs must be told that rules live in `claimguard/rules/`.

**Verification evidence:**
```
uv pip install -e .
python -c "from claimguard._pack import make_result, money; print(money('1510.005'))"   -> 1510.01
python -c "import claimguard; print(claimguard.__version__)"  (from /tmp)              -> 0.1.0
```

## ADR-002 | Rules self-register; nothing central lists them

Date / authors / commit: 2026-09-26 / Tammam BenBettaieb / branch `tb/spine-skeleton`

**Context and constraint:** Twelve rules, three authors, one week. Any file that every author must edit becomes a conflict point and a serialization point.

**Options considered:**
1. A dict literal mapping rule IDs to functions, maintained by hand.
2. An `__init__.py` importing each rule module explicitly.
3. `@rule("Rxxx")` decorators plus `pkgutil` auto-discovery at package import.

**Decision and rationale:** Option 3. An author adds `r013.py` and it registers itself; no shared file is touched, so two people adding two rules never conflict. Options 1 and 2 both reintroduce the single-file bottleneck we left `base_check` to escape.

**Data and tool permissions:** `claimguard/rules/__init__.py` imports every module in its own package and nothing else. The registry holds callables only; it reads no data and performs no I/O.

**Failure behaviour:** The known hazard of a decorator registry is silence — an unimported module registers nothing and its rule reports `NOT_IMPLEMENTED` with no error. Two guards: auto-discovery removes the "forgot to add the import" case, and `rule()` raises `RuntimeError` on a duplicate registration rather than overwriting. The runner iterates `config()['rules']`, so a genuinely absent implementation still emits exactly one `NOT_IMPLEMENTED` result and the claim-rule pair count stays at 15.

**Consequences and known limitations:** Modules whose names start with an underscore are skipped, which is how `rules/_template.py` ships without registering. Import order across rule modules is not guaranteed, so no rule may depend on another at import time. Cross-rule dependencies (R009 reads R008's per-line outcome) are handled at evaluation time through `RuleContext.prior`, not through imports.

**Verification evidence:**
```
python -c "import claimguard.rules; from claimguard.engine.registry import REGISTRY; print(sorted(REGISTRY))"  -> []
```
Empty is the expected result before any rule module exists, and proves discovery runs without finding anything.

## ADR-003 | One accumulator owns precedence, messages and evidence

Date / authors / commit: 2026-09-26 / Tammam BenBettaieb / branch `tb/spine-skeleton`

**Context and constraint:** The three baseline rules each re-implement the same logic with three different accumulator styles: R003 keeps lists of failures and unknowns, R006 a boolean `missing` flag, R001 a path list with a default substituted on PASS. Twelve more rules by three authors would produce twelve more variations of the precedence law, and the scorer rejects results for missing evidence, blank explanations and foreign line IDs.

**Options considered:**
1. Each rule returns a complete result dict via `make_result`, as the baseline does.
2. A shared helper function for precedence only.
3. A `Findings` accumulator that owns precedence, message composition, evidence ordering and line-ID ordering, and asserts the scorer's remaining rejection conditions.

**Decision and rationale:** Option 3. Every rule follows the same five moves (seed evidence, accumulate, apply precedence, compose the message, build the result); only the second varies. Centralising the other four makes precedence impossible to get wrong per rule and turns four `evaluate.py` rejections into assertion failures inside our own tests, with a stack trace pointing at the rule responsible.

Two conventions are taken from the gold data rather than chosen: across 9,000 public expected results, `affected_line_ids` appear only on FAIL (never on UNABLE_TO_ASSESS, PASS or NOT_APPLICABLE), and multi-line IDs are always in claim line order (62 of 62). So `unknown()` accepts no line ID, and `verdict()` orders line IDs by claim position whatever the call order.

**Data and tool permissions:** `Findings` reads the `RuleContext` it was given and nothing else. It performs no I/O.

**Failure behaviour:** `verdict()` raises `AssertionError` for an invalid status, a blank message, empty evidence or a line ID not in the claim. A rule that cannot produce a valid result fails loudly in tests instead of producing a run that `evaluate.py` rejects wholesale.

**Consequences and known limitations:** Rules whose baseline messages are fixed strings (R001, R006) pass `message=` to override composition. Byte-identical reproduction of the baseline output is the acceptance test for this design (Block D).

**Verification evidence:** `tests/test_engine.py` encodes the full `verdict()` contract as 15 tests marked `expectedFailure` until Block C1 implements it.

## ADR-004 | Policies resolve exactly, with no fallback, and are frozen

Date / authors / commit: 2026-09-26 / Tammam BenBettaieb / branch `tb/u2.4-policy`

**Context and constraint:** Seven rules (R005, R008, R009, R010, R013, R014, R015) read the claim's policy. The public data contains an unrecognised `policy_id`, `EDU-NO-POLICY`, on 15 of 600 claims. The rulebook: *"An unrecognized policy_id means no matching policy was supplied, not proof of non-coverage."*

**Options considered:**
1. Fall back to a default policy (e.g. EDU-BASIC) when the ID is unknown.
2. Resolve exactly; return `None` for an unknown ID and let each rule abstain.
3. Normalise the ID (trim, fold case) before lookup.

**Decision and rationale:** Option 2. A fallback invents coverage terms the claim never had, which is exactly what the rulebook forbids. Normalising (option 3) breaks the rulebook's instruction not to silently trim or repair source data, and its statement that exact identifiers are case-sensitive.

Policies are also deep-frozen on load (`MappingProxyType`, lists to tuples). The same two policy objects serve every claim in a run, so a rule that mutated one, for instance appending to `allowed_providers`, would silently change results for every later claim. Frozen, that raises `TypeError` or `AttributeError` at the offending line.

**Data and tool permissions:** `PolicyBook` reads `rules/policies.json` once per run through `config()`. It never writes. Rules receive a read-only view.

**Failure behaviour:** Unknown `policy_id` → `None`, and rules record an unknown. A `policies.json` entry whose key disagrees with its own `policy_id` raises `ValueError` at load, before any claim is evaluated.

**Consequences and known limitations:** Frozen policies are not JSON-serialisable. This does not matter today, since evidence pointers resolve into the claim, never the policy. The claim has no policy-version field, so resolution is by ID only; policy version switching (a pack stretch goal) would need a new envelope field.

**Verification evidence:** `tests/test_policy.py`: all 600 public claims resolve exactly when their policy exists, and exactly 15 resolve to `None`.

## ADR-005 | Ingestion checks each line on its own, against the full claim schema

Date / authors / commit: 2026-10-01 / Mohammed Aziz Kadri / branch `mak/ingest-malformed-input`

**Context and constraint:** `src/run_baseline.py` calls `validate_transport()` on every claim with no guard, so one malformed line aborts the run for every claim. Doc 03: a malformed JSON line, wrong structural type, duplicate line ID or missing transport key "is an ingestion error: quarantine it and report it separately, never silently drop it or create a passed claim." `validate_transport()` also lets through inputs that later break the run or behave differently per Python version: NaN and Infinity, which make `evaluate.py` reject the whole run (DEC-003); dates such as `20260525` that only Python 3.11+ reads (DEC-010); and non-object or incomplete coverage, authorization and attachment records (DEC-012).

**Options considered:**
1. Wrap `validate_transport()` in `try/except` and nothing more.
2. Add hand-written checks for each hostile input found so far.
3. Check each line against `validate_transport()` and then `schemas/claim.schema.json`, read from the file.

**Decision and rationale:** Option 3. Option 1 fixes the crash but leaves every input behind DEC-003, DEC-010 and DEC-012 in the run. Option 2 is a list that grows with each attack. The schema already forbids all three: numbers must be finite, dates are `format: date`, and every nested record has required keys and `additionalProperties: false`. Enforcing it cannot cost a legitimate claim: QA_REPORT.md states that all 800 claims, the mentor's 200 held-out ones included, were checked against it, and `tests/test_ingest.py` confirms that all 600 public claims are accepted unchanged. A date must match `[0-9]{4}-[0-9]{2}-[0-9]{2}` (ASCII digits only; `\d` also matches fullwidth digits) and be a real calendar date, so every rule sees the same input on 3.10 and 3.12. Duplicate JSON keys are rejected, because `json.loads` silently keeps the last one and a reviewer reading the raw line could see a different value from the engine's.

**Data and tool permissions:** `claimguard.ingest` reads the input file and `schemas/claim.schema.json`, and writes nothing unless run as a command. It imports from the pack only through `claimguard._pack`. The schema check implements exactly the keywords `claim.schema.json` uses and raises at import if the schema ever uses another, rather than ignoring it.

**Failure behaviour:** A rejected line becomes an ingestion-error record, `{event, stage, reason, claim_id, provenance}`, with `stage` one of `decode`, `json`, `transport`, `contract` or `duplicate_claim_id`. Every other line is still read. A reason never quotes the input: it names a JSON pointer built from schema keys and array indices only, and a `claim_id` outside the public shape is reported as `null`, so untrusted text cannot reach a log or UI through an error. `python -m claimguard.ingest` writes the accepted lines' original bytes, unchanged, to `outputs/accepted.jsonl`, which the pack's runner and scorer read with every evidence value intact. It writes the errors to `outputs/ingestion_errors.jsonl` and exits 0.

**Consequences and known limitations:** Provenance (adapter, adapter version, source file and its SHA-256, line number, SHA-256 of the line's original bytes) travels beside the claim in `Ingested`, never inside it, because `validate_transport()` rejects any extra envelope key. Ingestion errors are not yet in the audit chain: `src/audit.py` accepts only the four review actions until U4.4 (Role 1) extends it. They must never be logged as a review action such as `request_information`, which would forge a human decision. A rejected claim produces no results. That is what doc 03 asks, but if the mentor's claims file ever contains a claim this check rejects, `evaluate.py` will report missing pairs. **Question for the mentor:** can a held-out claim be outside `claim.schema.json`, and if so, what are its expected results? The same contract check backs the CSV adapter (`claimguard/ingest/csv_folder.py`), which assembles each claim from the five CSV files and rejects only the claim a bad row belongs to, and the FHIR adapter (ADR-008). `adapter` in the provenance names which one produced a claim.

**Verification evidence:** `tests/test_ingest.py`, 21 tests, passing on Python 3.10 and 3.12. Among them: the pack's runner exits non-zero on a file with one broken line, while `python -m claimguard.ingest` reads it, and the runner then produces 3 × 15 results from the accepted file.

## ADR-006 | Injection text is flagged, not quarantined, and the flag keeps it from the model only

Date / authors / commit: 2026-10-01 / Mohammed Aziz Kadri / U6.4

**Context and constraint:** Docs 03, 05 and 10: notes and attachment text are data, never instructions; "attachment instructions cannot change a rule outcome". The public data carries one injection sentence, on 9 of 600 claims, and those claims have ordinary expected results (CG-116C84D4774D: R012 FAIL). `evaluate.py` rejects a run that omits any claim. Docs 03 and 10 use "quarantine" for ingestion errors: claims that are not read.

**Options considered:**
1. Quarantine claims with instruction-like text: remove them from the run.
2. Flag them: run all 15 rules as usual, keep them away from the model, show the flag to the reviewer.

**Decision and rationale:** Option 2. Option 1 loses their scored results and makes `evaluate.py` reject the whole run. The real protection is architectural: rules never read free text, and the model's output is validated and kept out of the results (ADR-007). `claimguard.guards.screen()` is a layer in front of the model. It scans every string in the claim, as written and decoded (HTML, percent, escapes, base64, hex, ROT13, reversed), normalized (NFKC, combining marks, zero-width characters, Cyrillic and Greek lookalikes), squashed (separators removed, leetspeak mapped) and joined across fields in both directions.

**Data and tool permissions:** reads a claim, writes nothing; never modifies the claim.

**Failure behaviour:** A hit names a JSON pointer, a pattern family and the decoding layer, never the text. On public data: the 9 injection claims flagged, 0 of the other 591; on the 25 exercise cases: the 5 hostile notes flagged, 0 of the 20 benign.

**Consequences and known limitations:** English patterns plus a few French forms. An instruction phrased otherwise, or in another language, passes the filter; it still cannot change a result.

**Verification evidence:** `tests/test_injection.py`.

## ADR-007 | The model sees one minimized finding, every answer passes a watchdog, and explanations live beside the results

Date / authors / commit: 2026-10-01 / Mohammed Aziz Kadri / U2.7, U3.5, U3.7, U6.3

**Context and constraint:** Brief: "Do not relabel deterministic failures through an LLM." Docs 07 and 10: a model failure cannot remove a deterministic finding; invalid model output never enters the authoritative results; the model gets only the required evidence and rule excerpt. `prompts/explain_findings.md`: fall back on invalid JSON, unknown citations, timeout or model failure. Model access is still a team decision, so everything is built against the pack's mock.

**Options considered:**
1. Write the model's explanation into the result rows' `explanation` field.
2. Keep explanations in their own file keyed by (claim_id, rule_id); the result rows are only read.

**Decision and rationale:** Option 2: no model answer or failure can reach `evaluate.py`'s input. Only FAIL and UNABLE_TO_ASSESS results are explained, and never on a flagged claim (ADR-006). The model receives the finding and rule only (`minimize.py`): no claim ID (also masked inside derived IDs such as `DOC-<claim>-1`), notes and attachment text withheld, any string over 64 characters withheld, evidence paths unchanged so citations can be checked. Every answer then passes `watchdog.py`: timeout, provider error, invalid JSON, the pack's `validate_explanation()`, text presenting a FAIL or UNABLE_TO_ASSESS finding as passed, text naming another rule.

**Data and tool permissions:** the provider is called with the minimized finding and rule, and nothing else. No tool use, no network beyond the provider. The API key is checked for presence only and never logged.

**Failure behaviour:** Anything but a passing answer gives the rule engine's own explanation, `source: fallback`, and a `model_failure` event naming the reason. Neither quotes the rejected answer or the provider's error message. A timeout uses a daemon thread, so a hung provider cannot hold up the run.

**Consequences and known limitations:** `claimguard/ai/_adapter.py` imports the pack's `llm_adapter` directly, the one exception to ADR-001, until those three names are added to `_pack.py`. The contradiction checks are heuristics. Exercise notes never reach the model, by design. The live provider is not written.

**Verification evidence:** `tests/test_ai.py`. With the mock on all public data: 777 FAIL/UNABLE_TO_ASSESS findings, 0 false fallbacks.

## ADR-008 | A FHIR bundle is accepted only if it rebuilds its normalized claim exactly

Date / authors / commit: 2026-10-01 / Mohammed Aziz Kadri / U1.4, U6.5

**Context and constraint:** Doc 01 requires one FHIR mapping example. Doc 11: FHIR alone cannot reproduce all 15 checks; notes and authorization details stay in the normalized sidecar. Some records deliberately reference a document patient outside the bundle, a business inconsistency for the rules, not a malformed bundle.

**Options considered:**
1. FHIR wins where both have a value; the sidecar fills the gaps.
2. Build the envelope from FHIR plus the sidecar's `schema_version`, `notes` and `authorizations`, and require it to equal the sidecar claim field for field, with the same JSON types.

**Decision and rationale:** Option 2. The scorer reads the normalized file, so any difference would break evidence values; choosing a side would be guessing (doc 04: "Do not silently trim or repair source data"). The mapping, documented in `claimguard/ingest/fhir.py`, rebuilds all 600 public claims exactly, key order included. A reference must resolve only where its content is needed (Claim.patient, Claim.insurance.coverage); others are read from their URL.

**Data and tool permissions:** reads the bundles file and the sidecar file; writes nothing unless run as a command.

**Failure behaviour:** Any bundle outside the projection is an ingestion error with stage `fhir` (structure) or `fhir_mismatch` (differs from the sidecar, or authorization IDs differ from `preAuthRef`), naming the element or JSON pointer, never the value. 500 seeded random mutations never crash the run and never yield an envelope that differs from the sidecar.

**Consequences and known limitations:** Not HL7 validation; the document service code is read from `description`, a convention of this projection. Provenance records both files and lines.

**Verification evidence:** `tests/test_fhir.py`.

## ADR-009 | One command; the run survives bad input and failing rules, and says so

Date / authors / commit: 2026-10-01 / Tammam BenBettaieb / branch `tb/u2.6-runner`

**Context and constraint:** The mentor scores our code on 200 held-out claims. The pack's `run_baseline.py` stops at the first claim that fails `validate_transport`, and a crash means no score. Ingestion, the injection screen and the AI explainer each had their own command passing files between them.

**Options considered:**
1. Keep separate commands; document the order.
2. One command that crashes on the first problem, as the baseline does.
3. One command: ingest → 15 rules → screen → optional explain → manifest → audit; bad records are recorded ingestion errors; a rule exception is an UNABLE_TO_ASSESS for that one result, recorded; `--strict` re-raises.

**Decision and rationale:** Option 3. A reviewer runs one thing and gets one manifest. A rejected record is a claim never checked; it is not reported as fifteen abstentions, and `evaluate.py` shows the gap. A rule exception is the mentor's "safe state": that result abstains and asks a human rather than taking down the run. CI runs `--strict`, so no such error merges unnoticed.

**Data and tool permissions:** Reads the input and config; writes results, manifest, explanations and audit events. Rules receive a read-only deep copy of earlier results.

**Failure behaviour:** Exit code 0 when clean, 2 when anything was rejected or any rule failed, each listed in the manifest. A run's audit events are appended in one batch at the end.

**Consequences and known limitations:** In production a rule bug degrades to abstentions rather than failing loudly; the manifest's `rule_errors` must be read.

**Verification evidence:** `tests/test_runner.py`, `tests/test_run_cli.py`; status accuracy 1.0 on all three public splits; the three adapters give the same results.

## ADR-010 | Typed, hash-chained audit events with an anchored head

Date / authors / commit: 2026-10-01 / Tammam BenBettaieb / branch `tb/audit-chain`

**Context and constraint:** Phase 1 awards 10 points for an "auditable, immutable log of all checks … and system decisions". The pack's `audit.py` chains four review actions only and cannot detect truncation or deletion, as its own CLI says.

**Options considered:**
1. Use `src/audit.py` unchanged.
2. A database with append-only permissions.
3. Our own chain: the pack's row format and hash, typed events on the team's `"event"` key, a head anchor written after every append.

**Decision and rationale:** Option 3. The pack's verifier still accepts our logs. The team's ingestion, injection and model-failure records go in unchanged. The anchor closes the truncation and deletion gap. A database adds a dependency and still needs the same tamper evidence.

**Data and tool permissions:** Append only.

**Failure behaviour:** `append` refuses a chain that does not verify and writes nothing if any event in a batch is invalid. `verify` raises on a broken link, on fewer events than the anchor recorded, and on a head that differs from the anchor.

**Consequences and known limitations:** Tamper-evident, not immutable; single writer; production needs WORM storage and an anchor held outside the system.

**Verification evidence:** `tests/test_audit_chain.py`.
