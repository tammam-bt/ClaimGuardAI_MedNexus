# The review interface

One HTML file, built from a run's outputs, that a claims reviewer opens in a browser. It works offline, with no server, no key and no package. Served by the optional local server (*The local server*, below), the same page also saves decisions and corrections without a terminal. It shows only what the run produced: when a source is missing, the page says so instead of inventing numbers.

## Build it

```bash
python -m claimguard.run --input data/development/claims.jsonl --output outputs/dev_predictions.jsonl \
    --explain --audit-log outputs/audit.jsonl
python -m claimguard.ui --results outputs/dev_predictions.jsonl --claims data/development/claims.jsonl \
    --audit-log outputs/audit.jsonl --gold data/development/expected_results.jsonl
```

Open `outputs/claimguard.html`. The manifest and explanations are read from beside `--results`, where `claimguard.run` writes them.

| Option | Adds |
|---|---|
| `--audit-log` | the Audit Logs page, the integrity badge and each claim's history |
| `--gold` | the Evaluation page and per-rule performance |
| `--corrections` | corrected claim versions (see *Corrections*) |
| `--output` | another file name (default `outputs/claimguard.html`) |

## The pages

Every page has the same sidebar, top bar and components. A concept (a status, a route, an action) always has the same label, colour and icon.

| Page | What it shows |
|---|---|
| **Dashboard** | An administrator's home. The run's life cycle in eight steps (received → ingested → checked → screened → explained → routed → in review → outcome), where the review stands, routes, the rules most often failing, your drafts, the audit log, records rejected at ingestion. Every number opens the list it counts; every card names its source (run manifest, results, audit log, this browser) |
| **Review Queue** | A reviewer's home. The next claim with a finding to decide, then the claims routed REVIEW or ESCALATE, open ones first, most urgent route then oldest first, each with its 15-check fingerprint. Filters and sort live in the address |
| **Claims** | Every claim. One claim is a review workspace: its findings, the finding being decided in three layers (from the claim, explanation, your decision) and the claim's data, where "show in claim" highlights each field a finding cites. Then its life cycle, 15 checks, history and corrected versions. When the last finding is decided, the next open claim is one key away |
| **Audit Logs** | The hash chain, verified when the page was built; run events are shown to admins only |
| **Rules** | The 15 rules of `rules/rules.json`: logic quoted from the rulebook, the policy values each one reads, this run's statuses, performance, the claims concerned. Read-only |
| **Evaluation** | The official scorer's metrics: overall, per rule, expected-against-predicted matrix, disagreements, AI summary |
| **Settings** | The reviewer's name, role and unsent drafts; how findings are explained, routing, security and permissions, read-only |

`#/components` (not linked from any page) shows every component in every state.

A reviewer's sidebar lists Review Queue, Claims, Rules and Settings, with the other pages under "More"; an administrator's lists all seven. This is a convenience, not access control. Every list is one tab stop (↑ ↓ or j / k, Enter); below 1100 px the sidebar is a drawer behind a menu button, and below 768 px the page is one column. `docs/DESIGN_SYSTEM.md` has the details.

The page speaks a claims reviewer's language: it shows no command, file path of the run, hash or version tag, and no document citation. Run details (run ID, input hash, versions) stay in the run's manifest; the commands below live here, not in the page.

## From a decision to the audit log

1. On a claim, a reviewer picks one of the four actions of `schemas/review_event.schema.json` for each finding and writes a reason. Every action needs one.
2. Decisions are drafts in that browser until **Download decisions** saves them as `review_decision` events.
3. Append them to the chain:

   ```bash
   python -m claimguard.ui.decisions --decisions review_decisions_<run>.jsonl --log outputs/audit.jsonl \
       --directory actors.json --results outputs/dev_predictions.jsonl --claims data/development/claims.jsonl
   ```

   Every decision is checked first: the event format, the role (`claimguard.guards.rbac`), the date, that it was taken on this version of the claim, on a finding of this run, at its current status. One bad decision writes nothing. Appending the same file twice adds nothing. `--directory` is required: it maps each name to a role, in the format of `actors.example.json`. A name that is not in it records nothing, and neither does a role that is not `reviewer` or `admin`. The command ends by printing the log's count and head: record them outside this machine (see *The gate*).
4. Rebuild the page: the decisions now count in every stage, counter and history.

**In one step.** `python -m claimguard.ui.apply` appends, runs the gate and rebuilds the page, with the same checks and the same result as `decisions`, `gate` and `claimguard.ui` run in order:

```bash
python -m claimguard.ui.apply --decisions review_decisions_<run>.jsonl --log outputs/audit.jsonl \
    --directory actors.json --results outputs/dev_predictions.jsonl --claims data/development/claims.jsonl \
    [--corrections outputs/corrections] [--gold data/development/expected_results.jsonl] \
    [--expect-count N --expect-head HASH]
```

- With `--expect-count` and `--expect-head`, the log is checked against the head recorded outside this machine before anything is appended.
- It prints how many decisions were appended, the gate's verdict and the page's path, and ends with the count and head to record outside.
- Exit 0 when every claim is ready, 1 while any is blocked, as the gate does. 2 when it stopped without rebuilding the page: a decision was refused (nothing is appended), or the chain or the run's files cannot be trusted.
- The audit log's `append_performed` event names `claimguard.ui.apply` as the command.

A finding is settled only by **Dismiss with reason**. A check that did not run can never be dismissed.

## Corrections

```bash
python -m claimguard.review.correct --claims data/development/claims.jsonl --claim-id CG-B39790AC3604 \
    --changes fix.json --actor "Reviewer 01" --reason "Authorization added from the source record." \
    --directory actors.json --log outputs/audit.jsonl --output outputs/corrections
```

`fix.json` is a list of JSON Patch operations. The claim as received stays version 1 and is never edited.

- Each correction builds on the latest version in `--output`: version 2, then 3, and so on.
- The stored versions are replayed from the claim as received first. A version file that is not exactly its parent plus its recorded changes refuses the correction, and nothing is written.
- The new version runs through all 15 rules, and a `version_created` event is recorded.

Rebuild with `--corrections outputs/corrections`: the claim shows every version, with what changed, the status changes and its new route. A correction never forces a pass: wrong data stays a finding.

If the latest version still has findings, the claim is *Rechecked as a new version* and the reviewer decides them on that version:
- the claim page says *Deciding on version N* and shows that version's findings, checks and data; the claim as received is still shown unchanged;
- each decision is taken on that version's `input_hash`, so a decision on an older version no longer counts;
- append the downloaded decisions with the same folder: `python -m claimguard.ui.decisions ... --corrections outputs/corrections`. Without it, the command judges the claim as received and refuses decisions on the new version; with it, it refuses decisions on any older version.

## The local server: no download, no command (Track C)

The same page, served from this machine, saves decisions and rechecks corrections itself:

```bash
python -m claimguard.ui.serve --results outputs/dev_predictions.jsonl --claims data/development/claims.jsonl \
    --log outputs/audit.jsonl --directory actors.json --corrections outputs/corrections \
    [--gold data/development/expected_results.jsonl] [--users users.json] [--port 8765] \
    [--expect-count N --expect-head HASH]
```

It prints one address, `http://127.0.0.1:8765/?token=…`, to open in a browser on this machine. An administrator starts it, from the account that owns the run's files.

- **Save to the audit log.** The drafts banner (Queue, Claims, each claim), the dashboard's "Your drafts" and Settings offer *Save to the audit log (N)* beside *Download decisions*. The server runs the same checks and append as `python -m claimguard.ui.decisions`, inside the writer lock. On success the page reloads from the files: each decision reads *In the audit log*, and a notice gives the log's new count and head and the gate's verdict, in the page's own labels ("Gate: 136 of 400 claims ready; blocked: 263 to review, 1 correction needed"). A refusal lists every problem, saves nothing, and keeps every draft.
- **Correct this claim.** On a claim, pick a field, enter its new value (a number stays a number), add as many changes as needed, give a reason. With the server, *Recheck as a new version* runs `python -m claimguard.review.correct` with `--log`: the page reloads on the new version, with the status changes. It is refused if the claim gained a version since the page was loaded. Without the server, the same card downloads the patch file that command reads.
- **Sign-in (optional, B4).** With `--users`, every save needs a signed-in person (Settings, *Local server*): each decision's actor must be that person, and a correction is recorded under their name. Set a password with `python -m claimguard.ui.signin --users users.json --directory actors.json --name "Reviewer 01"` (typed twice at the keyboard, at least 12 characters, stored as an scrypt hash; the name and the file are checked before the prompt, and on Windows the prompt cannot be piped). It proves who saved only if reviewers cannot use the account that runs the server (`docs/THREAT_MODEL.md`).
- **The offline file is unchanged.** The page `python -m claimguard.ui` writes has no token and never calls anything; its policy still has no `connect-src`. The served page adds only `connect-src 'self'`.
- `append_performed` names `claimguard.ui.serve`, the OS user running it and the SHA-256 of the request body. When the server stops, it prints the count and head to record outside this machine.

| Request | Does |
|---|---|
| `GET /` | the page, rebuilt from the run's files whenever they change |
| `GET /api/status` | the audit log's verified count and head; whether corrections and sign-in are on |
| `POST /api/decisions` | `{"decisions": [...]}`: check, then append |
| `POST /api/corrections` | `{"claim_id", "parent_hash", "changes", "actor", "reason"}`: correct and recheck |
| `POST /api/signin`, `/api/signout` | only with `--users` |

Every request needs `Host` to be `127.0.0.1:<port>` or `localhost:<port>`. The page needs the launch token (moved from the address to an `HttpOnly`, `SameSite=Strict` cookie); every API call sends it in `X-ClaimGuard-Token`. Every `POST` needs `Origin` to be this server, `application/json` and at most 1 MiB. `docs/THREAT_MODEL.md` says what each check prevents; `tests/test_ui_serve.py` and `tests/test_ui_serve_e2e.py` prove them.

## The gate: what may proceed

The page shows each claim's state but enforces nothing: decisions are drafts until appended. The gate enforces it:

```bash
python -m claimguard.review.gate --results outputs/dev_predictions.jsonl --claims data/development/claims.jsonl \
    --log outputs/audit.jsonl --directory actors.json --corrections outputs/corrections --output outputs/gate.jsonl
```

- It verifies the audit chain first; a chain that does not verify judges nothing (exit 2). That includes a log with events and no anchor file.
- With `--expect-count N --expect-head HASH`, a count and head recorded outside this machine, it also checks that event N still has that head, and exits 2 if not. It ends by printing the current count and head to record. See `docs/PRIVACY_SECURITY.md` for where the team keeps them and how to restore a lost anchor.
- Each claim is judged on its latest version. It is **ready** when nothing is flagged, or when every flagged finding was dismissed with a reason, by an actor the directory allows, on that version and that status.
- Otherwise it is **blocked**, in the page's own words: to review, in review, correction needed, waiting for information, awaiting recheck, or rechecked. A claim ingestion rejected, or one with no results, is blocked too.
- It exits 0 only when every claim is ready, so a submission step can rely on it. With no decisions, development gives 136 ready and 264 blocked, as the dashboard shows.
- Each blocked finding lists its triggers: low confidence, high severity, proven issue.

`python -m claimguard.review.feedback --log outputs/audit.jsonl` summarizes the recorded decisions:
- by action, rule and actor;
- the rules reviewers often dismiss, to raise with the mentor. A rule is never changed automatically.

## Roles

`View as` in the top bar switches between Reviewer and Admin, using the permission matrix of `claimguard.guards.rbac` (shown in Settings). There is no login on the offline page (doc 10): the role only changes what the page shows. Signed in on the local server, the top bar shows the signed-in name instead, and the role is the directory's. The permission that counts is checked against the actor directory (`--directory`) when decisions are appended and when a correction is recorded.

## Security

- Claim text, document text and explanations are always inserted as text, never parsed as HTML. The page builds every element itself; no HTML string is ever parsed into it.
- The data sits in a `<script type="application/json">` element with `<`, `>`, `&`, U+2028 and U+2029 escaped, so no claim text can close it.
- The page loads nothing from the network and sends nothing, and its Content-Security-Policy makes the browser enforce it: no request, image, font, frame or form can leave the page. The decisions download still works. Served by the local server, the policy adds `connect-src 'self'`, so the page can talk to that server and nothing else.
- The API key is never written to the run's files, so it is never part of the page.
- Claims flagged by the injection pre-filter are marked, keep their 15 results, and their text never reaches the model.
- An explanation the watchdog rejected is labelled *Rule's explanation (AI answer rejected)*, and the reason is given in plain words: no answer in time, the model service failed, an unreadable answer, an incomplete answer or one citing something it was not given, a failed check called passed, clinical advice, or another rule named. The rejected answer itself is never shown. Settings lists these reasons and what the model never sees (claim number, notes, document text, and patient and member numbers, replaced by placeholders such as `[patient-1]`).

## Consistency, enforced by tests

| Rule | Test |
|---|---|
| Every icon named in the page exists in `static/icons.svg`; statuses, routes, actions and explanation sources never share an icon; the seven navigation icons differ | `tests/test_ui_core.py` |
| Every colour is a token in `:root`; no external resource; no HTML-parsing API | `tests/test_ui_core.py` |
| Every reason the watchdog can reject an AI answer for has a plain-language label in the page | `tests/test_ui_core.py` |
| Every text colour meets WCAG AA (4.5:1) on its background; the focus ring 3:1 | `tests/test_ui_contrast.py` |
| A claim's stage, computed in the page, matches `claimguard.review.routing.outstanding` | `tests/test_ui_core.py` (Node) |
| A claim's outcome in the page matches the gate's | `tests/test_ui_core.py` (Node) |
| The page carries a Content-Security-Policy; the download still works under it; any refusal counts as a page error | `tests/test_ui_bundle.py`, `tests/test_ui_e2e.py` |
| The local server refuses a missing or wrong token, a wrong Host or Origin, a body that is not JSON or over 1 MiB, and a second writer; decisions saved through it give the same gate result as the command line | `tests/test_ui_serve.py` |
| A reviewer decides, saves and sees *In the audit log* against a live server; a refused save keeps its draft; a correction is rechecked | `tests/test_ui_serve_e2e.py` (headless Chrome) |
| Every page draws with no JavaScript error, no unnamed control, no unlabelled field, no duplicate ID, one `h1`; the skip link is the first keyboard stop; nothing scrolls sideways at 1280 px; no network request; the decision flow, the queue, filters, roles and hostile text | `tests/test_ui_e2e.py` (headless Chrome) |

The Node and Chrome tests are skipped where Node or Chrome is not installed.

## Files

| Path | Role |
|---|---|
| `claimguard/ui/bundle.py` | gathers the run's files, computes routes, verifies the chain, scores against the gold |
| `claimguard/ui/page.py` | inlines CSS, icons, data and scripts into one HTML file |
| `claimguard/ui/decisions.py` | appends downloaded decisions to the chain, after checking them |
| `claimguard/ui/apply.py` | one step: `decisions`, then the gate, then the page rebuilt |
| `claimguard/ui/serve.py` | the local server: the page, `/api/status`, saving decisions and corrections (Track C) |
| `claimguard/ui/signin.py` | optional sign-in for the server: scrypt password file, sessions, throttling (B4) |
| `claimguard/review/correct.py` | correction → new version → recheck → `version_created` |
| `claimguard/review/gate.py` | the gate: ready or blocked per claim, exit code; `outcome()` is the twin of `Core.outcome` |
| `claimguard/review/feedback.py` | decisions summarized from the audit chain |
| `claimguard/ui/static/core.js` | pure logic: vocabulary, life cycle, stages, formatting (tested in Node) |
| `claimguard/ui/static/ui.js` | shared components, router, decisions store |
| `claimguard/ui/static/page-*.js` | one file per page; pages only assemble `ui.js` components |
| `claimguard/ui/static/app.css`, `icons.svg` | design tokens and components; one icon per concept |

## Limits

- No login on the offline page: names and roles are self-declared (doc 10). The local server's sign-in is optional, and authenticates only under an account reviewers cannot use.
- Drafts live in one browser until downloaded or saved through the local server; another browser does not see them.
- No time series: one run has no history, so there are no trend lines.
- Phase 2 is mock only: explanations are the rule's own text until the mentor gives the model key in a later phase and a live provider is wired (`claimguard/ai/provider.py`). With a live model, an explanation can name a patient or member only by its placeholder (`[patient-1]`); the finding's evidence still shows the real value.
- The page shows the run it was built from; it cannot start a run. Rebuild after each run, decision append or correction made on the command line. The served page is rebuilt by the server whenever the files change.
