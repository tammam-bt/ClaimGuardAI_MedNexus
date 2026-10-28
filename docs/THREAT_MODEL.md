# Threat model: the local review server (B0)

Track C adds `python -m claimguard.ui.serve`: a small server that serves the
review page and lets a reviewer save decisions and corrections from it,
without the download-and-command step (M9). This page says who can reach it,
what they could change, and which check stops what. The decision to build it
is DEC-015 in [DECISIONS.md](DECISIONS.md). Tests named below are in `tests/test_ui_serve.py` unless another file is given.

## What it is

- Python standard library only (`http.server`), started by the administrator
  who owns the run's files, for the length of a review session.
- Bound to `127.0.0.1`, never to another interface: there is no option for it.
- A random token per launch (`secrets.token_urlsafe(32)`), printed once in the
  address the reviewer opens.
- It writes only what the command-line tools write, through the same code:
  `claimguard.ui.decisions.check` then `chain.append` for decisions,
  `claimguard.review.correct.correct_claim` for corrections.

## What is worth protecting

| Asset | Why |
| --- | --- |
| Audit log and its anchor | Integrity: what was decided, by whom, on which version. |
| Corrections folder | Integrity: each version must follow from the claim as received. |
| Actor directory (`--directory`) | The only source of roles. The server reads it and never writes it. |
| Password file (`--users`, B4 only) | scrypt hashes. The server reads it and never writes it. |
| Claims and results | Confidentiality. The data is synthetic, but it is handled as if it were not. |

## Who can reach it, and what each check prevents

| # | Who | What they could try | Check | Test |
| --- | --- | --- | --- | --- |
| T1 | Anyone on the network | Open the page, post decisions | Bound to `127.0.0.1` only | `test_bound_to_this_machine_only` |
| T2 | A web page in the reviewer's browser (CSRF) | Post a forged decision to `127.0.0.1` | Token header on every API call; `Origin` must be this server; `Sec-Fetch-Site` must be `same-origin` when sent; JSON only, so a cross-site post needs a preflight, which is never answered (no CORS headers) | `test_api_refuses_another_origin`, `test_api_takes_json_only`, `test_api_refuses_a_missing_or_wrong_token` |
| T3 | A web page using DNS rebinding (its own name resolving to `127.0.0.1`) | Read the page and its token, then post | `Host` must be `127.0.0.1:<port>` or `localhost:<port>`; the launch cookie is bound to that host | `test_wrong_host_is_refused` |
| T4 | Another account or process on this machine | Use the API through loopback | The token is needed for the page and every API call, and is printed only in the launching terminal | `test_page_needs_the_token` |
| T5 | Any client that has the token | Large or malformed bodies, slow connections | `Content-Length` required, 1 MiB at most, JSON object only, 15 s per connection | `test_oversized_body_is_refused`, `test_a_chunked_body_is_refused`, `test_api_takes_json_only` |
| T6 | A reviewer | Record a decision under someone else's name | Without sign-in: names are self-declared, as on the static page (doc 10); roles come from the directory; `append_performed` names the command and the OS user running the server. With sign-in (B4): every decision's actor must be the signed-in user | `test_signed_in_actor_must_match`, `test_saving_needs_a_signed_in_person` |
| T7 | Two writers at once (two tabs, or the server and a command) | Interleave appends | One server lock, then M4's `<log>.lock`: a second writer is refused, never interleaved | `test_a_second_writer_is_refused`, `test_saves_from_two_tabs_at_once_are_serialised` |
| T8 | A reviewer with an old page | Save a decision on a version or status that changed | `decisions.check` (`input_hash`, `original_status`); a correction names the version it builds on and is refused if it is no longer the latest | `test_a_stale_decision_is_refused`, `test_a_correction_on_an_old_version_is_refused` |
| T9 | Hostile claim text | Run script in the page, then call the API | Text is never parsed as HTML (`h()`); the served page's policy adds only `connect-src 'self'` | `test_ui_e2e.test_hostile_text_never_runs`; `test_served_page_policy`; `test_ui_serve_e2e.test_the_page_talks_to_this_server_only` |
| T10 | Browser history, logs, referrers | Leak the token | The token is moved from the address to an `HttpOnly`, `SameSite=Strict` cookie by a redirect; `Referrer-Policy: no-referrer`; the server never logs a query string; the token dies with the process | `test_token_moves_to_a_cookie`, `test_ui_serve_e2e.test_the_page_talks_to_this_server_only` |
| T11 | Someone at an unlocked browser (B4) | Reuse a session | Session cookie `HttpOnly`, `SameSite=Strict`, in memory only, 8 hours at most, sign-out; 5 failed sign-ins lock a name for 60 s | `SignInTests` |

## What it does not protect against

- **The same OS account.** A process running as the user who started the
  server can read the token from the terminal and edit the files directly.
  The server adds no protection there; the audit chain's anchor and a head
  recorded outside the machine (M2 + M3) are what detect such edits.
- **A reviewer with a shell on this machine.** Sign-in (B4) only means
  something if the server and its files run under an account reviewers cannot
  use. Otherwise it records who signed in, not who could have written.
- **Transport encryption.** None: traffic never leaves loopback.
- **Denial of service by a local process.** It can hold connections open;
  the server is restarted by the person who started it.

## Decision

Go, given by the user on 2026-10-28, on the condition that the static page
keeps working offline with no server (B1's rule). The mentor's confirmation
is still to be recorded (DEC-015).
