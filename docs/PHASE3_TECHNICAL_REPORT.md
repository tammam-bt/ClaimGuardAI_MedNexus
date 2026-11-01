# ClaimGuard AI — Phase 3 Technical Report

**Team:** MedNexus  
**Project:** ClaimGuard AI — synthetic healthcare-claim pre-validation and human review  
**Report date:** 1 November 2026  
**Repository:** [tammam-bt/ClaimGuardAI_MedNexus](https://github.com/tammam-bt/ClaimGuardAI_MedNexus)  
**Current repository revision:** `932f59d`  
**Data classification:** Synthetic educational data only

> This report describes the implementation in this repository. It does not claim
> clinical validity, payer approval, production readiness, or independent
> validation on real healthcare data.

## Abstract

ClaimGuard AI is a Python prototype that pre-validates synthetic healthcare
claims against a fictional payer rule catalogue and presents findings for human
review. It accepts normalized JSONL, relational CSV exports, and a constrained
educational FHIR R4 projection. The deterministic engine evaluates 15 rules
and emits structured findings with rule-linked evidence, severity, and
corrective actions. Claims can be routed to review or escalation, corrected
and rechecked as a new version, and held behind a review gate until required
decisions are recorded.

The review experience is provided as a self-contained HTML/CSS/JavaScript
interface. It can be opened offline or served by an optional local Python
server that saves decisions and corrections through the existing review
workflow. A hash-chained audit log detects many forms of tampering, but is not
immutable storage. The optional explanation component currently uses a mock
provider, not a live language model. Public benchmark scores show agreement
with the supplied synthetic reference labels, not independent or clinical
performance.

## 1. Source-code repository and proof of concept

### Source repository

The source code, tests, synthetic datasets, schemas, rule catalogue, and
technical documentation are maintained at:

- GitHub: [https://github.com/tammam-bt/ClaimGuardAI_MedNexus](https://github.com/tammam-bt/ClaimGuardAI_MedNexus)
- Local application package: `claimguard/`
- Existing starter-pack scripts and assets: `src/`, `data/`, `rules/`,
  `schemas/`, and `examples/`

### Proof of concept

The PoC demonstrates the end-to-end flow:

1. Ingest and validate a synthetic claim package.
2. Run all 15 deterministic payer checks.
3. Generate structured results, a manifest, and optionally bounded
   explanations and audit events.
4. Route claims to `CLEAR`, `REVIEW`, or `ESCALATE`.
5. Review findings, inspect cited evidence, record a reasoned decision, and
   optionally correct and recheck a claim.
6. Verify that the audit chain and review gate accept or block the run as
   expected.

Example commands from the repository root (PowerShell):

```powershell
python -m claimguard.run --input data/development/claims.jsonl --output outputs/dev_predictions.jsonl --explain --audit-log outputs/audit.jsonl

python -m claimguard.ui.serve --results outputs/dev_predictions.jsonl --claims data/development/claims.jsonl --log outputs/audit.jsonl --directory actors.example.json --corrections outputs/corrections --gold data/development/expected_results.jsonl
```

Open the loopback address printed by the server in a browser on the same
machine. The server binds to `127.0.0.1`; its startup message includes a
per-launch token. For the offline PoC, generate the standalone page with
`python -m claimguard.ui` and open `outputs/claimguard.html`.

The local server is a demonstration component, not a remotely deployable
multi-user production service. See [docs/DEMO_WALKTHROUGH.md](./DEMO_WALKTHROUGH.md)
for a reproducible reviewer/admin walkthrough and
[docs/INTERFACE.md](./INTERFACE.md) for command options and safeguards.

## 2. Team overview and contributions

The contribution roles below follow the repository's team record. They describe
the assigned areas and should be confirmed by each member before final
submission.

| Team member | Main contribution |
|---|---|
| Tammam BenBettaieb | Team lead; system spine and audit |
| Malak Ben Othmane | Identity and catalogue rules: R002, R004, R005, R011, R015 |
| Mohammed Aziz Kadri | Money rules: R007, R012, R013; routing, evaluation, and review interface |
| Aymen Zahmoul | Authorization and document rules: R008, R009, R010, R014; correction workflow |
| Kacem Barhoumi | Ingestion, security guards, and AI explainer |

Development is collaborative. The detailed contribution history and role
records are in the repository and Git history. AI coding tools were used on
some work; the team remains responsible for understanding, testing, and
presenting the implementation. See [CONTRIBUTING.md](../CONTRIBUTING.md) and
[docs/PHASE2_WORKLOG.md](./PHASE2_WORKLOG.md).

## 3. Problem statement and industrial context

Healthcare claims can contain missing fields, inconsistent identities or
dates, unsupported services, duplicate items, and incomplete documentation.
Finding such issues before submission can make review more focused. A useful
pre-validation tool must also explain what it found and where the evidence
comes from, while leaving decisions to authorized human reviewers.

ClaimGuard models this workflow for a fictional payer using invented claims,
codes, providers, and policies. It is an educational proof of concept: it does
not connect to a real payer, adjudicate or pay claims, provide clinical
guidance, or establish that a claim is medically necessary.

## 4. Proposed solution and user experience

The solution separates deterministic validation from human decisions:

- The engine is authoritative for rule status, severity, and evidence.
- The optional explanation component can produce explanation text only; it
  cannot change a finding.
- Routing highlights cases needing review or escalation.
- Review decisions require a reason and are checked against the actor
  directory, finding status, and claim version before being appended.
- A correction creates a new version and reruns the rules; it does not erase
  the original claim.
- The review gate checks whether required findings are resolved on the latest
  version.

### Interface mockup / principal screen

The implemented dashboard follows this layout; the repository's live interface
is the final interactive mockup:

```text
+-------------------+------------------------------------------------------+
| ClaimGuard AI     | Dashboard             Search claim/rule    Role     |
|                   +------------------------------------------------------+
| Dashboard         | Run lifecycle: received -> checked -> routed -> review|
| Review Queue      +--------------------+------------------+--------------+
| Claims            | Routing outcomes   | Review progress  | Drafts       |
| Audit Logs        +--------------------+------------------+--------------+
| Rules             | Rule outcome profile                | Audit status |
| Evaluation        +------------------------------------------------------+
| Settings          | Claims by route and other run summaries             |
+-------------------+------------------------------------------------------+
```

The claim review workspace presents findings, their rule-linked evidence,
explanations, and reviewer decisions as separate layers. Selecting an evidence
item can highlight the corresponding claim field. Reviewers can choose one of
the supported actions, provide a reason, save a browser draft, and—when using
the optional local server—save it to the audit log without switching to a
terminal.

### UX and accessibility decisions

- Seven main areas: Dashboard, Review Queue, Claims, Audit Logs, Rules,
  Evaluation, and Settings.
- Findings show status, severity, cited evidence, and corrective action.
- Search, filtering, sorting, keyboard navigation, and a next-open-claim flow
  support review of larger lists.
- Responsive navigation and a one-column layout support narrow screens.
- Light and dark themes, visible focus, reduced-motion support, and contrast
  checks are included.
- The interface distinguishes an unsaved draft from a decision in the audit
  log; it does not label a clean pre-check as payer approval.

The documented desktop/mobile, keyboard, and contrast evidence is in
[docs/DESIGN_SYSTEM.md](./DESIGN_SYSTEM.md),
[docs/UI_BASELINE.md](./UI_BASELINE.md), and
[docs/READINESS.md](./READINESS.md). Phone/tablet and screen-reader testing
remain areas for further verification.

## 5. System design

```text
Synthetic JSONL / CSV / supported FHIR projection
                        |
                        v
          Ingestion adapters + schema contract
                        |
                        v
          Python deterministic engine (15 rules)
               |                    |
               v                    v
       Structured results     Injection screening
               |                    |
               +---------+----------+
                         v
              Routing and optional explanation
                         |
              +----------+-----------+
              |                      |
              v                      v
      Static offline HTML       Local review server
                                     |
                       reasoned decision / correction
                                     |
                                     v
                     hash-chained audit + review gate
```

The key data flow is documented in [docs/ARCHITECTURE.md](./ARCHITECTURE.md).
The main code areas are:

| Area | Implementation |
|---|---|
| Ingestion and normalization | `claimguard/ingest/` |
| Rule execution and policy | `claimguard/engine/`, `claimguard/rules/`, `rules/` |
| Results, schemas, and evaluation | `schemas/`, `claimguard/evaluation/` |
| AI explanation and watchdog | `claimguard/ai/` |
| Security screening and roles | `claimguard/guards/` |
| Routing, corrections, feedback, and gate | `claimguard/review/` |
| Audit chain and manifest | `claimguard/audit/` |
| Web UI and optional local server | `claimguard/ui/` |

The FHIR adapter handles the repository's constrained educational projection
and uses a normalized sidecar for fields that projection does not carry. It is
not full validation against every HL7 FHIR profile. The audit chain is
tamper-evident, not immutable; an independently stored head and append-only
storage are needed for stronger guarantees.

## 6. Technologies, frameworks, and tools used

| Category | Used in this implementation |
|---|---|
| Core language | Python 3.10+ |
| Web interface | HTML, CSS, vanilla JavaScript; standalone offline page |
| Local web serving | Python standard-library HTTP server in `claimguard.ui.serve` |
| Data and interfaces | JSON, JSONL, CSV, JSON Schema, constrained educational FHIR R4 projection |
| Audit | SHA-256 hash chain with a local chain-head anchor |
| Testing | Python `unittest`; Node-based UI logic tests; headless Chrome end-to-end tests when configured |
| Dependencies | The core PoC does not require third-party runtime packages |

React/Next.js, FastAPI/Flask, LangChain/LangGraph, AutoGen/CrewAI, Docker,
WebSockets, OCR, and RAG are **not used by this implementation**. They are
possible future directions, not features to present as completed work.

## 7. Development milestones

| Milestone | Work completed |
|---|---|
| 1. Data contract and starter baseline | Defined the normalized claim/result schemas, synthetic datasets, rulebook, and baseline evaluation workflow. |
| 2. Ingestion and deterministic engine | Added JSONL, CSV, and constrained FHIR ingestion; implemented 15 deterministic rules and structured results. |
| 3. Explainability and safety controls | Added bounded explanation records, data minimization, injection screening, watchdog validation, and deterministic fallback. The provider remains a mock. |
| 4. Review and audit | Added routing, a human-review workflow, reasoned decisions, corrections as new versions, the review gate, and a tamper-evident audit chain. |
| 5. Evaluation and robustness | Added per-rule/category metrics, malformed-input handling, fuzz and mutation tests, and public-split evaluation. |
| 6. UI/UX refinement and local PoC | Refined the offline review interface and added an optional local server for saving decisions and corrections without a terminal. |

Phase planning, decisions, and implementation evidence are recorded in
[docs/PHASE2_WORKLOG.md](./PHASE2_WORKLOG.md),
[docs/READINESS.md](./READINESS.md), and
[docs/DEMO_WALKTHROUGH.md](./DEMO_WALKTHROUGH.md).

## 8. Testing results

The repository's readiness report records the following regression results
for Python 3.10.21 and 3.12.14:

- `python src/validate_pack.py`: PASS.
- `python -m unittest discover -s tests` with `REQUIRE_E2E=1`: 606 tests OK
  on each version, including browser end-to-end tests.
- Public synthetic splits: 400 development, 150 validation, and 50 stress
  claims. Reported status accuracy and issue F1 are 1.000 on these splits;
  false FAIL pairs are zero.
- The audit tamper demonstration reports 8 of 8 cases as documented,
  including the documented limit when both log and local anchor are rewritten.
- UI checks cover keyboard use, responsive layout, contrast, offline behavior,
  local-server decision saving, and correction/recheck flows.

These are repository-reported results, not an independent evaluation. The
public expected results are derived from the supplied reference engine; the
validation split has already been used as feedback. No claim is made about
real-world clinical or payer performance. See
[docs/EVALUATION_REPORT.md](./EVALUATION_REPORT.md) for definitions, detailed
results, latency, baseline comparison, and limitations.

## 9. Future improvements

1. Conduct an independent review with the mentor-held test set and publish
   results separately from public reference-label agreement.
2. Validate real-world FHIR requirements with appropriate profiles and
   interoperability tests before claiming broad FHIR support.
3. If a live language model is approved, implement a provider behind the
   existing provider interface; test privacy, latency, cost, failure behavior,
   clinical-advice rejection, and explanation quality before use.
4. For deployment beyond one machine, replace the local demonstration server
   with a production API, authenticated identities, secure deployment,
   database-backed concurrency controls, and operational monitoring.
5. Store audit events append-only and anchor the chain head independently;
   add trusted timestamps, recovery procedures, and a second-reviewer process
   where policy requires it.
6. Evaluate usability with reviewers, keyboard-only users, screen readers,
   mobile devices, and browsers beyond the current headless-Chrome coverage.
7. Consider OCR/RAG for attachments only after establishing consent,
   document provenance, access controls, extraction accuracy checks, and
   strict separation between retrieved content and validation decisions.
8. Use reviewer feedback to propose rulebook changes for human approval;
   do not automatically change payer rules from overrides.
9. Add deployment packaging (for example Docker) only when a defined hosting
   and operational need exists.

## 10. References and submission checklist

- [Source repository](https://github.com/tammam-bt/ClaimGuardAI_MedNexus)
- [Architecture and data flow](./ARCHITECTURE.md)
- [Interface guide](./INTERFACE.md)
- [Design system](./DESIGN_SYSTEM.md)
- [Evaluation report](./EVALUATION_REPORT.md)
- [Privacy and security note](./PRIVACY_SECURITY.md)
- [Readiness and regression evidence](./READINESS.md)
- [Demo walkthrough](./DEMO_WALKTHROUGH.md)

Before submission, confirm the contribution table with the team, capture
current UI screenshots from the final revision for the presentation, verify
that the reported repository revision matches the submitted source, and rerun
the documented validation/test commands in the submission environment.
