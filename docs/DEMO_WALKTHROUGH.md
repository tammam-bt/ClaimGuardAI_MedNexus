# ClaimGuard AI · demo walkthrough

About ten minutes, on the development split: a reviewer works the queue and decides a claim by keyboard, an administrator puts the decisions in the audit log with one command, and the chain shows what it detects and what it cannot. Every step and output below was run on 28 Oct 2026 (P8), from `mak/p7-responsive`.

## Before the demo

```bash
python -m claimguard.run --input data/development/claims.jsonl --output outputs/dev_predictions.jsonl \
    --explain --audit-log outputs/audit.jsonl
python -m claimguard.ui --results outputs/dev_predictions.jsonl --claims data/development/claims.jsonl \
    --audit-log outputs/audit.jsonl --gold data/development/expected_results.jsonl
```

Open `outputs/claimguard.html` in Chrome or Edge. If this browser has drafts from an earlier rehearsal of the same run, clear them first: Settings › Discard all drafts.

The demo uses `actors.example.json` as the actor directory ("Reviewer 01", "Reviewer 02", "Admin 01"). A real team keeps its own `actors.json`.

## 1. The reviewer's home (1 minute)

The page opens on the **Review Queue**: a reviewer's home.

- 264 open claims: 201 Escalate and 63 Review, all 264 not started. Each card opens its list.
- **Next to decide** is the first claim of the list with a finding left to decide, one button away.
- Each row carries the claim's **check fingerprint**: 15 cells, one per rule, told apart by shape as well as colour (a solid block failed, hatched could not assess, a short bar passed).
- Pick a route filter: it goes into the address, so the filtered list is a link that survives a reload.
- Keyboard: one Tab reaches the table; ↑ ↓ or j / k move, Enter opens.

Say: the queue never says "approve" or "reject". A clear result is a passed pre-check, never payer approval.

## 2. A claim, decided by keyboard (3 to 4 minutes)

Type `CG-785C09BD9CC8` in the search box and press Enter. It is an Escalate claim with two high-severity findings: R003 (coverage not active on the service date) and R004 (member and beneficiary do not match).

1. **Three panes:** the findings, the finding being decided, the claim's data. The header holds the route, the stage, the total and the fingerprint.
2. **The evidence thread:** in "1. From the claim", press the chip **Coverage › End date 2026-04-09**. The same field lights up in the claim's data and a line draws under it. The engine cited this exact field; the page only points at it.
3. **Explanation:** labelled "Rule's explanation". This run uses the mock explainer, so nothing is called AI.
4. **Decide:** Tab to **Dismiss with reason**, press Space, Tab to the reason, type *Coverage extension confirmed by the payer.*, then your name (*Reviewer 01*), Tab to **Save draft**, Enter. Dismiss settles a finding, so the page asks once more: **Yes, dismiss**.
5. The next finding, R004, opens by itself, and the page announces "Draft saved for R003. Next: R004 …" in a live region for screen readers. Dismiss it the same way (*Member record corrected upstream.*).
6. **Every finding on this claim is decided**, and the focus is on **Next open claim**: Enter would start the next one.
7. Escape on a finding goes back to the list; Enter goes in.

Say: these are **drafts in this browser**, not yet in the audit log. The banner says so. The claim's stage already counts them ("Ready for submission"), but the gate will not until they are appended.

## 3. The run at a glance (1 to 2 minutes)

Switch **Demo: view as** to Admin. The page says "Demo" because it is a demonstration switch, not access control: there is no login. The Dashboard is an administrator's home.

- The run's **life cycle** in eight stages: 400 records, 400 accepted, 6,000 checks, 4 flagged for injection, 495 explained and 4 withheld, 201 escalate · 63 review · 136 clear, the review, the outcome.
- **Every number opens the list it counts**, and **every card names its source**: the run manifest, the results, the audit log or this browser.
- **Your drafts:** the two decisions, and the download.

## 4. Into the audit log, in one step (2 minutes)

Press **Download decisions (2)**. The browser saves `review_decisions_<run>.jsonl`. Then, as the administrator:

```bash
python -m claimguard.ui.apply --decisions <downloads>/review_decisions_<run>.jsonl --log outputs/audit.jsonl \
    --directory actors.example.json --results outputs/dev_predictions.jsonl --claims data/development/claims.jsonl \
    --gold data/development/expected_results.jsonl
```

It prints, on this run:

```
2 decision(s) appended, 0 already in the audit log.
400 claims: 137 ready, 263 blocked (263 to_review).
Page rebuilt: <the page>
Record this outside this machine (pull request description, email to the mentor, or a git tag): --expect-count 10 --expect-head <hash>
```

- Every decision is checked before any is appended: the actor and role, the claim version, the finding's current status. One bad decision appends nothing.
- 137 ready: the 136 clear claims and CG-785C09BD9CC8. The exit code is 1 because 263 claims are still blocked, as the gate's is.
- Running it again appends nothing ("0 decision(s) appended, 2 already in the audit log").
- Write the count and head down outside this machine: that is what makes a later rewrite detectable.

Reload the page, then clear the drafts that are now in the log (Settings › Discard all drafts). On the claim, each finding now reads "In the audit log", by Reviewer 01. The Audit Logs page shows the two `review_decision` events and, for an admin, who ran the append.

## 4b. The same, with no terminal: the local server (2 minutes, if B0 stays "go")

Start the server once, as the administrator, on a fresh copy of the run's log:

```bash
python -m claimguard.ui.serve --results outputs/dev_predictions.jsonl --claims data/development/claims.jsonl     --log outputs/audit.jsonl --directory actors.example.json --corrections outputs/corrections     --gold data/development/expected_results.jsonl
```

Open the address it prints (`http://127.0.0.1:8765/?token=…`). The token leaves the address bar at once.

- Decide the two findings of CG-785C09BD9CC8 as in section 2. The banner now offers **Save to the audit log (2)** beside the download. Press it: the page reloads, each finding reads "In the audit log", and the notice gives the log's new count and head and the gate's verdict. No file, no command.
- Show a refusal: Settings › Local server tells what the server checked; a decision on a status that changed is refused with its reason, and the draft stays.
- **Correct this claim** on CG-B39790AC3604: field *Line L1 › Authorization ID*, new value `AUTH-CG-B39790AC3604-1`, a reason, **Recheck as a new version**. The page reloads on v2: R008 went from failed to passed, R009 now fails. The claim as received is still shown, unchanged.
- Stop the server with Ctrl+C: it prints the count and head to record. Open `outputs/claimguard.html` as a file: it works as before, offline, and its download is the way in.

Say: the server only removes the download and the command. It runs the same checks, through the same code, and answers only this machine.

## 5. What the chain detects, and what it cannot (1 minute)

```bash
python -m claimguard.audit.tamper_demo --log outputs/audit.jsonl
```

It works on copies and shows each case. Every edit, removal, deletion and rewrite is detected, except one: when both the log and its anchor are rewritten, the chain verifies. Only the head recorded outside the machine catches it ("both rewritten, head held outside: detected").

Say: tamper-evident, not immutable.

## 6. Narrow screen (optional, 30 seconds)

Make the window narrow. Below 1100 px the sidebar becomes a drawer behind the menu button; below 768 px the page is one column, with nothing scrolling sideways. Reduced motion in the operating system turns every animation off.

## What not to claim

- "Accuracy 1.0" is agreement with the pack's reference labels on the public splits, not clinical or contractual correctness. Nobody has scored the hidden split.
- The explanations are the rules' own text: no model was called.
- Reviewer names are self-declared, checked against a directory file. The role switch is a demonstration.
- The page and the chain run on one machine, with no immutable storage. The local server answers only that machine. Its sign-in is optional and, on a machine where reviewers share the server's account, proves nothing (DEC-016).
