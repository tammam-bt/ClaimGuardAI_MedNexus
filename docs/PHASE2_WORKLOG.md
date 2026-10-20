# Phase 2 work log · 19 October 2026

What was audited, built, fixed and decided for Phase 2 (Integration and Testing, 30 points), on top of `main` at `b40f0b5`. The authoritative scope is the CSTAM 3.0 Challenge Book, Velodoc pages 17 to 19.

| | |
|---|---|
| Roles done | A Evaluation · B Robustness and FHIR · D Review gate, including decisions on a corrected version · E Privacy and access · C AI guards (C1 clinical-advice check, C2 exercises through every guard, pseudonymized identifiers in the model's view, C4 manual scorecard) |
| Role C open | C3 live provider (later phase: the mentor gives the key; Phase 2 is mock only) |
| Frozen | tag `phase2-freeze`, 20 Oct 2026 (section 10) |
| Tests | 510, all passing on Python 3.14, including 19 headless-Chrome tests. CI runs 3.10 and 3.12. |
| Pack integrity | `python src/validate_pack.py`: PASS. No starter-pack file changed. |
| Scores | Status accuracy 1.000, macro F1 1.000 and 0 false alarms on all three public splits (details below) |
| Author | Mohammed Aziz Kadri, with an AI coding assistant (see the end of this log) |

## 1. What Phase 2 asks

From the book (page 18):

| Block | Points | Requirement |
|---|---|---|
| Detection Quality and Benchmark Performance | 15 | High macro F1 across rule categories on "the validation dataset (50 claims)"; preserve valid claims (low false-positive rate) |
| Human-in-the-Loop and Escalation Logic | 10 | Route low-confidence or high-severity cases for explicit human approval; manual overrides; feedback logging |
| Privacy, Security and Safety Guards | 5 | Data minimization; access control; prompt/data security guards, including against hallucinated clinical advice; graceful handling of malformed FHIR |
| Deliverables | — | A test evaluation report (detection metrics, F1, false-positive rate, latency, limitations) and a privacy and security note (threat model, access control, least privilege, auditability) |

Phase 3 (10 points: UI/UX, technical report, demo video) and Phase 4 (pitching) are out of scope here.

## 2. The audit before the work

A fresh clone of `b40f0b5` passed 418 tests, and the engine scored 1.000 on every split. The eight findings of the earlier audit were checked against the code:

| Finding | Verdict |
|---|---|
| No macro F1; `rules/rules.json` has no category | Confirmed |
| `templates/Evaluation_Report.md` is empty | Confirmed |
| The AI watchdog accepts clinical advice | Confirmed: 4 of 4 probes accepted. Fixed by C1: all 4 now fall back |
| `routing.outstanding()` ignores the claim version | Confirmed; it also accepted unknown actors |
| `ui/decisions.py` makes everyone a reviewer by default | Confirmed |
| One claim that fails ingestion voids the scored run | Confirmed: "15 missing pairs", run rejected |
| No privacy and security note with a threat model | Confirmed |
| The 5 browser tests are skipped | Refuted: with Node and Chrome installed they run and pass |

## 3. What each role built

### Role A · Evaluation

| | |
|---|---|
| `claimguard/evaluation/summary.py` | `python -m claimguard.evaluation.summary`: macro F1 over rules and over categories (rules without a FAIL are listed as undefined, never counted), false-alarm claims, clean claims sent to a reviewer, claim exact match, and latency from the run manifest (refused if the manifest belongs to another run) |
| `claimguard/evaluation/categories.json` | The grouping, in the book's own words: missing (R001, R008, R010), inconsistent (R002, R004, R007, R012, R015), duplicate (R006), unsupported (R003, R005, R009, R011, R013, R014). Pending the mentor's confirmation. |
| `docs/EVALUATION_REPORT.md` | The deliverable, following the template's sections: metrics, starter-baseline comparison, latency including a 4,000-claim scale run, five hard cases, robustness, AI evaluation, the confidence mapping, the held-out protocol, limitations, per-rule tables in Appendix A |
| Tests | `tests/test_summary.py` (13) |

### Role B · Robustness and FHIR

| | |
|---|---|
| `python -m claimguard.run --complete` | A claim rejected at ingestion still gets 15 UNABLE_TO_ASSESS results, so one malformed held-out claim no longer voids the run. Claim IDs are read the way the scorer reads them, including unusual ones. FHIR completes only sidecar claims; CSV orphan rows are skipped; refused together with `--limit`. Off by default; recorded in DEC-013. |
| `claims_by_id()` | A tolerant claims reader: the review page, the decision command and the correction command no longer crash on a malformed claim |
| Tests | 10-case malformed-FHIR matrix and "one bad bundle never costs the others" (`tests/test_fhir.py`); seeded JSONL and CSV mutation sweeps (`tests/test_ingest_fuzz.py`); `CompleteOutputTests` in `tests/test_run_cli.py`; `tests/test_rejected_claims.py` |
| Scale | 4,000 claims at 7.9 to 9.1 ms a claim, linear |

### Role D · Review gate

| | |
|---|---|
| D1 | `outstanding(routing, events, *, input_hash=None, directory=None)`: a dismissal counts only on that version of the claim and by an actor the directory allows |
| D6 | Each routing reason names its triggers, `low_confidence`, `high_severity` or `issue`, in the book's words; shown on the claim page. Routing policy 1.1.0; the route table is unchanged. |
| D2 | `python -m claimguard.review.gate`: verifies the audit chain, judges each claim on its latest version, and reports ready or blocked in the page's own state names. Exits 0, 1 or 2. On development with no decisions it reports 136 ready and 264 blocked, exactly the dashboard's numbers. |
| D5 | `python -m claimguard.review.feedback`: decisions by action, rule and actor, plus rules often dismissed, raised with the mentor and never changed automatically |
| CSP | The review page carries a Content-Security-Policy (`default-src 'none'`). The browser test proves the decisions download still works and counts any refusal as an error. |
| Tests | `tests/test_gate.py`, `tests/test_feedback.py`, new tests in `tests/test_routing.py`, a Python/JavaScript parity test for `outcome` in `tests/test_ui_core.py`, a download check in `tests/ui_e2e.mjs` |

### Role E · Privacy and access

| | |
|---|---|
| `docs/PRIVACY_SECURITY.md` | The deliverable. 15 threats, each with its control, the test that proves it and the residual risk; access control; least privilege; data minimization; auditability with doc 10's six-control immutable-logging design; doc 10's six security acceptance checks. A test fails if the note cites a test that does not exist. |
| E2 | `--directory` is required to append decisions and to record corrections. Before, corrections accepted any typed name. Directory files are validated; `actors.example.json` shows the format. |
| E3 | `tests/test_privacy.py`: a full run with an API key set. The key appears in none of the six output files, and no log contains claim free text. |
| E5 | `python -m claimguard.audit.tamper_demo`: an edit, a removal, a deletion and a rewrite are each detected; a rewrite of the log and its anchor together is not, which shows the "tamper-evident, not immutable" limit |

## 4. Bugs found and fixed

| Bug | Where | Fix |
|---|---|---|
| A string holding a lone surrogate (`"\ud800"`, legal JSON) crashed the results write: the run produced nothing | `claimguard/run.py` | Such a row is written with ASCII escapes; it reads back identical |
| An audit batch could be half-written: valid events were appended, then the batch failed and the anchor was not updated, while the command reported nothing appended | `claimguard/audit/chain.py` | Every row is hashed and encoded before the first byte is written |
| One malformed claim in the claims file made every decision append fail, and crashed the review page with `--complete` | `claimguard/ui/decisions.py`, `claimguard/ui/bundle.py` | Tolerant reader; rejected claims are listed, and a decision on them is refused with a reason |
| Corrections accepted any actor name | `claimguard/review/correct.py` | The actor must be in the directory with the right role |
| `--complete` missed unusual claim IDs and gave incoherent output with `--limit` | `claimguard/run.py` | IDs are read as the scorer reads them; `--limit` refused |

## 5. Decisions taken (defaults until the mentor answers)

| Question | Default |
|---|---|
| Which set is "the validation dataset (50 claims)"? | Report validation (150) as the headline and stress (50) separately |
| Macro F1 "across rule categories" | Report both: over the 15 rules, and over the four categories in `categories.json` |
| What a rejected held-out claim returns | Use `--complete` (15 UNABLE_TO_ASSESS) and disclose it (DEC-013) |
| The book's "confidence score" | Keep `confidence: null` (the pack's scorer refuses a number on a deterministic result); low confidence means the engine abstained, and the routing triggers say so |
| What counts as a "valid claim" | Both definitions reported: no expected FAIL (62 on validation), or all PASS/NOT_APPLICABLE (53); 0 flagged under either |
| Model access | Mock only, stated in the report |

## 6. Results

| | development | validation | stress |
|---|---:|---:|---:|
| Status accuracy | 1.000 | 1.000 | 1.000 |
| Macro F1 over rules | 1.000 (15 defined) | 1.000 (15 defined) | 1.000 (6 defined) |
| Macro F1 over categories | 1.000 | 1.000 | 1.000 (3 defined) |
| False-alarm claims | 0 of 160 | 0 of 62 | 0 of 24 |
| Clean claims sent to a reviewer | 0 of 136 | 0 of 53 | 0 of 12 |
| Run time with explanations (mock) | 3.2 s | 1.2 s | 0.4 s |

The starter baseline scores macro F1 0.200 over rules on validation and sends all 53 clean claims to a reviewer. The public labels come from the pack's reference engine: a perfect score means agreement with it, not independent validity.

## 7. Traps met, for the rest of the team

- **Checksummed pack files.** `templates/`, `exercises/`, `prompts/`, `.gitignore`, the numbered `docs/NN_*.md`, `README.md` and `rules/*.json`: editing any of them fails `validate_pack.py` and CI. That is why the report and the note are new files under `docs/`.
- **`tests/test_confusion.py` pins the keys `confusion_by_rule()` adds.** New metrics go in a separate module.
- **Python versions differ.** A 5,000-deep JSON input is rejected as `json` on 3.10 to 3.12 but `fhir` on newer versions; test on 3.10 or 3.11, not only 3.14.
- **Line endings.** Python's `write_text` on Windows writes CRLF; `.gitattributes` wants LF.
- **In `claims.csv` the claim ID is the second column**, after `schema_version`.
- **The pack's gold cannot be scored against a modified claims file**, because it quotes the original values.
- **The repository's secret scan flags `sk-ant-` followed by 20 or more characters**, even in tests; build fake keys at runtime.
- **The pack's own scorer crashes on a claim whose `lines` is not a list**, whatever the predictions (mentor question 6).

## 8. Still to do

| Item | Owner |
|---|---|
| C3: a live provider behind `select_provider`, in a later phase, once the mentor gives the key. Phase 2 is mock only | Role C |
| C4: a second teammate checks the judged columns of `docs/llm_manual_scorecard_mock.csv` | Role C |
| Merge PRs #29 and #30 into `main` (merge commits, so the tag stays in `main`'s history) | Tammam |
| Mentor answers: the 50-claim set, the category grouping, `--complete` for the held-out run, the confidence wording, `lines` that is not a list | Team |
| Run once from a fresh clone on another laptop | Team |

## 9. New commands

```bash
python -m claimguard.run --complete --input <claims.jsonl> --output <pred.jsonl> --explain --audit-log <audit.jsonl>
python -m claimguard.evaluation.summary --split validation --gold <expected.jsonl> --pred <pred.jsonl> --claims <claims.jsonl> \
    --manifest <pred.jsonl>.manifest.json --markdown <summary.md>
python -m claimguard.review.gate --results <pred.jsonl> --claims <claims.jsonl> --log <audit.jsonl> --directory actors.json
python -m claimguard.review.feedback --log <audit.jsonl>
python -m claimguard.audit.tamper_demo --log <audit.jsonl>
python -m claimguard.ui.decisions ... --directory actors.json      # now required
python -m claimguard.review.correct ... --directory actors.json    # now required
```

## 10. Finishing Phase 2 · 20 October 2026

| Item | What was done |
|---|---|
| C4 manual scorecard | `docs/AI_SCORECARD.md` and `docs/llm_manual_scorecard_mock.csv`: the 25 exercises scored on the five criteria of docs/07, with the rubric written down. Finding 24/25, evidence 25/25, rule 25/25, action 0/25, uncertainty 22/25, no unsupported fact. `tests/test_scorecard.py` recomputes the mechanical columns from a fresh run, and checks that the write-up's totals match the card. |
| Decisions on a corrected version (Role D) | A corrected version that still flagged findings could never be approved: the page stopped at "rechecked", and the decision command accepted only the claim as received. Now the page decides on the latest version (`Core.current`), `python -m claimguard.ui.decisions --corrections` checks decisions against it, and the gate judges it. A decision on an older version is refused. |
| Page and gate disagreed | A correction that cleared every finding showed "Rechecked" on the page while the gate said ready, because the page judged version 1. Both now judge the latest version, and the parity test covers versions. |
| README and CI | `.github/README.md` lists the Phase 2 commands, `--directory` and the deliverables. CI also scores validation and stress. |
| Freeze | The numbers were re-run from the tag on all three splits and are unchanged. The report and the note name the tag. |

Checked in a real browser on a two-claim run: correct, rebuild, dismiss both v2 findings on the page, append, gate. The command refuses those decisions without `--corrections` and accepts them with it. The gate then exits 0, and the pack's `src/audit.py --verify` accepts the chain.

## 11. Use of AI coding tools

CSTAM allows AI tools if the team understands, validates and can explain every line (`CONTRIBUTING.md`, section 7). This Phase 2 work was produced with Claude Code, an AI coding assistant, directed and reviewed by Mohammed Aziz Kadri:
- Every change was written test-first or with its test.
- The full suite was run after each role.
- Behaviour was verified by running the real commands on the public data.

The bugs in section 4 were found by tests and probes, not assumed. Whoever presents a part of this work must be able to explain it in Q&A.
