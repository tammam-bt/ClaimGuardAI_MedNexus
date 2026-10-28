# ClaimGuard AI · readiness note (version 1)

Track A's must-do fixes M0 to M5 are in: 14 of the 15 items of the readiness bar hold, each with a test or a command that fails if it breaks. The one left is page copy, moved to the redesign (P3). None of it is on `main` yet: PRs #31 to #34 are open, each green on Python 3.10 and 3.12.

This note separates what is implemented and tested, what is only documented, and what nobody outside the team has verified. "Accuracy 1.0" means our statuses agree with the pack's reference labels on the three public splits. It does not mean the rules are clinically or contractually right, and nobody has scored the hidden split.

| | |
|---|---|
| Team · date | MedNexus · 26 Oct 2026 |
| Commit | branch `mak/m8-readiness`, on `mak/m5-append-performed` at `b87e4e7` (PRs #31 → #32 → #33 → #34, stacked, open) |
| Pack | ClaimGuard AI starter pack 1.0.0, `validate_pack.py` PASS |
| Plan | Master plan revision 4, Track A; next versions of this note come with P8 (v2) and B5 (v3) |

## 1. Readiness bar

| Item | Holds | Evidence |
|---|---|---|
| `validate_pack.py` passes | Yes | Regression run (section 2); CI step "Starter pack integrity" |
| CI green on 3.10 and 3.12, e2e running | Yes | GitHub checks `check (py3.10)` and `check (py3.12)` succeed on all four PR heads. `REQUIRE_E2E=1` makes a missing Node or Chrome a failure: `test_ui_e2e` (M7) |
| Accuracy 1.0 on all three public splits | Yes | Section 2: development 6,000, validation 2,250, stress 750 results; 0 FP, 0 FN, 0 not implemented |
| No accepted claim is missing a row; an unreadable row fails closed | Yes | `test_csv.test_an_unparseable_child_row_rejects_every_claim`, `test_ingest_fuzz.test_mutated_csv_never_crashes_and_stays_scorable` (M0) |
| A NUL in a CSV row gives the same result on every version | Yes | `test_csv.test_nul_rejects_only_its_claim_on_every_version`, run on 3.10 and 3.12 (M0) |
| No tracked `.env*` file at any depth but `.env.example` | Yes | CI step and `test_rbac_and_secrets.test_no_env_file_but_the_example_would_be_committed` (M1) |
| `tamper_demo`: missing anchor detected | Yes | Section 2; `test_tamper_demo.test_every_scenario_behaves_as_stated` |
| `tamper_demo`: both files rewritten, NOT detected | Yes, as stated | Same. This is the limit, shown on purpose |
| `tamper_demo`: both rewritten, head held outside, detected | Yes | Same (M3) |
| A lost anchor is restored only against a head kept outside, for events up to it | Yes | `test_audit_chain.AnchorTests` (M3) |
| The gate exits 2 on a broken chain, a head mismatch or any malformed anchor, never a traceback | Yes | `test_gate.AnchorGateTests`, `test_gate.test_a_malformed_anchor_exits_2_never_a_traceback` (M4); section 2 |
| A second writer is refused | Yes | `test_audit_chain.WriterLockTests` (M4); section 2 |
| Every append records the OS user who ran it, including `run`, and only admins see it | Yes | `test_audit_chain.AppendPerformedTests`, `test_ui_commands`, `test_ui_e2e.test_audit_page_follows_the_role` (M5) |
| No page copy claims a draft is in the audit log | **Partly** | Queue, Claims and Settings say "saved in this browser, not yet in the audit log". The reason box on a claim still reads "Recorded with your name in the audit log", which is only true once appended. Moved to P3, which absorbs M6 |
| The readiness note separates tested, documented and verified, and states the torn-write limit | Yes | This note, sections 3 and 4 |

Revision 4 adds "one command applies decisions and rebuilds the page": that is M9, not started.

## 2. Regression run, 26 Oct 2026

Every step of `.github/workflows/ci.yml`, run locally on Windows from `b87e4e7` (this branch's base; the note adds no code), plus the audit commands. Python 3.10.21 and 3.12.14 gave the same results.

| Check | 3.10 | 3.12 |
|---|---|---|
| `src/validate_pack.py` | PASS | PASS |
| Tracked `.env*` files but `.env.example` | none | none |
| `python -m unittest discover -s tests` with `REQUIRE_E2E=1` | 541 OK, 0 skipped | 541 OK, 0 skipped |
| Contrast tests (`test_ui_contrast`, part of the above) | pass | pass |
| A rule reads the wall clock | no | no |
| `status_accuracy`, development · validation · stress | 1.0 · 1.0 · 1.0 | 1.0 · 1.0 · 1.0 |
| `tamper_demo` on a run's log | 8 of 8 as stated | 8 of 8 as stated |
| Pack's own `src/audit.py --verify` on that log, `append_performed` included | valid, 7 events | valid, 7 events |
| Gate on a truncated anchor | exit 2, "the anchor cannot be read as JSON" | same |
| A run while `audit.jsonl.lock` exists | exit 2, nothing appended | same |

`validate_pack.py` reports a checksum mismatch on `.gitignore` in a Windows checkout with `core.autocrlf=true`, which turns it into CRLF. A clone with `core.autocrlf=false` passes on both versions, as CI on Linux does. It is not a change to the pack.

## 3. Tested, documented only, independently verified

**Implemented and tested.** Everything marked "Yes" in section 1. "Tested" means a test or a CI step in this repository fails if it breaks. The threat table in `docs/PRIVACY_SECURITY.md` names the test for each control.

**Documented only: no code enforces it.**
- Recording the head outside this machine after every append. `decisions` and `gate` print the line to record; `run` and `correct` do not, so after those the head comes from `python -m claimguard.audit.chain`. Whether the team records it is a habit, not a check.
- Removing a stale `<log>.lock` after a crash. The error says to remove it only if no command is running; nothing checks that.
- GitHub secret scanning, which M1 says to turn on by hand. Not confirmed: the repository's settings are visible to its admin only.
- The production controls in `docs/PRIVACY_SECURITY.md` section 6: WORM storage, an audit-writer service account, trusted timestamps, single sign-on. None is built.
- Using `--complete` on the held-out run (DEC-013): our default, waiting on the mentor.

**Independently verified: nothing yet.** GitHub CI runs our own tests on a clean Linux machine, which rules out "works on one laptop", but it checks only what we wrote. No mentor or other team has reviewed the chain, the gate or the page. The scores are agreement with labels the pack provides, and the scorer checks statuses and evidence values, not reasoning: a correct status for a wrong reason would still score.

## 4. Known limits

- **A torn log write cannot be recovered.** A crash in the middle of writing a batch leaves a partial last line. Verification then fails at that event: every command that appends or judges refuses the log, the page shows it as invalid, and no tool repairs it. Restore the log from a trusted copy. A crash between the log write and the anchor write is safe: the log is then ahead of its anchor, which verifies.
- **The OS user name is kept permanently.** Each append records who ran it (`append_performed.os_user`). That name is personal data, and a hash chain cannot erase a row without breaking every row after it. The page shows it to admins only, but the page's embedded data holds every event for every role: the role switch is a demonstration, not access control.
- **Who appended is not who decided.** Reviewer names are self-declared, checked against an actor directory anyone with a shell can edit. The OS user says which account ran the command, which is not authentication either.
- **An unreadable row rejects the whole CSV folder.** When a row in a nested CSV file cannot be parsed, its `claim_id` cannot be read, so any claim might be missing it: every claim in the folder is rejected rather than one accepted incomplete (DEC-014). A NUL is readable on every version, so it rejects only its own claim.
- **Tamper-evident, not immutable.** Whoever controls the log and its anchor can rewrite both; only a head kept outside this machine detects it, and only up to the last head recorded.
- **Mock model only.** No live-model quality, latency or cost has been measured (`docs/EVALUATION_REPORT.md`).

## 5. Next

1. Merge PRs #31 to #34 in order. Gate G0 is met: M0 is green on 3.10 and 3.12.
2. M9: one command appends decisions, rebuilds the page and prints the head to record.
3. Track B. P3 takes the remaining copy item above. P8 writes version 2 of this note, with before and after evidence.
