# ClaimGuard AI · review page baseline (P1)

The review page as it stands before the redesign (Track B of master plan revision 4): what it measures, how it looks at four widths, and what fails a keyboard-only walk. P8 repeats the same measurement on the redesigned page and compares against the numbers here.

| | |
|---|---|
| Team · date | MedNexus · 27 Oct 2026 |
| Commit | `e242c16` (M9, branch `mak/m9-one-step-apply`, PR #36) |
| Page | Development split: 400 claims, 7 audit events, evaluation on; 5,282,509 bytes |
| Browser | Headless Chrome 137.0.7151.68 on Windows 11, file opened from disk, no throttling |
| Script | `scripts/ui_baseline.mjs`, 9 runs per number, medians |

## 1. How to repeat it

```
python -m claimguard.run --input data/development/claims.jsonl --output outputs/dev_predictions.jsonl --explain --audit-log outputs/audit.jsonl
python -m claimguard.ui --results outputs/dev_predictions.jsonl --claims data/development/claims.jsonl --audit-log outputs/audit.jsonl --gold data/development/expected_results.jsonl
node scripts/ui_baseline.mjs <chrome> outputs/claimguard.html outputs/p1_baseline 9
```

It writes `baseline.json` (every number below, with each run) and 40 screenshots, `screens/<page>@<width>.png`, the "before" set for the report. `outputs/` is not committed. Pages taller than 6,000 px are cut at 6,000 px.

For P8, measure the old and the new page back to back on the same machine: whole-run medians of the first frame moved between 85 and 103 ms over two runs of the same page.

## 2. Size and render time

| Measure | Baseline | Notes |
|---|---|---|
| Page size | 5.28 MB | 5.12 MB (97 %) is the embedded run data; CSS, JS and icons are about 160 KB |
| First frame with content, cold load | **85 ms** (72 to 151) | From navigation start to the first frame after the page has drawn itself. Chrome reports no first-contentful-paint for a headless tab, so this is timed directly |
| DOMContentLoaded | 82 ms | The whole page is drawn by one inline script before this event |
| Script time per load | 28 ms | |
| Layout time per load | 3 ms | 45 ms on the first load of a session |

Moving between pages inside the loaded page (hash change to the next frame):

| Page | Drawn | Next frame | Elements |
|---|---|---|---|
| Dashboard | 6 ms | 17 ms | 508 |
| Review Queue | 26 ms | **137 ms** | 7,148 |
| Claims | 29 ms | **133 ms** | 10,244 |
| Claim `CG-785C09BD9CC8` | 4 ms | 20 ms | 778 |
| Audit Logs | 2 ms | 15 ms | 328 |
| Rules | 3 ms | 18 ms | 600 |
| Rule R013 | 8 ms | 35 ms | 1,963 |
| Evaluation | 3 ms | 19 ms | 618 |
| Settings | 2 ms | 8 ms | 423 |
| Components | 4 ms | 23 ms | 974 |

The "over 5 seconds" seen earlier was the desktop app's preview pane loading the file over a local server. In Chrome the page is fast; the cost is in the Queue and Claims lists, which draw every row (264 and 400) at once.

## 3. Width

Sideways scroll, in pixels, of the whole page:

| Width | Every page |
|---|---|
| 375 px | **244 to 268 px** on all ten pages |
| 768 px | 0 |
| 1280 px | 0 |
| 1440 px | 0 |

## 4. Keyboard and structure

Checked on every page at 1440 px by pressing Tab from the top and recording each stop, plus a structure check (landmarks, headings, names and labels).

What holds:

- The skip link is the first stop and moves focus to the content.
- Every stop shows a focus ring (3 px `--focus` outline); no stop is hidden or zero-sized.
- One `header`, `nav`, `main` and `aside` per page; one `h1`; `lang` set.
- Every control has a name and every field a label. No positive `tabindex`.
- The side panel is a modal dialog done right: focus moves into it, stays in it, Escape closes it, focus returns to the opener.
- Sortable columns are buttons, and the header cell carries `aria-sort`.

Stops per page (capped at 120):

| Page | Stops | Before the content | To the first decision |
|---|---|---|---|
| Dashboard | 36 | 11 | |
| Review Queue | 120+ | 11 | |
| Claims | 120+ | 11 | |
| Claim `CG-785C09BD9CC8` | 54 | 11 | **41** |
| Audit Logs | 13 | 11 | |
| Rules | 32 | 11 | |
| Rule R013 | 83 | 11 | |
| Evaluation | 36 | 11 | |
| Settings | 12 | 11 | |
| Components | 31 | 11 | 17 |

## 5. Findings

Each finding names the plan item that fixes it. **K** = keyboard or assistive technology, **L** = layout, **W** = review workflow, **C** = copy, **P** = performance.

| # | Kind | Finding | Where | Fixed in |
|---|---|---|---|---|
| 1 | L | Below 768 px the page is unusable. The sidebar stays 240 px wide and nothing collapses, so at 375 px the content gets about 135 px, text breaks one letter per line and every page scrolls sideways by 244 to 268 px. The only breakpoints are at 1360 and 1100 px. | `app.css` `.app`, `@media` | P7 |
| 2 | K | On a claim, "Your name" is the **last** tab stop (54 of 54), after both findings, but Save stays disabled until it is filled. A keyboard user tabs 41 stops to the first decision, finds Save disabled, tabs to the end for the name, then back up. On screen the name card sits top right, so focus order and visual order disagree. | `page-claims.js` side column | P3 |
| 3 | K | Every row of a clickable table is its own tab stop: 264 on the Queue, 400 on Claims, 56 on a rule. Reaching anything after the table takes hundreds of presses. Rows open on Enter only (not Space) and have no link or button role, so a screen reader does not announce them as actions. | `ui.js` `table()` | P4 (j/k and Enter, one stop per list) |
| 4 | W | On a claim at 1440 × 900 the first decision button is about 1,560 px down. Above it: the life cycle (8 buttons), the escalation callout, and all 15 checks as equal-weight tiles, 13 of them green. Each finding takes about 770 px. | Claim page | P3 (three panes), fingerprint (P2) |
| 5 | W | The reason box says "Recorded with your name in the audit log", but a saved decision is a draft in this browser until an admin appends it. | `page-claims.js` textarea placeholder | P3 (M6 copy) |
| 6 | C | "Download decisions" is a primary button on Queue, Claims and Settings, and the Queue spends a stat card on it. It is an export, not the main action. "View as" reads like access control; it is a demo switch. | `page-queue.js`, `page-claims.js`, `page-settings.js`, `main.js` | P3 (M6 copy), P4 |
| 7 | K | Headings jump from `h1` to `h3` (card titles) on six pages: Dashboard, Queue, Audit, Rules, Evaluation and Settings. | `card()` titles | P2 |
| 8 | K | Evidence tables (one per finding) and the expected-against-predicted matrices have no caption or name; the generic `table()` has one. | `ui.js` evidence and matrix tables | P3, P5 |
| 9 | K | Eleven stops before the content on every page (skip link, seven nav links, "Set your name", search, role). The skip link makes this acceptable; the shorter reviewer nav in P4 cuts it. | Shell | P4 |
| 10 | K | Nothing announces that a draft was saved: no live region on the claim page or the dashboard. | Claim page | P7 |
| 11 | K | Tabs (`role=tab`) have no arrow-key movement, `aria-controls` or roving tab index, and the panel has no name. Only the Components page uses them today; fix before P3 or P5 adopts them. | `ui.js` `tabs()` | P2 |
| 12 | P | The Queue and Claims lists draw every row: 7,148 and 10,244 elements, 133 to 137 ms to the next frame. Fine on this machine, the first thing to slow down on a weak one. | `ClaimViews.list` | P4 |
| 13 | L | No dark theme: `app.css` has no `prefers-color-scheme` rule. | `app.css` | P2 |
| 14 | C | "Click a rule to open it" (Evaluation) assumes a mouse. | `page-evaluation.js` | P5 |

Not a finding: in the full-page screenshots the dark sidebar stops at 900 px. It is `position: sticky; height: 100vh`, so in a real window it stays put while the page scrolls.

## 6. What P8 compares

- First frame with content no worse than the 85 ms here, measured back to back with this build (section 1).
- Queue and Claims next frame no worse than 137 and 133 ms.
- 0 px sideways scroll at all four widths, 375 px included.
- Keyboard: on a claim, the first decision reachable within the first stops of the content, and the name field before Save in tab order; no list costs one stop per row.
- The "after" screenshots taken with the same script and widths.

## 7. Progress after P3

Measured with the same script on the same machine, back to back with this baseline (three rounds each).

| # | Finding | After P3 (`mak/p3-review-workspace`) |
|---|---|---|
| 2 | Name field last in tab order | The name field sits beside Save in each decision panel. The keyboard e2e test types it on the way to Save. |
| 3 | One tab stop per row | Fixed in the claim workspace: the findings list is one stop (roving focus), with j / k and the arrow keys to move and Enter to open. The Queue and Claims tables are P4. |
| 4 | First decision 1,560 px down | The claim is a three-pane workspace. At 1440 × 900 the whole first finding, Save included, is on screen (Save ends at 861 px). The first decision is tab stop 22 from the top, was 41; from the content, 5 stops reach the findings list and 7 more the first action. |
| 5 | Reason box promises the audit log | Now "Kept with your name in this browser's draft"; the label says an administrator adds drafts to the audit log. |
| 6 | Download as the main action; "View as" | "Download decisions" is a secondary button on Queue, Claims and Settings, and in a drafts banner ("not in the audit log until an administrator appends them"). The switch reads "Demo: view as". |
| 8 | Evidence tables without a name | Named ("Evidence the engine cited"). |
| 10 | Nothing announces a saved draft | Announced on the claim page ("Draft saved for R003. Next: R004 …"). |

Render time is unchanged: first frame 77–98 ms against 80–97 ms for this baseline, the claim page 20–21 ms against 21–23 ms. P2 closed 13 (dark theme). Still open: 1 (375 px, P7); 3 for the Queue and Claims tables, 9 and 12 (P4); 7 and 11 (heading levels, tab keys); 14 (P5).

## 8. Progress after P4

Measured with the same script, P4 against the P3 build of the same run, back to back, three rounds each (medians of 9 runs per round). This machine was slower than on the P1 day for both builds, so compare the two columns, not either one with section 2.

| # | Finding | After P4 (`mak/p4-queue-nav`) |
|---|---|---|
| 3 | One tab stop per row | Every table that opens something is one tab stop. Its first cell holds a real link (or a button, for a table that opens a panel), so a screen reader announces the action. ↑ ↓ or j / k move, Home and End jump, Enter or Space opens, and one Tab leaves the table. Tab stops on the Queue page: 32, were 120 or more (the walk stops at 120); Claims 29; Rules 16, were 32. |
| 6 | The Queue spends a stat card on drafts | The drafts card is gone; drafts show in the same banner as on Claims. The fourth card is "Not started", a link to that filter. The Queue's first action is "Next to decide": the first claim of the list, as filtered and sorted, with a finding left to decide. |
| 9 | Eleven stops before the content | A reviewer's nav is Review Queue, Claims, Rules and Settings, with Dashboard, Audit Logs and Evaluation under "More" (one stop while closed, opened on its own pages). The content is now stop 10 on the Queue, Claims and Rules, was 12. An administrator keeps all seven links. It is a convenience, not access control: every page opens at its address for both roles. |
| 12 | Lists draw every row | A claim list draws 50 rows and a "Show 50 more" button (other tables 100). Queue: 2,455 elements, next frame 55–87 ms, against 7,148 and 141–248 ms for P3. Claims: 2,398 elements, 46–62 ms, against 10,244 and 166–320 ms. |

Also in P4:

- **Home page.** An address without a page opens the Review Queue for a reviewer and the dashboard for an administrator.
- **Fingerprint rows.** Queue and Claims rows show the claim's 15 checks as a fingerprint (its current version, as on the claim header), then the findings in words.
- **Filters and sort in the address.** The sort joins the filters (`?route=REVIEW&sort=-total`), so a reload, a shared link or Back keeps both. A claim's Previous / Next follow the order on screen, sort included (before, a column sort did not reach them), and its back link returns to the list it came from with its filters ("Review Queue", "All claims" or the rule).
- **Next open claim.** When the last finding of a claim is decided, the finding pane says so and the focus moves to "Next open claim: CG-…", the next claim of that list with a finding left to decide (from the top again after the end). The e2e test checks it.

First frame is unchanged within the noise: 122–221 ms for P4 against 139–193 ms for P3 in the same rounds; the claim page 21–23 ms against 22–38 ms. Still open: 1 (375 px, P7); 7 and 11 (heading levels, tab keys); 14 (P5).

## 9. Progress after P5

The dashboard is now a command center, with the run's eight-stage life cycle still as its spine. Measured as in section 8, P5 against the P4 build, three rounds back to back.

- **Every number opens its list.** The four stat cards open the Review Queue, the ready claims, the flagged claims and the rejected records (`#/dashboard?focus=rejected` scrolls to them and moves the focus). Each bar of "Where the review stands" opens the claims at that stage, each route bar the claims on that route, and each row of "Rules most often failing or unassessed" the claims that rule failed or could not assess (it opened the rule before).
- **Every card names its source:** the run manifest, the results (with "routed by the fixed rules" where the route is computed), the audit log, or this browser. The life cycle uses all four.
- **A card that answered no question is gone.** "Results", the status of all 6,000 checks, is replaced by "Where the review stands": the claims at each stage, from To review to Ready for submission. "Records received" moves into the life cycle (stage 1); its stat card is now "Rejected at ingestion", out of the records received.
- **Empty states point to the next action.** "No draft in this browser" links to the Review Queue; "No rule failed" to every claim; a page built without an audit log says to ask an administrator for one built with it (the page never shows a command).
- **New card "Your drafts"** (source: this browser): the decisions saved here and not yet in the audit log, with the download, in place of the banner.
- Finding 14 closed: Evaluation's "Click a rule to open it" now reads "Each rule opens its page: logic, policy values and the claims it flagged".

Nothing was added that the data cannot hold: no turnaround, trend or workload per reviewer.

Render time: the dashboard's next frame is 34–44 ms against 25–33 ms for P4 in the same rounds, from the extra bars and cards. First frame (the dashboard, cold) 121–151 ms against 107–230 ms, within this machine's noise today. Sideways scroll is 0 px at 768, 1280 and 1440 px; 375 px is still P7. Still open: 1 (375 px, P7); 7 and 11 (heading levels, tab keys).

## 10. Progress after P6

Purposeful motion, as set out in `docs/DESIGN_SYSTEM.md` section 5: a fade between pages, the dashboard's sections rising in three short steps, a finding sliding into its pane, the evidence thread drawing itself, a saved draft popping in the findings list, and the drawer sliding in. Nothing runs past 300 ms, keyframes move transform and opacity only, and reduced motion turns all of it off (the e2e test checks both, in a real browser).

View Transitions, which the plan suggested, were dropped: they draw the new page a frame late, and while one ran every page scrolled sideways by 15 px, a scrollbar's width.

Measured as before, P6 against the P5 build, three rounds back to back: first frame 143–222 ms against 134–203 ms, the dashboard 30–37 ms against 33–36 ms, the Queue 63–100 ms against 84–91 ms, all within this machine's noise; the claim page 25–35 ms against 23–25 ms, a few ms for the sliding finding. Sideways scroll unchanged: 0 px at 768, 1280 and 1440 px; 375 px is P7.

## 11. Progress after P7

Responsive layout and accessibility, as set out in `docs/DESIGN_SYSTEM.md` section 6. Measured as before, P7 against the P6 build, three rounds back to back.

| # | Finding | After P7 (`mak/p7-responsive`) |
|---|---|---|
| 1 | Unusable below 768 px | 0 px of sideways scroll on every page at 375, 768, 1280 and 1440 px, against 246 px at 375 px for P6. Below 1100 px the sidebar is a drawer behind a menu button; below 768 px everything is one column and the top bar wraps. The e2e test now checks all four widths, ten pages each, and names what sticks out when one fails. |
| 7 | Headings jump from h1 to h3 | Card titles are h2, or h3 under a page's own h2. The e2e accessibility check fails any page whose headings skip a level. |
| 10 | Nothing announces a saved draft | Done in P3 (the claim page's live region); the dashboard saves nothing. |
| 11 | Tabs without arrow keys | One tab stop; the arrow keys, Home and End move and open; `aria-controls`, a named panel. |

Also: Escape moves the focus back from a finding to the findings list, and, where the claim data sits under the finding, from a cited field back to its chip. The e2e run found one more overflow at 375 px: a callout quoting a long file path (the expected-results file on Evaluation), now allowed to break anywhere.

Render time within the noise: first frame 103–171 ms against 106–165 ms, dashboard 17–38 ms against 18–32 ms, Queue 50–71 ms against 56–140 ms, claim page 23–39 ms against 34–55 ms. Keyboard at 1440 px unchanged (the menu button shows only below 1100 px).

All 14 findings of section 5 are now closed. P8 reruns this script on the final build for the before-and-after comparison.

**Found by CI after P7 was pushed.** On GitHub's Linux runners the Queue still scrolled sideways by 35 px at 375 px: Linux draws with DejaVu Sans, wider than Windows' Segoe UI, and a `<select>` is as wide as its longest option ("R002 · Service and submission chronology"). A wide-font pass (Verdana, or DejaVu Sans where Verdana is missing) reproduced it on Windows and found two more: an unbreakable token in Rule R013's rulebook text, `policy.max_unit_price[service_code],` (10 px), and the largest type specimen on Components (6 px). Fixed: fields and selects never exceed their row, text breaks inside a long word rather than scroll the page, and the type specimens stack below 768 px. The e2e test now runs the ten pages at 375 px with that wide font as well.
