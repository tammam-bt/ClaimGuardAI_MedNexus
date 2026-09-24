# 15 | Initial team backlog

Each task should have an owner and a short review note. The order below follows dependencies. Keep the code simple until all checks and evidence are correct.

| ID | Task | Completion evidence |
|---|---|---|
| T01 | Run baseline, tests and validation on every teammate's laptop | Saved terminal output and setup note. |
| T02 | Explain three worked cases without looking at labels | Manual findings with pointers and rule IDs. |
| T03 | Add R002, R004 and R005 | Positive, negative and unknown tests. |
| T04 | Add R007, R012 and R015 | Decimal/tolerance cases and currency mismatch. |
| T05 | Add R011 and R013 | Unknown code, limit boundaries and invalid quantities. |
| T06 | Add R008 and R009 | Missing references, absent records and aggregate limits. |
| T07 | Add R010 and R014 | Document identity/status and submission boundaries. |
| T08 | Produce all 15 results per claim | Strict evaluator accepts a complete run. |
| T09 | Add a model explanation adapter and fallback | Manual scorecard and invalid-output tests. |
| T10 | Build review queue and correction/recheck workflow | Source and decisions remain separate. |
| T11 | Add run-level trace metadata | Input hash, rule/model/prompt versions and errors. |
| T12 | Freeze and evaluate a release | Versioned report, error analysis and demo. |

Stretch tasks after the core MVP: a selected FHIR ingestion adapter with explicit unsupported fields; policy version switching; comparison of two model explanation approaches; authenticated review and a durable audit design. Do not expand into real patient data, clinical decisions or live claim submission for this challenge.
