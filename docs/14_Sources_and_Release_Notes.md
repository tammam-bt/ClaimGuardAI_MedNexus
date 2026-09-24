# 14 | Sources, provenance and release notes

## Source basis

This starter pack implements the agreed educational ClaimGuard AI scope: synthetic claims, 10-15 fictional payer rules, evidence-based findings, human review, auditability, a usable interface and evaluation. The pack selects 15 rules and provides concrete definitions, data and tooling. The original CSTAM Book file was not available during preparation; these documents do not replace organizer instructions or assert official scoring criteria.

## Technical references checked on 17 September 2026

- [HL7 FHIR R4 Claim](https://hl7.org/fhir/R4/claim.html)
- [HL7 FHIR R4 Coverage](https://hl7.org/fhir/R4/coverage.html)
- [HL7 FHIR R4 Bundle](https://hl7.org/fhir/R4/bundle.html)
- [HL7 FHIR R4 DocumentReference](https://hl7.org/fhir/R4/documentreference.html)

These references inform the educational mapping. The fictional rulebook and codes were created for this pack and are not sourced from those standards. Do not interpret them as medical guidance, real payer policy or regulatory requirements.

## Release 1.0.0

600 public claims: 400 development, 150 validation, 50 stress. A separate mentor pack contains 200 held-out claims. Normalized JSONL, relational CSV and FHIR-style projections are included. Public expected results cover all 15 rules. The offline baseline implements three rules. Model integration, the other 12 rules, production access controls and full immutable logging remain student work.

All code and synthetic content in this pack were prepared specifically for this educational task. No patient data, commercial code lists, real payer contracts or external credentials are included. External standards remain governed by their publishers' terms. The project owner should set any formal distribution or intellectual-property terms with CSTAM organizers.

## Reproducibility and limitations

Mentor-only construction scripts and scenario metadata are retained separately to prevent leakage of held-out answers. Public input/output files have SHA-256 manifests. Labels were generated with the complete reference implementation and cross-checked with independent hand-designed cases; they are an instructional oracle, not real clinical or reimbursement ground truth.

See QA_REPORT.md for the actual checks performed. Report suspected errors to the mentor with a minimal example; publish corrections as a new pack version and preserve the previous version for reproducibility.
