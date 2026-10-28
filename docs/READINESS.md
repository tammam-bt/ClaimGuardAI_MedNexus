# ClaimGuard AI · readiness note (version 3)

All three tracks of master plan revision 4 are built: the must-do fixes M0 to M9, the review page redesign P1 to P8, and the local backend B0 to B5. Every item of the readiness bar holds, each with a test or a command that fails if it breaks, on Python 3.10 and 3.12, locally. Track C has not been through GitHub CI yet: it is not pushed. **And only M0, M1 and M7 are on `main`**: section 1 says why, and how one pull request brings in the rest.

This note separates what is implemented and tested, what is only documented, and what nobody outside the team has verified. "Accuracy 1.0" means our statuses agree with the pack's reference labels on the three public splits. It does not mean the rules are clinically or contractually right, and nobody has scored the hidden split.

| | |
|---|---|
| Team · date | MedNexus · 28 Oct 2026 |
| Commit | branch `mak/track-c-backend`, on `mak/p8-verification` at `423e18c` |
| Pack | ClaimGuard AI starter pack 1.0.0, `validate_pack.py` PASS |
| Plan | Master plan revision 4: Tracks A, B and C done. B0 was decided "go" by the user; the mentor's confirmation is pending (DEC-015) |
| Changed since version 2 | B0 (`docs/THREAT_MODEL.md`, DEC-015), B1 to B3 (`python -m claimguard.ui.serve`: the page, saving decisions, the correction builder), B4 (optional sign-in, DEC-016), B5 (tests, security review, this note) |

## 1. What is on `main`

The stacked pull requests #31 to #41 all show as merged, but only #31 reached `main`. Each later one targeted the branch below it, and those branches were kept after merging, so GitHub never moved the next pull request onto `main`: #32 to #41 merged into each other's branches.

| On `main` | Not on `main` |
|---|---|
| M0 (CSV fails closed), M1 + M7 (CI) | M2 + M3, M4, M5, M8, M9, P1 to P8, Track C |

The top of the stack holds everything below it. One pull request from the top branch into `main` brings all of it in; deleting each branch once its pull request merges keeps the next one on `main`. Track C sits on top of P8, so the same pull request can carry it, or P8's can go first.

## 2. Readiness bar

**After Track A and Track B** (version 2, unchanged by Track C; rerun in section 3):

| Item | Holds | Evidence |
|---|---|---|
| `validate_pack.py` passes; CI green on 3.10 and 3.12 with e2e running | Yes | Section 3 (local); CI on `251d45d` for Track B. Track C is not pushed yet |
| Accuracy 1.0 on all three public splits | Yes | Section 3: 0 FP, 0 FN, 0 not implemented |
| No accepted claim is missing a row; unreadable rows fail closed; NUL the same on every version | Yes | `test_csv`, `test_ingest_fuzz` (M0) |
| No tracked `.env*` file at any depth but `.env.example` | Yes | CI step and `test_rbac_and_secrets` (M1) |
| `tamper_demo`: each case as stated, including the one it cannot detect | Yes | Section 3: 8 of 8, the same lines as version 2 |
| A lost anchor is restored only against an outside head; the gate exits 2 on any broken chain, head mismatch or malformed anchor | Yes | `test_audit_chain.AnchorTests`, `test_gate.AnchorGateTests` (M3, M4) |
| A second writer is refused; every append records who ran it | Yes | `WriterLockTests`, `AppendPerformedTests` (M4, M5); through the server too (below) |
| One command applies decisions and rebuilds the page | Yes | `test_ui_apply` (M9) |
| Every finding can be decided from the workspace, by mouse or keyboard; three labelled layers; no Approve or Reject | Yes | `test_ui_e2e` (P3, P4) |
| No page claims a draft is in the audit log | Yes | Drafts say "not in the audit log until an administrator appends them", or, served, "until you save them" |
| Every dashboard number names its source and opens its list | Yes | `test_ui_e2e` (P5) |
| Both themes pass WCAG AA; reduced motion respected; no sideways scroll at 375 to 1440 px | Yes | `test_ui_contrast`, `test_ui_e2e` (P2, P6, P7) |
| Render time no worse than the P1 baseline | Yes | `docs/UI_BASELINE.md` section 12. The offline page's start-up is unchanged: it asks no server |

**After Track C** (new):

| Item | Holds | Evidence |
|---|---|---|
| Server reachable only from this machine, with a per-launch token | Yes | Bound to `127.0.0.1` with no option for another address; token for the page and every API call: `test_bound_to_this_machine_only`, `test_page_needs_the_token`, `test_api_refuses_a_missing_or_wrong_token` |
| Bad token, Host, Origin or size refused, with tests | Yes | `test_wrong_host_is_refused`, `test_api_refuses_another_origin`, `test_api_takes_json_only`, `test_oversized_body_is_refused`, `test_a_chunked_body_is_refused` |
| Decisions saved from the page give the same gate result as the command line | Yes | `test_saved_like_the_command_line`: the gate's rows for a log written by the server and one written by `python -m claimguard.ui.decisions` are equal |
| A failed save loses no draft | Yes | `test_ui_serve_e2e.test_a_refused_save_keeps_the_draft`: refused, every problem listed, the draft still in the browser and in its storage |
| A reviewer decides, saves and sees "In the audit log" without a terminal | Yes | `test_ui_serve_e2e.test_a_reviewer_saves_and_sees_in_the_audit_log`, in headless Chrome against a live server |
| A correction is rechecked from the page, and only on the latest version | Yes | `test_ui_serve_e2e.test_a_correction_is_rechecked_as_a_new_version`, `test_a_correction_on_an_old_version_is_refused` |
| A second writer is refused, here or on the command line; two tabs never interleave | Yes | `test_a_second_writer_is_refused`, `test_saves_from_two_tabs_at_once_are_serialised` |
| The static file still works offline, with no server | Yes | `test_ui_e2e` unchanged and passing; `test_served_page_policy`: the file's policy still has no `connect-src`, the served one adds only `connect-src 'self'` |
| `tamper_demo` results unchanged | Yes | Section 3 |
| This note says what sign-in does and does not prove | Yes | Section 5 |

## 3. Regression run, 28 Oct 2026

Every step of `.github/workflows/ci.yml`, plus the audit commands, run on Windows from a snapshot of the branch: `HEAD` plus the changed files, extracted with `core.autocrlf=false` so the pack's checksums see the same bytes as CI on Linux, one per Python version.

| Check | 3.10.21 | 3.12.14 |
|---|---|---|
| `src/validate_pack.py` | PASS | PASS |
| Tracked `.env*` files but `.env.example` | none | none |
| `python -m unittest discover -s tests` with `REQUIRE_E2E=1` | 606 OK | 606 OK |
| A rule reads the wall clock | no | no |
| `status_accuracy`, development · validation · stress | 1.0 · 1.0 · 1.0 (0 FP, 0 FN, 0 not implemented) | same |
| `tamper_demo` on a run's log | 8 of 8 as stated | 8 of 8 as stated |

Version 2 had 565 tests; Track C adds 36 server tests (`tests/test_ui_serve.py`) and 5 end-to-end tests against a live server (`tests/test_ui_serve_e2e.py`). The snapshot is not a git checkout, so the 4 tests that ask git which files would be committed (`test_rbac_and_secrets.SecretsTests`) skipped there; they pass in the working checkout, new files included.

**Security review of the server (B5).** Each check of `docs/THREAT_MODEL.md` was tried from outside with a raw HTTP client, and three gaps were found and fixed before this note:
- a body nested too deeply for Python's JSON parser raised `RecursionError`, which dropped the connection: now a 400;
- a decision whose `claim_id` or `action` was a list crashed the role check with `TypeError`: every field must now be text, as the review-event schema says, and the problem is listed;
- any other unexpected error now answers 500 with "Nothing was saved", and the details go to the server's log only.
Found while testing: Windows lets a second program bind a port already in use when `SO_REUSEADDR` is set, which Python's HTTP server sets by default; the server turns it off and asks for exclusive use. Cookies are shared by every port of a host, so the server's cookie names hold the port.

## 4. Tested, documented only, independently verified

**Implemented and tested.** Everything marked "Yes" in section 2. "Tested" means a test or a CI step in this repository fails if it breaks. The threat tables in `docs/PRIVACY_SECURITY.md` and `docs/THREAT_MODEL.md` name the test for each control.

**Documented only: no code enforces it.**
- Recording the head outside this machine after every append. `decisions`, `apply`, `gate` and the server (when it stops) print the line to record; `run` and `correct` do not.
- Starting the server from the account that owns the run's files, and keeping the password file where reviewers cannot write it.
- Removing a stale `<log>.lock` after a crash.
- GitHub secret scanning, which M1 says to turn on by hand.
- The production controls in `docs/PRIVACY_SECURITY.md` section 6: WORM storage, an audit-writer service account, trusted timestamps, single sign-on.
- Using `--complete` on the held-out run (DEC-013): our default, waiting on the mentor.

**Checked only partly.**
- The page on a real phone or tablet, with a screen reader, on Apple devices, or in browsers other than Chrome: as in version 2. The served page was tested in headless Chrome only.
- The server under load: it serves one reviewer's session; nothing measured how many it can serve.

**Independently verified: nothing yet.** GitHub CI has run Tracks A and B, but only our own tests; Track C has not run there. No mentor or other team has reviewed the chain, the gate, the page or the server.

## 5. Known limits

- **What sign-in proves, and what it does not.** With `--users`, the server saves a decision only for the signed-in person, whose password it checked (scrypt). That proves who used the page. It does not prove who could have written the files: anyone with a shell under the account that runs the server can edit the log, the actor directory or the password file directly. Sign-in authenticates only when the server and its files run under an account reviewers cannot use. On the prototype's one machine they do not, so sign-in is off by default (DEC-016).
- **Without sign-in, names are self-declared**, through the server as on the static page; the directory checks the role, and `append_performed` records the OS user running the server, not the reviewer.
- **The same OS account is trusted.** A process running as the user who started the server can read its token and the files; the server adds nothing against it (`docs/THREAT_MODEL.md`).
- **A torn log write cannot be recovered**, and **the OS user name is kept permanently**: as in version 2.
- **Drafts live in one browser** until downloaded or saved through the server.
- **An unreadable row rejects the whole CSV folder** (DEC-014).
- **Tamper-evident, not immutable**, and **mock model only**: as in version 2.
- **No four-eyes approval.** A second reviewer for high-severity dismissals (DEC-004) waits on the mentor, and needs sign-in under a separate account to mean anything.

## 6. Next

1. Ask the mentor to confirm B0 (DEC-015) and B4 (DEC-016), and question 2 on four-eyes approval.
2. Push `mak/track-c-backend` and let CI run it on Linux, then one pull request from the top of the stack into `main` (section 1).
3. Check the page on an Apple device (Safari) and, if possible, with a screen reader.
4. A demo script, with the server (section 4b), is in `docs/DEMO_WALKTHROUGH.md`.
