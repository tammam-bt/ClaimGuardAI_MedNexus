# ClaimGuard AI · design system v2 (P2)

The tokens, themes, type and signature components of the review page, as built for plan item P2 (master plan revision 4, Track B). The tokens live at the top of `claimguard/ui/static/app.css`. Every component appears, in every state, on the page's `#/components` route.

## 1. Direction

| | Decision |
|---|---|
| Colour | Refined teal (brand, actions) and navy (ink, surfaces, sidebar). Status colours stay apart from teal. |
| Theme | Light first. Dark follows the system (`prefers-color-scheme`), or the reviewer picks it in Settings › You › Theme. |
| Fonts | System fonts: `system-ui` and its fallbacks for text. A monospace stack (`ui-monospace, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace`) for code, IDs and numeric data: table numbers, stat values, bar values. No web font, so the page's `default-src 'none'` policy is unchanged. |

## 2. Tokens

Two layers. Components use only the second.

1. **Primitives** (`:root`): teal and navy scales 50 to 950, the status hues (green, amber, red, blue), type, spacing, radius, motion, z-index, focus ring, layout and breakpoints.
2. **Semantic colours** (`--color-*`): what a colour is for (`--color-text-muted`, `--color-surface-raised`, `--color-error-subtle`, `--color-chart-fail`…). The light set is on `:root`. The dark set appears twice, in `@media (prefers-color-scheme: dark)` and on `:root[data-theme="dark"]`, because CSS cannot share one block between them.

Surfaces: `--color-surface` is the page ground, `--color-surface-raised` the cards and panels, and `--color-bg` the top bar and inputs. `--color-surface-muted` and `--color-surface-strong` are tints inside a card (table heads; tracks, counts, disabled controls).

Type: sizes `--text-xs` (12) to `--text-4xl` (36), with 14 px (`--text-sm`) as the interface's body size. Weights `--weight-regular` to `--weight-bold`; line heights `--leading-tight`, `-snug`, `-normal`. Monospace runs large beside the sans, so it is set at `--font-mono-scale` (0.92 em).

Breakpoints: `--bp-md` 768, `--bp-lg` 1100, `--bp-xl` 1360 px. A media query cannot read a custom property, so the `@media` rules repeat the values and a test checks that they match.

## 3. What the tests hold

| Test | Holds |
|---|---|
| `test_ui_contrast.test_every_text_pair_meets_aa_in_both_themes` | 40 text pairs, 4.5:1 or better, in each theme |
| `test_ui_contrast.test_focus_ring_is_visible_in_both_themes` | Focus ring 3:1 on the top bar, page ground, cards and sidebar |
| `test_ui_contrast.test_chart_fills_stand_out_from_their_track` | Every chart fill 3:1 on its track |
| `test_ui_contrast.test_every_semantic_token_is_set_in_both_themes` | No semantic token missing from a theme |
| `test_ui_contrast.test_the_two_dark_blocks_are_identical` | The two dark blocks never drift apart |
| `test_ui_core.test_colors_live_only_in_the_tokens` | No colour outside the four token blocks |
| `test_ui_core.test_type_layers_and_motion_come_from_tokens` | Every font family, size, weight, line height, z-index and transition duration is a token |
| `test_ui_core.test_media_queries_use_the_breakpoint_tokens` | Every `@media` width is a breakpoint token |

Lowest contrast in each theme, from the stylesheet:

| | Light | Dark |
|---|---|---|
| Body text on a card | 16.65 | 12.93 |
| Muted text on a card | 8.47 | 9.28 |
| Subtle text, lowest pair | 4.81 (on `--surface-strong`) | 5.12 (on `--surface-strong`) |
| Status text on its tint, lowest | 4.56 (success, clear) | 6.61 (error) |
| Focus ring, lowest | 3.83 | 8.68 |
| Chart fill on its track, lowest | 3.01 (neutral) | 4.41 (fail) |

Three values of the first proposal failed and were changed. The light focus ring was teal-500 at 2.90:1 on white; it is now teal-600. Warning text was amber-700 on amber-100 at 4.45:1; it is now amber-800. Dark subtle text was navy-400 on navy-800 at 3.86:1; dark muted text is now navy-200 and subtle text navy-300.

## 4. Signature components

All are in `ui.js` and take their state as arguments. P3 wires them into the claim page and P4 into the queue.

| Component | What it is | States on `#/components` |
|---|---|---|
| `fingerprint(results, { size })` | A claim's 15 checks as 15 cells in rule order. Each status has its own shape as well as colour: fail a solid block, unable hatched, not implemented a dashed outline, not applicable a low hollow cell, pass a short bar. One label sums it up for a screen reader. | Legend; escalate, review and clear claims; small (rows) and medium (header) |
| `evidenceChip(e, claim, { onShow, active })` | A cited field and its value. With `onShow` it is a toggle, pressed while the field is highlighted: the hook for the evidence thread. | Default, pressed, missing value, structured value, not interactive |
| `findingBlock({ result, claimLayer, explanationLayer, decisionLayer, selected })` | One finding in three labelled layers: from the claim, explanation, your decision. | Selected, with chips, rule explanation and a decision panel |
| `decisionPanel({ … })` | The four actions, a required reason and Save. It updates itself as the reviewer works, so focus never jumps. "Your name" sits beside Save when it is missing, so the keyboard meets it on the way (P1 finding 2). Dismiss settles a finding, so it asks once more, with the focus on "Yes, dismiss". A browser that will not store the draft says so, and the reason stays. Copy says "draft", never "audit log", until an administrator appends it (M6). Two actions per row in a narrow panel, four when it has room. | No name, no reason, ready, asks before Dismiss, draft saved, not stored, check did not run |
| `timeline(items)` | A claim's history. A logged event has a solid mark and line; a draft a dashed one, and the words "Draft, not in the audit log". | Logged and draft |
| `openPanel(title, body)` | The drawer, a modal side panel: focus moves in and stays, Escape closes it, focus returns to the opener. | Opens from a button |
| `table({ rowHref \| onRowClick, pageSize, sort, onOrder })` | A table whose rows open something (P4). The first cell holds a real link (`rowHref`) or button (`onRowClick`), so a screen reader announces the action; a click anywhere on the row opens it. The whole table is one tab stop: ↑ ↓ or j / k move, Home and End jump, Enter or Space opens. It draws `pageSize` rows (100 by default, 50 for claims) and a "Show more" button that hands the keyboard to the first new row. `onOrder` hears each draw with all rows in their order, which the claim lists use to keep the sort in the address and the claim page's Previous / Next in step. | Sample claims, opening a panel |

## 5. Checked on which systems

System fonts change the face, not the scale. Checked so far:

| System | Browser | Text | Numbers and code | Result |
|---|---|---|---|---|
| Windows 11 | Chrome 137 | Segoe UI | Consolas | Checked: screenshots of both themes, every component state, no console error |
| macOS or iOS | Safari | San Francisco (expected) | SF Mono (expected) | **Not yet checked** |

To check on an Apple device: build the page, open `#/components` in Safari, then go through the cards below in light and dark (Settings › You › Theme).

- **Type card:** every row on one line at 1440 px, and the numbers in SF Mono at the same visual size as the text beside them.
- **Check fingerprint card:** the cells line up on the baseline.
- **Decision panel card:** buttons wrap, never overflow.
