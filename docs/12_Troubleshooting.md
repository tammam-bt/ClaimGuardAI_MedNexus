# 12 | Troubleshooting and common mistakes

| Symptom | What to check |
|---|---|
| python command not found | Try py on Windows or python3 on macOS/Linux; install/configure Python if absent. |
| File not found | Run commands from the extracted student root containing README.md. |
| Low baseline score | Expected: only R001, R003 and R006 are implemented. Inspect per-rule metrics. |
| Missing/extra prediction pairs | Supply every claim and all 15 rules exactly once; do not score a limited run against full gold. |
| Evidence mismatch | Preserve original values and zero-based JSON pointer indices; do not cite transformed copies. |
| Apparent duplicate findings | R008 and R009, or R007 and R012, check different conditions; inspect the rulebook. |
| Boundary date fails | Dates are inclusive; use service date, never the computer's current date. |
| 0.01 amount difference fails | The tolerance is inclusive; use Decimal and ROUND_HALF_UP. |
| Unknown policy treated as valid | An absent policy prevents dependent checks; report unable to assess. |
| Review decision disappeared | Download decisions before closing/reloading the browser tab. The static page has no database. |
| Audit verification fails | Inspect whether earlier content was modified; work on a copy for tamper exercises. |
| FHIR does not contain every field | The normalized envelope is the authoritative sidecar; see the mapping limits. |

When asking the mentor for help, include the claim ID, rule ID, expected and actual status, relevant evidence paths, command used and version/commit. Do not paste API keys or real patient data.

If you disagree with a label, build the smallest example and explain the exact rule wording. Record a clarification and version change rather than silently changing the benchmark or copying a label into your prediction code.
