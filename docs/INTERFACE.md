# The review interface

One HTML file, built from a run's outputs, that a claims reviewer opens in a browser. It works offline, with no server, no key and no package. It shows only what the run produced: when a source is missing, the page says so instead of inventing numbers.

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
| **Dashboard** | The run's life cycle in eight steps (received → ingested → checked → screened → explained → routed → in review → outcome), routes, result statuses, the rules most often failing, latest audit events, records rejected at ingestion |
| **Review Queue** | Claims routed REVIEW or ESCALATE, open ones first, most urgent route then oldest first, with the routing rules explained |
| **Claims** | Every claim; one claim's life cycle, its 15 checks, each finding's evidence (field and value), explanation, corrective action and the reviewer's decision, its documents, history and corrected versions |
| **Audit Logs** | The hash chain, verified when the page was built; run events are shown to admins only |
| **Rules** | The 15 rules of `rules/rules.json`: logic quoted from the rulebook, the policy values each one reads, this run's statuses, performance, the claims concerned. Read-only |
| **Evaluation** | The official scorer's metrics: overall, per rule, expected-against-predicted matrix, disagreements, AI summary |
| **Settings** | The reviewer's name, role and unsent drafts; how findings are explained, routing, security and permissions, read-only |

`#/components` (not linked from any page) shows every component in every state.

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

`View as` in the top bar switches between Reviewer and Admin, using the permission matrix of `claimguard.guards.rbac` (shown in Settings). There is no login (doc 10): the role only changes what the page shows. The permission that counts is checked against the actor directory (`--directory`) when decisions are appended and when a correction is recorded.

## Security

- Claim text, document text and explanations are always inserted as text, never parsed as HTML. The page builds every element itself; no HTML string is ever parsed into it.
- The data sits in a `<script type="application/json">` element with `<`, `>`, `&`, U+2028 and U+2029 escaped, so no claim text can close it.
- The page loads nothing from the network and sends nothing, and its Content-Security-Policy makes the browser enforce it: no request, image, font, frame or form can leave the page. The decisions download still works.
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
| Every page draws with no JavaScript error, no unnamed control, no unlabelled field, no duplicate ID, one `h1`; the skip link is the first keyboard stop; nothing scrolls sideways at 1280 px; no network request; the decision flow, the queue, filters, roles and hostile text | `tests/test_ui_e2e.py` (headless Chrome) |

The Node and Chrome tests are skipped where Node or Chrome is not installed.

## Files

| Path | Role |
|---|---|
| `claimguard/ui/bundle.py` | gathers the run's files, computes routes, verifies the chain, scores against the gold |
| `claimguard/ui/page.py` | inlines CSS, icons, data and scripts into one HTML file |
| `claimguard/ui/decisions.py` | appends downloaded decisions to the chain, after checking them |
| `claimguard/review/correct.py` | correction → new version → recheck → `version_created` |
| `claimguard/review/gate.py` | the gate: ready or blocked per claim, exit code; `outcome()` is the twin of `Core.outcome` |
| `claimguard/review/feedback.py` | decisions summarized from the audit chain |
| `claimguard/ui/static/core.js` | pure logic: vocabulary, life cycle, stages, formatting (tested in Node) |
| `claimguard/ui/static/ui.js` | shared components, router, decisions store |
| `claimguard/ui/static/page-*.js` | one file per page; pages only assemble `ui.js` components |
| `claimguard/ui/static/app.css`, `icons.svg` | design tokens and components; one icon per concept |

## Limits

- No login: names and roles are self-declared (doc 10).
- Drafts live in one browser until downloaded; another browser does not see them.
- No time series: one run has no history, so there are no trend lines.
- Phase 2 is mock only: explanations are the rule's own text until the mentor gives the model key in a later phase and a live provider is wired (`claimguard/ai/provider.py`). With a live model, an explanation can name a patient or member only by its placeholder (`[patient-1]`); the finding's evidence still shows the real value.
- The page shows the run it was built from; it cannot start a run. Rebuild after each run, decision append or correction.
