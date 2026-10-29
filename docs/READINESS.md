# ClaimGuard AI · readiness note (version 2)

Tracks A and B of master plan revision 4 are done: the must-do fixes M0 to M9 and the review page redesign P1 to P8. Every item of the readiness bar holds, each with a test or a command that fails if it breaks, on Python 3.10 and 3.12, locally and in CI. **But only M0, M1 and M7 are on `main`**: section 1 says why, and how one pull request brings in the rest.

This note separates what is implemented and tested, what is only documented, and what nobody outside the team has verified. "Accuracy 1.0" means our statuses agree with the pack's reference labels on the three public splits. It does not mean the rules are clinically or contractually right, and nobody has scored the hidden split.

| | |
|---|---|
| Team · date | MedNexus · 28 Oct 2026 |
| Commit | branch `mak/p8-verification`, on `mak/p7-responsive` at `251d45d` |
| Pack | ClaimGuard AI starter pack 1.0.0, `validate_pack.py` PASS |
| Plan | Master plan revision 4: Tracks A and B done. Next: B0, the go/no-go for a local server, with the mentor. Version 3 of this note comes with B5 |
| Changed since version 1 | M9 (one-step apply); P1 to P8 (the review page redesign); this note |

## 1. What is on `main`

The stacked pull requests #31 to #41 all show as merged, but only #31 reached `main`. Each later one targeted the branch below it, and those branches were kept after merging, so GitHub never moved the next pull request onto `main`: #32 to #41 merged into each other's branches.

| On `main` | Not on `main` |
|---|---|
| M0 (CSV fails closed), M1 + M7 (CI) | M2 + M3, M4, M5, M8 (readiness note v1), M9, P1 to P7, the CI fix of P7, this note |

The top of the stack holds everything below it. `git merge-tree` shows `mak/p7-responsive` merging into `main` with no conflict (13 commits, 38 files). One pull request from the top branch into `main` brings all of it in; deleting each branch once its pull request merges keeps the next one on `main`.

## 2. Readiness bar

| Item | Holds | Evidence |
|---|---|---|
| `validate_pack.py` passes | Yes | Section 3, from a clean clone; CI step "Starter pack integrity" |
| CI green on 3.10 and 3.12, e2e running | Yes | `check (py3.10)` and `check (py3.12)` on `251d45d` (section 3). `REQUIRE_E2E=1` makes a missing Node or Chrome a failure |
| Accuracy 1.0 on all three public splits | Yes | Section 3: development 6,000, validation 2,250, stress 750 results; 0 FP, 0 FN, 0 not implemented |
| No accepted claim is missing a row; an unreadable row fails closed | Yes | `test_csv.test_an_unparseable_child_row_rejects_every_claim`, `test_ingest_fuzz` (M0) |
| A NUL in a CSV row gives the same result on every version | Yes | `test_csv.test_nul_rejects_only_its_claim_on_every_version` (M0) |
| No tracked `.env*` file at any depth but `.env.example` | Yes | CI step and `test_rbac_and_secrets` (M1) |
| `tamper_demo`: each case behaves as stated, including the one it cannot detect | Yes | Section 3: 8 of 8; `test_tamper_demo` (M2, M3) |
| A lost anchor is restored only against a head kept outside | Yes | `test_audit_chain.AnchorTests` (M3) |
| The gate exits 2 on a broken chain, a head mismatch or any malformed anchor, never a traceback | Yes | Section 3; `test_gate.AnchorGateTests` (M4) |
| A second writer is refused | Yes | Section 3; `test_audit_chain.WriterLockTests` (M4) |
| Every append records the OS user who ran it; only admins see it | Yes | `test_audit_chain.AppendPerformedTests`, `test_ui_e2e.test_audit_page_follows_the_role` (M5) |
| No page copy claims a draft is in the audit log | **Yes** (was "partly") | The reason box reads "Kept with your name in this browser's draft"; drafts banner and "Your drafts" say "not in the audit log until an administrator appends them" (P3, P5) |
| One command applies decisions and rebuilds the page | Yes | `python -m claimguard.ui.apply`; `test_ui_apply`; run end to end in section 3 (M9) |
| The page renders no slower than the P1 baseline | Yes | `docs/UI_BASELINE.md` section 12: first frame 148 ms against 147 ms; Queue 55–70 ms against 187–192 ms |
| No page scrolls sideways at 375, 768, 1280 and 1440 px, nor at 375 px with a wider font | Yes | `test_ui_e2e.test_no_page_scrolls_sideways_at_any_width`, `test_no_page_scrolls_sideways_with_a_wider_font` (P7, and the CI fix) |
| Text contrast AA, focus ring and chart fills 3:1, in both themes | Yes | `test_ui_contrast`: 44 text pairs, lowest 4.56:1 light and 5.12:1 dark; focus ring lowest 3.83:1 |
| A claim is decided by keyboard alone; every list is one tab stop | Yes | `test_ui_e2e.test_a_claim_is_decided_by_keyboard_alone`, `test_a_table_is_one_tab_stop`; first decision at stop 20, was 41 |
| Motion is short and off with reduced motion | Yes | `test_ui_core.test_motion_is_short_and_moves_transform_and_opacity_only`, `test_ui_e2e.test_motion_is_short_and_off_with_reduced_motion` (P6) |
| The readiness note separates tested, documented and verified, and states the limits | Yes | This note, sections 4 and 5 |

## 3. Regression run, 28 Oct 2026

Every step of `.github/workflows/ci.yml`, plus the audit commands, run on Windows from two clean clones of `9827838` with `core.autocrlf=false` (so the pack's checksums see the same files as CI on Linux), one per Python version. The CI fix `251d45d` changes the stylesheet and the e2e test only; the full suite was run again on it, with the same result.

| Check | 3.10.21 | 3.12.14 |
|---|---|---|
| `src/validate_pack.py` | PASS | PASS |
| Tracked `.env*` files but `.env.example` | none | none |
| `python -m unittest discover -s tests` with `REQUIRE_E2E=1` | 564 OK, 0 skipped (565 on `251d45d`) | 564 OK, 0 skipped (565 on `251d45d`) |
| A rule reads the wall clock | no | no |
| `status_accuracy`, development · validation · stress | 1.0 · 1.0 · 1.0 | 1.0 · 1.0 · 1.0 |
| `tamper_demo` on a run's log | 8 of 8 as stated | 8 of 8 as stated |
| Pack's own `src/audit.py --verify` on that log | valid, 7 events | valid, 7 events |
| Gate on a truncated anchor | exit 2, "the anchor cannot be read as JSON" | same |
| A run while `audit.jsonl.lock` exists | exit 2, nothing recorded | same |
| GitHub CI on `251d45d` (PR #42) | `check (py3.10)` success | `check (py3.12)` success |

**One-step apply, end to end** (on a copy of a development run's log): two decisions in the format the page downloads, both "Dismiss with reason" on `CG-785C09BD9CC8`, gave "2 decision(s) appended", "400 claims: 137 ready, 263 blocked", the page rebuilt with both decisions in a valid chain of 10 events, and the count and head to record. The exit code was 1, as documented while any claim is blocked. Applying the same file again appended nothing.

**What CI found that the local run did not.** On `9827838` CI failed on both versions: on Linux, whose default font is wider, the Queue scrolled 35 px sideways at 375 px. `251d45d` fixes it, and the e2e test now checks every page with a wide font, which reproduces the failure on Windows (`docs/UI_BASELINE.md` section 11).

## 4. Tested, documented only, independently verified

**Implemented and tested.** Everything marked "Yes" in section 2. "Tested" means a test or a CI step in this repository fails if it breaks. The threat table in `docs/PRIVACY_SECURITY.md` names the test for each control.

**Documented only: no code enforces it.**
- Recording the head outside this machine after every append. `decisions`, `apply` and `gate` print the line to record; `run` and `correct` do not. Whether the team records it is a habit, not a check.
- Removing a stale `<log>.lock` after a crash. The error says to remove it only if no command is running; nothing checks that.
- GitHub secret scanning, which M1 says to turn on by hand. Not confirmed: the repository's settings are visible to its admin only.
- The production controls in `docs/PRIVACY_SECURITY.md` section 6: WORM storage, an audit-writer service account, trusted timestamps, single sign-on. None is built.
- Using `--complete` on the held-out run (DEC-013): our default, waiting on the mentor.

**Checked only partly.**
- The page on a real phone or tablet: only Chrome's emulated widths, at 375 to 1440 px.
- Screen readers: the structure is tested (names, labels, landmarks, headings in order, live regions, focus moves), but no screen reader was run.
- Apple devices: the system fonts (San Francisco, SF Mono) are not checked yet (`docs/DESIGN_SYSTEM.md`, section 7).
- Browsers other than Chrome: the page was built and tested in Chrome only.

**Independently verified: nothing yet.** GitHub CI runs our own tests on a clean Linux machine, which rules out "works on one laptop" and this time caught a real bug, but it checks only what we wrote. No mentor or other team has reviewed the chain, the gate or the page. The scores are agreement with labels the pack provides, and the scorer checks statuses and evidence values, not reasoning.

## 5. Known limits

- **A torn log write cannot be recovered.** A crash in the middle of writing a batch leaves a partial last line; every command then refuses the log, and it has to be restored from a trusted copy. A crash between the log write and the anchor write is safe.
- **The OS user name is kept permanently.** Each append records who ran it, which is personal data a hash chain cannot erase. The page shows it to admins only, but the page's embedded data holds every event for every role: the role switch ("Demo") is a demonstration, not access control.
- **Who appended is not who decided.** Reviewer names are self-declared, checked against an actor directory anyone with a shell can edit.
- **Drafts live in one browser.** A decision is kept in that browser's storage until it is downloaded; another browser, a private window or cleared site data does not have it. The page says so and offers the download.
- **An unreadable row rejects the whole CSV folder** (DEC-014).
- **Tamper-evident, not immutable.** Whoever controls the log and its anchor can rewrite both; only a head kept outside this machine detects it, and only up to the last head recorded.
- **Mock model only.** No live-model quality, latency or cost has been measured (`docs/EVALUATION_REPORT.md`).

## 6. Next

1. Open one pull request from the top of the stack into `main`, and merge it once CI is green (section 1). P6 (`mak/p6-motion`) never had a pull request of its own; it is inside that one.
2. Check the page on an Apple device (Safari) and, if possible, with a screen reader.
3. B0 with the mentor: is the local server (Track C) in scope? If not, `python -m claimguard.ui.apply` stays the product's loop.
4. A demo script for the presentation is in `docs/DEMO_WALKTHROUGH.md`.
