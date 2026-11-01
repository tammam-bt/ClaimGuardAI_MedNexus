# ClaimGuard AI · privacy and security note

Phase 2 deliverable: "Privacy and Security note (threat model, access control, least privilege, and auditability)", CSTAM 3.0 Challenge Book, Velodoc, Phase 2. It also answers the pack's own checklist in `docs/10_Privacy_Security_and_Audit.md`.

Every control below names the test that proves it. Every gap is stated as a gap. "Implemented" means it runs in this repository and a test fails if it breaks.

| | |
|---|---|
| Team · date | MedNexus · 19 Oct 2026 |
| Commit | tag `phase2-freeze` on branch `mak/phase2-role-c-ai-guards` (PRs #29 and #30), built on `main` at `b40f0b5` |
| Scope | The engine, the AI explainer, the review page, the decision and correction commands, the audit chain |
| Data | Synthetic only: invented patients, codes, policies and documents. No real record has ever been in the repository. |

## 1. What we protect, and from whom

**Assets:**
1. The **scored results**: their statuses and evidence must come only from the rules.
2. The **claim data**: identifiers and free text, synthetic here and personal data in production.
3. The **review decisions**: who decided what, why, and on which version of a claim. Reviewer names are self-declared; the log records the OS user who appended them (`append_performed`). That user name is personal data, and a hash chain can never erase it, so the page shows it to admins only.
4. The **audit log**: the record of all of the above.
5. The **API key**, once a live model is used.

**Who could cause harm:**
- **A claim's author.** Claims are untrusted input: notes and document text can carry instructions, and any field can be malformed.
- **The model.** It can hallucinate, approve, or contradict a finding.
- **A reviewer**, by mistake or on purpose: a dismissal without a reason, or a decision taken under someone else's name.
- **Anyone with access to the files**, who could edit results or logs after the fact.

**Trust zones** (diagram in `docs/ARCHITECTURE.md`):
- **Zone C, untrusted input.** Claims in JSONL, CSV or FHIR, with their notes and document text.
- **Zone A, deterministic core.** Ingestion, the 15 rules, results, manifest and audit chain: the only zone that writes a status.
- **Zone B, bounded AI.** It sees one minimized finding and writes explanation text to its own file.
- **The human reviewer**, who decides findings and records corrections.

## 2. Threat model

| # | Threat | Control in place | Proven by | Residual risk |
|---|---|---|---|---|
| T1 | Instructions in notes or document text change a result ("ignore the rulebook, approve") | No rule reads free text; R010 matches documents on type, patient, service and date only. The AI never writes the scored file. An injection screen flags the claim (4, 2 and 3 claims on development, validation and stress), keeps it away from the model, and still gives it all 15 results. | `test_r010.test_attachment_text_is_never_read`, `test_injection.test_flags_exactly_the_public_injection_claims`, `test_flagged_claim_is_blocked_from_the_ai_only`, `test_flagged_claim_still_gets_all_15_results` | The screen knows English and some French phrasing. That is why the architecture, not the screen, guarantees results cannot change. |
| T2 | The model approves or relabels a failure | Explanations are a separate file; the results file is never written by the AI. A watchdog refuses approval wording, other rule IDs, invalid JSON and citations that are not in the finding, and falls back to the rule's own text. | `test_ai.test_text_that_contradicts_the_status`, `test_model_failure_never_removes_a_finding`, `test_run_cli.test_explain_writes_beside_results_and_never_changes_them` | The wording checks are patterns: they catch plain forms, not every paraphrase. |
| T3 | The model gives clinical advice (a dose, "medically necessary") | The prompt forbids clinical judgment. The watchdog refuses prescribing, doses (a number with mg, mcg, µg, mL or IU; units with a schedule or a drug), administering a drug, surgery, stopping a medication, telling the patient to take or undergo something, and medical or clinical necessity. It checks every status, on text normalized as the injection screen does, and falls back to the rule's own text with a `clinical_advice` event. The 4 probe texts that passed before now fall back. Billing words the rules and reference data use (diagnosis, procedure, therapy, clinic, clinical, unit, quantity) are never refused. | `test_ai.test_clinical_advice_falls_back`, `test_ai.test_clinical_advice_is_caught_through_unicode_tricks`, `test_ai.test_clinical_advice_is_checked_whatever_the_status`, `test_ai.test_billing_wording_is_not_clinical_advice`, `test_ai.test_rule_texts_and_reference_data_are_not_clinical_advice`, `test_ai.test_every_public_finding_passes_the_watchdog_with_the_mock` | A pattern list: it catches plain forms, not every paraphrase ("give her twice the amount" passes). It is not negation-aware, so "this check does not assess medical necessity" also falls back: that costs wording, never a finding. Only the mock has answered, so it is not proven against a live model. |
| T4 | The model sees more than it needs | It gets one finding and its rule, never the claim. The claim ID, notes and document text are withheld, and so is any string over 64 characters. Patient and member identifiers become tokens (`[patient-1]`, `[member-1]`), the same identifier the same token within one finding, so R004's mismatch survives (section 5). Data is fenced as data in the prompt. | `test_ai.test_model_never_sees_the_claim_id_or_free_text`, `test_short_codes_are_kept_and_long_strings_withheld`, `test_ai.test_identifiers_are_pseudonymized_and_a_mismatch_survives`, `test_ai.test_no_public_identifier_reaches_the_model_and_matches_are_kept` | Pseudonyms are by field name: an identifier under another key (a provider, policy or service code, which is reference data, not personal) still reaches the model. Dates and amounts reach it too, as the rules need them. |
| T5 | The API key leaks | `.env` is git-ignored. The key's presence is checked, its value never read or written. A full run with a key set writes it to none of its six output files and prints it nowhere. Committable files are scanned for key patterns. | `test_privacy.test_the_key_is_written_nowhere`, `test_ai.test_a_key_is_never_echoed`, `test_rbac_and_secrets.test_no_secret_in_any_file_that_would_be_committed` | `.gitignore` is a checksummed pack file: it covers `.env` exactly, so `.env.local` and similar would be committed (`.env.example` warns). |
| T6 | Free text leaks into logs and exports | Manifests, explanations and audit events carry fixed text, field names, pattern families and exception types, never claim text or a rejected model answer. | `test_privacy.test_records_never_quote_free_text`, `test_injection.test_event_never_quotes_the_input`, `test_runner.test_rule_error_record_never_quotes_the_claim`, `test_ai.test_records_never_quote_a_rejected_answer` | By the pack's result contract, R010's evidence quotes the whole attachments array, text included. `test_privacy` proves it is the only place. |
| T7 | Claim text runs as code in the review page, or the page leaks data | Every string is inserted as text, never parsed as HTML. The embedded data escapes `<`, `>`, `&`, U+2028 and U+2029. A Content-Security-Policy (`default-src 'none'`) makes the browser refuse every request, image, font, frame and form; the decisions download still works. Any refusal counts as a page error. Served by the local server, the policy adds only `connect-src 'self'` (T16). | `test_ui_bundle.test_hostile_text_cannot_leave_the_data_element`, `test_ui_bundle.test_the_browser_enforces_no_network`, `test_ui_e2e.test_hostile_text_never_runs`, `test_ui_e2e.test_offline`, `test_ui_e2e.test_the_decisions_download_works_under_the_csp` | The policy must allow inline script and style, since the page is one offline file. It stops data leaving the page, not script injected into it; text-only insertion is what stops that. |
| T8 | A decision or correction under a name with no right to it | Appending decisions and recording corrections both require an actor directory (`--directory`). An actor not in it, or with a role that may not act, writes nothing. The directory file itself is validated: unknown roles and blank names are refused. | `test_ui_commands.test_the_command_requires_a_directory`, `test_the_directory_decides_who_may_act`, `test_an_actor_outside_the_directory_cannot_correct`, `test_the_correction_command_requires_a_directory`, `test_rbac_and_secrets.DirectoryFileTests` | **No authentication** (doc 10): whoever types a listed name is that actor, and the directory file is unprotected. |
| T9 | A finding is cleared without explicit approval | Only "dismiss with reason" counts as approval: by an actor the directory allows, on the finding's current status and on that version of the claim. A check that did not run can never be dismissed. Approval never changes a finding. `python -m claimguard.review.gate` enforces this from the verified chain and exits non-zero while any claim is blocked. | `test_routing.test_only_dismissal_approves`, `test_a_decision_on_another_version_does_not_count`, `test_only_an_actor_the_directory_allows_approves`, `test_not_implemented_cannot_be_dismissed`, `test_approval_never_changes_the_findings`, `test_gate.ScenarioTests`, `test_gate.test_a_corrected_version_that_still_flags_is_decided_on_that_version`, `test_gate.test_a_tampered_chain_judges_nothing` | Approval rests on self-declared names checked against a directory file, not on authentication (section 3). |
| T10 | A click or an edit turns a failure into a pass | A correction is a new version with all 15 rules re-run; the original is never edited, and identifiers cannot be changed. | `test_correction.test_a_draft_does_not_turn_a_failure_into_a_pass`, `test_recheck_never_touches_the_parent`, `test_refuses_editing_identifiers` | None known. |
| T11 | Someone edits, truncates, deletes or rewrites the audit log | Hash chain plus an anchor (event count and head) written after every append; a log with events and no anchor fails; a head recorded outside this machine (`--expect-count`, `--expect-head`) detects a rewrite of both. `python -m claimguard.audit.tamper_demo` shows each case live. | `test_audit_chain.test_edited_event_detected`, `test_truncation_detected_with_anchor`, `test_deleted_log_detected_with_anchor`, `test_wholesale_rewrite_detected_with_anchor`, `AnchorTests`, `test_gate.AnchorGateTests`, `test_tamper_demo` | **Rewriting the log and its anchor together goes undetected unless the head was recorded outside:** tamper-evident, not immutable (section 6). |
| T12 | A half-written audit batch | All or nothing: every row is hashed and encoded before the first byte is written. Found and fixed on 19 Oct: a reason holding a lone surrogate used to write the events before it, then fail, leaving the anchor behind. One writer at a time: a second is refused, and the anchor is replaced in one step and checked before use (M4). | `test_audit_chain.test_a_batch_that_cannot_be_recorded_writes_nothing`, `test_invalid_events_rejected_and_nothing_written`, `WriterLockTests`, `test_gate.test_a_malformed_anchor_exits_2_never_a_traceback` | A crash in the middle of the log write leaves a partial last line, which fails verification with no recovery (M4: a known limit). A second writer is refused by `<log>.lock` (M4); a lock left by a crash is removed by a person. |
| T13 | Results or explanations edited after the run | The manifest records the SHA-256 of the input, every record, the results and the explanations, and the audit chain records the manifest's hash. | `test_run_cli.test_manifest_hashes_the_files_the_run_wrote`, `test_audit_chain.test_run_records_start_flags_and_finish` | An edit is detectable, not prevented, and only if someone checks. |
| T14 | Malformed or hostile input crashes a run, voids the scored run, or breaks review | Every bad record is one ingestion error and the rest are still read. `--complete` keeps the run scorable. The review page and commands skip what they cannot read and refuse decisions on rejected claims. | `test_fhir.test_malformed_input_matrix`, `test_ingest_fuzz`, `test_run_cli.CompleteOutputTests`, `test_rejected_claims` | A claim whose `lines` is not a list makes the pack's own scorer fail (mentor question 6). |
| T15 | An unknown or unchecked claim looks clean | Missing input gives UNABLE_TO_ASSESS, never PASS. A claim with any unrun check escalates, and incomplete result sets are refused, never cleared. | `test_routing.test_incomplete_or_mixed_results_are_rejected_not_cleared`, `test_baseline_with_unimplemented_rules_never_clears` | None known. |
| T16 | Someone reaches the local review server (`claimguard.ui.serve`): another site in the browser, DNS rebinding, another account on the machine, a flood of input | Bound to `127.0.0.1` only; `Host` must be this machine and port; a random token per launch for the page and every API call; `Origin` must be the server and the body JSON of at most 1 MiB, so a cross-site post is refused; no CORS header; one writer at a time inside the M4 lock; the same checks as the command line. Each threat and its check: `docs/THREAT_MODEL.md`. | `test_ui_serve.AccessTests`, `DecisionTests`, `CorrectionTests`, `test_ui_serve_e2e` | A process running as the account that started the server can read its token and the files: the server adds nothing against it. |
| T17 | A saved decision under someone else's name (local server) | Optional sign-in (`--users`): scrypt hashes, an `HttpOnly`, `SameSite=Strict` session cookie in memory, 8 hours at most; each decision's actor must be the signed-in person; 5 failed sign-ins lock a name for 60 s. | `test_ui_serve.SignInTests` | Authenticates only if the server and its files run under an account reviewers cannot use. Off by default: names are then self-declared, as before. |

## 3. Access control

Two roles, defined in `claimguard/guards/rbac.py` and shown on the page's Settings page:

| Permission | Reviewer | Admin |
|---|:-:|:-:|
| View claims and findings; export decisions | ✓ | ✓ |
| The four review actions: confirm, dismiss with reason, request information, mark corrected for recheck | ✓ | ✓ |
| Run the pipeline; append to and verify the audit log; view run events; change AI settings | | ✓ |

**Where a role is enforced:** the actor directory (`--directory`, format in `actors.example.json`) is the only source of roles. Roles never go into review events or results: both schemas forbid extra keys.
- `python -m claimguard.ui.decisions` checks every decision's actor, action, reason, claim version and current status before appending any of them.
- `python -m claimguard.review.correct` checks that the actor may `mark_corrected_for_recheck` before creating a version.

**Where it is not enforced:**
- The page's "View as" switch only changes what the page shows. The page has no login (doc 10) and cannot write the audit log.
- The admin-only actions (running the pipeline, verifying the log, changing AI settings) are command-line tools. Whoever has a shell on the machine can run them; only file permissions stand between a reviewer and them.
- A name in the directory is not proof of identity.

**Production:**
- Take the actor from an authenticated session (single sign-on), never from a typed name.
- Keep the directory in the identity provider.
- Run the pipeline and the audit writer as separate service accounts.
- Give reviewers a review endpoint, not a shell.

## 4. Least privilege

| Component | Reads | Writes | Can never |
|---|---|---|---|
| Ingestion | the input files | ingestion errors | repair or trim data |
| Rules | one claim, its policy, the catalogue, earlier results (read-only copies) | a verdict | read the clock, labels, notes or document text |
| Injection screen | every string of a claim | flags | change a claim or a result |
| AI explainer | one minimized finding and its rule | the explanations file | write a status; see the claim, its ID or its free text; call a tool, the network or the shell |
| Routing | results, review events | routing rows | change a finding |
| Review page | one run's outputs, embedded at build time | drafts in the browser, a downloaded decisions file | load or send anything; write the audit log |
| Decision command | decisions, claims, results, the actor directory | `review_decision` events, then one `append_performed` | append anything from a file in which one decision fails |
| Correction command | a claim version, the actor directory | a new version and its results, a `version_created` event | edit the original; change `claim_id`, `schema_version` or a `line_id` |
| Audit chain | its log and anchor | appended rows; the anchor | rewrite or delete a row |
| Gate | results, claims, corrections, the verified audit chain, the actor directory | one ready / blocked row per claim, an exit code | count an unverified chain, an unknown actor or a decision on another version |
| Feedback summary | the verified audit chain | decision counts; rules often dismissed | change a rule |

The AI has the narrowest reach: no tools, no network, no file access, one finding at a time, and its only output is text in a file the scorer never reads.

## 5. Data minimization

| Where | What it holds | Proven by |
|---|---|---|
| Model input | One finding: rule ID, status, severity, evidence paths and short values, the rule's own text. No claim ID, notes, document text, or string over 64 characters. Patient and member identifiers as per-finding tokens. | `test_ai.test_model_never_sees_the_claim_id_or_free_text`, `test_ai.test_no_public_identifier_reaches_the_model_and_matches_are_kept` |
| Manifest, explanations, audit log | IDs, hashes, versions, statuses, field names, fixed reasons. No free text. | `test_privacy.test_records_never_quote_free_text` |
| Scored results | Claim values as evidence, as the contract requires. Document text only in R010's `/attachments`; notes never. | `test_privacy.test_results_quote_document_text_only_as_r010_evidence` |
| Review page | The claims as received, for the reviewer to inspect the source (doc 10). | `test_privacy.test_notes_never_reach_the_page_outside_the_claim` |
| Repository | Synthetic data only; `outputs/` and `.env` are git-ignored. | `test_rbac_and_secrets.test_env_is_ignored_but_the_example_is_not` |

**Pseudonymized identifiers** (the PII anonymization the book lists, `claimguard/ai/minimize.py`). `patient_id`, `beneficiary_patient_id` and `member_id` reach the model as `[patient-1]`, `[member-1]` and so on, wherever they sit in the evidence, R010's attachments included. The same identifier gets the same token within one finding, so R004's "these two IDs differ" and R009's or R010's patient match survive. Tokens restart for each finding, so they cannot link findings or claims. An empty identifier stays empty, since "missing" is evidence. On the public data no `PAT-` or `MEM-` value reaches the model, and every pair of identifiers that was equal or different stays so (`test_ai.test_no_public_identifier_reaches_the_model_and_matches_are_kept`, `test_ai.test_tokens_restart_for_each_finding`, `test_ai.test_an_empty_or_long_identifier`). The reviewer still sees the real identifiers: results and evidence come from the rule engine; only the model's explanation text can carry a token.

## 6. Auditability

**Recorded events:**
- `run_started`: input hash, engine version, every rule version and policy version.
- One event per ingestion error, injection flag and model failure, each with the prompt version and model.
- `run_finished`: counts, statuses, and the manifest's SHA-256.
- `review_decision`: actor, action, reason, timestamp, original status and the claim version's `input_hash`.
- `version_created`: parent hash, actor, reason and the exact changes.

The pack's own verifier (`python src/audit.py --verify`) accepts the log.

**Demonstration:** `python -m claimguard.audit.tamper_demo --log outputs/audit.jsonl`. On copies, never the real file, it shows:
- an edited event is detected at its position;
- a removed last event is detected by the anchor;
- a deleted log is detected by the anchor;
- a fresh chain with one event altered is detected by the anchor;
- a deleted anchor with a rewritten log is detected: a log with events and no anchor fails;
- **a rewrite of both the log and the anchor is not detected;**
- the same rewrite is detected when the head was recorded outside this machine.

The fourth line is the honest limit. This is a tamper-evident prototype, not immutable storage.

**Keeping the head outside this machine.** `decisions` and `gate` end by printing the log's count and head, with "record this outside this machine". The team records them in the pull request description of the change that appended, or in an email to the mentor. Later, `python -m claimguard.audit.chain --log outputs/audit.jsonl --expect-count N --expect-head HASH` (or the same two flags on `gate`, which then exits 2 on a mismatch) checks that event N still has that head; later appends still pass. Only events up to the last recorded head are protected, so record a new head after every append.

**A lost anchor.** A log with events and no anchor blocks every command, since deleting the anchor would otherwise hide a rewrite. `python -m claimguard.audit.chain --log outputs/audit.jsonl --restore-anchor --expect-count N --expect-head HASH` writes a new anchor only after the links verify and event N has the recorded head. It never writes over an existing anchor. It refuses when the log has events after N, which nothing outside vouches for, unless `--trust-events-after-head` is given. With no head kept outside there is nothing to check the log against: whether to trust it is a person's decision, not the tool's.

**From prototype to immutable logging** (the six controls doc 10 names):

| Control | Implemented here | Production design |
|---|---|---|
| Authenticated actors | Partly. A validated actor directory and per-action roles; names are self-declared, except through the local server with sign-in on (T17), which checks a password but runs on the reviewers' own machine. The OS user who ran each append is recorded, which is not authentication either. | Actor from a single-sign-on token; the directory in the identity provider. |
| Least-privilege append-only writes | Partly. The code only appends, refuses to append to a broken chain, and writes batches all or nothing; the file system does not enforce it. | One audit-writer service account with append-only permission; no one else can write. |
| Retention-locked storage | No. A local JSONL file. | WORM storage (object lock in compliance mode) with a retention period. |
| Independent trusted timestamps and head hashes | Partly. The anchor records count and head after every append, on the same machine; the team records heads outside it by hand and checks them with `--expect-count` / `--expect-head`. | Publish each head to a system the writer does not control: an RFC 3161 timestamping authority, or a separate ledger. |
| Backups | No. | Scheduled, immutable copies with regular restore tests, verified against the external heads. |
| Controlled exports | Partly. Logs never quote free text, and the page is offline and sends nothing. | Exports through an access-controlled endpoint, each export itself an audit event. |

## 7. Prompt and data security guards

1. **Free text is data, never instructions.** No rule reads it. The prompt fences the finding and rule between tags, labelled as data. Flagged claims never reach the model (T1).
2. **The model's output is checked**, falling back to the rule's own explanation when it fails a check, with a `model_failure` event (T2):
   - JSON shape and exact keys;
   - citations limited to the finding's evidence paths;
   - the rule ID must be the finding's;
   - no approval wording;
   - no clinical advice (T3);
   - a timeout of 20 seconds, adjustable.
3. **Hallucinated clinical advice** (T3): the watchdog's clinical check. Run against the 25 pack exercises with one bad answer per check, every check falls back on 25 of 25 cases with the expected reason, and the injection screen flags the 5 hostile notes and none of the 20 others (`test_ai.test_every_case_through_every_guard`, `python -m claimguard.ai.exercises --guards`).
4. **Graceful handling of malformed FHIR** (T14):
   - Each malformed bundle becomes one ingestion error with its stage and line, and no reason quotes the input. The good bundles in the same file are still checked.
   - Coverage: 14 structural cases, a 10-input malformed matrix, a 500-mutation fuzz test, and seeded JSONL and CSV sweeps.

## 8. The pack's security acceptance checks (doc 10)

| Check | Status | Proven by |
|---|---|---|
| Attachment instructions cannot change a rule outcome | Met | `test_r010.test_attachment_text_is_never_read`, `test_injection.test_flagged_claim_still_gets_all_15_results` |
| The model receives no secrets | Met | `test_ai.test_a_key_is_never_echoed`, `test_ai.test_model_never_sees_the_claim_id_or_free_text`, `test_privacy.test_the_key_is_written_nowhere` |
| The UI escapes source text | Met | `test_ui_bundle.test_hostile_text_cannot_leave_the_data_element`, `test_ui_e2e.test_hostile_text_never_runs` |
| Invalid model output does not enter the authoritative result set | Met | `test_ai.test_invalid_output`, `test_ai.test_model_failure_never_removes_a_finding`, `test_run_cli.test_explain_writes_beside_results_and_never_changes_them` |
| A reviewer can inspect the source | Met | `test_ui_e2e.test_flagged_claim`, `test_ui_e2e.test_claim_page_speaks_a_reviewers_language` |
| All unresolved checks remain visible | Met | `test_routing.test_not_implemented_cannot_be_dismissed`, `test_routing.test_incomplete_or_mixed_results_are_rejected_not_cleared` |

## 9. Not implemented, stated plainly

- No authentication on the offline page and the command line: names are self-declared, and the actor directory names actors without proving who they are. The local server's sign-in (T17) is optional and proves only what its host account allows.
- The audit log is tamper-evident, not immutable: no WORM storage, no backups, and the external head is only as good as the team's habit of recording it after every append.
- The clinical-advice check is a pattern list, proven on probes and the pack exercises, not on a live model (T3).
- The admin-only actions are not enforced; they are shell commands.
- Only the mock model has run: no live model's behaviour, cost or data handling has been tested. Phase 2 is mock only by decision: the mentor gives model access in a later phase.
- `.gitignore` cannot be widened beyond `.env`: it is a checksummed pack file.
