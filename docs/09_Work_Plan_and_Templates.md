# 09 | Work plan and submission templates

This is a suggested four-week sequence. Adjust to the organizer's actual calendar; no dates or available team hours have been assumed.

| Stage | Focus | Exit evidence |
|---|---|---|
| Week 1 | Understand data; run baseline; implement core validation | Reproducible setup, data map, first tests and review screenshot. |
| Week 2 | Complete 15 rules; evidence and uncertainty | Per-rule metrics, edge-case tests, complete structured outputs. |
| Week 3 | Bounded AI; review workflow; audit | Grounded explanation examples, failure fallback, human action trace. |
| Week 4 | Evaluation; hardening; documentation; demo | Frozen version, error analysis, demo video, report and pitch. |

## Suggested weekly mentor review: 30 minutes

Five minutes on a working demonstration; ten on errors and evidence; ten on decisions/blockers; five on next commitments. Bring concrete claims and rule IDs, not only screenshots or general progress percentages.

## Definition of done for each rule

The rule is documented, implemented, emits the correct schema, references original evidence, handles nulls and boundaries, has at least one positive/negative/unknown test where applicable, and has been reviewed by another teammate. Record any rule clarification in a versioned decision log before changing expected behaviour.

## Included editable templates

templates/Architecture_Decisions.md records context, options, decision and consequences. templates/Evaluation_Report.md records versions, metrics, error analysis and limits. templates/Weekly_Update.md captures a demo, decisions, blockers and commitments. templates/Final_Submission_Checklist.md is the final handover checklist.

## Suggested final demonstration: 7 minutes

One minute: problem and scope. Two minutes: clean claim and clear issues. One minute: uncertainty and information request. One minute: grounded AI explanation plus fallback. One minute: evidence, review and audit trail. One minute: measured results, limitations and next steps. Follow the organizer's actual presentation time if different.

Avoid promising a real denial-reduction percentage from this synthetic exercise. Explain which administrative errors your implementation detects and how you measured them.
