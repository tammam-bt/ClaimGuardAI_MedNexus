# 10 | Privacy, security and audit design

## Data boundaries

All supplied patients, identifiers, services, policies and documents are synthetic. Do not add real records to the challenge repository. Do not treat the lack of personal information in this dataset as a completed compliance assessment for a future healthcare product.

Keep claim text separate from instructions. Allow the AI helper only read-only access to supplied claim evidence and rules. No shell execution, external browsing, message sending or payer submission is required. Do not put API keys in prompts, code, screenshots or audit logs.

## Failure behaviour

Malformed input becomes an explicit ingestion error. Unknown policy or missing necessary evidence becomes unable to assess. A timeout, unavailable model or invalid generated JSON falls back to deterministic findings and logs the error. Failed checks remain visible. Tool outputs and documents cannot grant new permissions.

## Human review

Keep automated findings separate from review decisions. Require an actor, timestamp and reason. A dismissal must be explainable and preserve the original issue. A corrected claim creates a new input version and a rerun; clicking a button alone must not change an error into a pass. The supplied static interface uses self-declared reviewer names and does not authenticate users.

## Audit prototype versus immutable logging

The supplied audit.py chains event hashes and detects an edited entry when later hashes have not also been rewritten. It is a single-process teaching prototype. It does not prevent log deletion, rollback, replacement, concurrent corruption or unauthorized access. It also does not automatically capture every model call or rule run; teams must add run-level events.

For the challenge's immutable-audit design requirement, document how you would combine authenticated actors, least-privilege append-only writes, retention-locked storage, independent trusted timestamps/head hashes, backups and controlled exports. Demonstrate prototype tamper detection and state which of these controls you actually implemented. Do not label a mutable local JSON file immutable.

## Security exercise acceptance

Attachment instructions cannot change a rule outcome. The model receives no secrets. The UI escapes source text. Invalid model output does not enter the authoritative result set. A reviewer can inspect the source, and all unresolved checks remain visible. Record these tests and limitations in the final report.
