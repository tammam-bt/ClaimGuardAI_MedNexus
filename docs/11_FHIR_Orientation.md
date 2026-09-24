# 11 | FHIR R4 mapping guide

The authoritative evaluation input is the normalized envelope. Each claim also has an educational FHIR R4-style collection Bundle in fhir_bundles.jsonl. These files support an integration exercise; they are not a complete national implementation guide or live payer request.

A Claim describes services and the associated reimbursement request. Read the official [HL7 R4 Claim specification](https://hl7.org/fhir/R4/claim.html). In this pack, claim_id maps to Claim.id, service code/date/quantity map to Claim.item, and submitted total maps to Claim.total. Claim.insurance points to Coverage; supportingInfo points to attached DocumentReference records.

Coverage supplies the beneficiary, payer and date period. The mapping uses Coverage.beneficiary, payor and period. These fields are described in the [HL7 R4 Coverage specification](https://hl7.org/fhir/R4/coverage.html). Membership is projected into subscriberId for this simplified teaching example; a real enrollment design needs its own modeling decisions.

The Bundle groups resources without representing a submission transaction. Each entry has a fullUrl used by resource references. See the [HL7 R4 Bundle specification](https://hl7.org/fhir/R4/bundle.html). Local example URLs use claimguard.example and are identifiers, not live endpoints.

Supporting text is included as base64 text/plain in DocumentReference.content. Patient and document metadata remain explicit. See [HL7 R4 DocumentReference](https://hl7.org/fhir/R4/documentreference.html). Decode the text for viewing; never execute it as instructions.

## Mapping coverage

| Normalized content | Projection |
|---|---|
| patient_id and member_id | Patient.id and identifier. |
| provider_id and payer_id | Organization resources and references. |
| invoice_number, diagnosis_code | Claim.identifier and diagnosisCodeableConcept with invented local codes. |
| line service/date/quantity/amount | Claim.item fields; sequence follows array order. |
| coverage dates/status | Coverage period/status. |
| authorization_id | Claim.insurance.preAuthRef plus a teaching line extension. |
| attachments | DocumentReference and Claim.supportingInfo. |

## Deliberate limitations

The line-authorization extension URL is a teaching convention without a published StructureDefinition. Full authorization details, policy limits, notes and some source metadata remain in the normalized sidecar; FHIR files alone are insufficient to reproduce all 15 checks. No reverse adapter is included. Keep normalized JSON as the benchmark input while implementing a selected mapping exercise.

Some business-inconsistent records intentionally reference a different document patient. Resource-shape checks are distinct from reference resolution and payer-rule checks. Do not assume that a structurally plausible FHIR resource is a valid claim.

QA checks mapping basics, not full HL7 conformance or national profiles. A production integration requires the relevant HL7, terminology, extension and partner-profile validation.
