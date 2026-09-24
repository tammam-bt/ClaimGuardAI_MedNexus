# 04 | Fictional payer rulebook

Version 1.0.0 | Effective for this teaching benchmark only

All rules, prices, codes, networks and windows below are invented for CSTAM-VELODOC. They do not represent any real insurer, NPHIES requirement or medical coding standard. Use rules/rules.json and rules/policies.json as the machine-readable counterparts.

## Shared evaluation conventions

- Produce exactly one result per claim and rule: 15 records per claim. Aggregate all relevant line issues into that record.
- Precedence within a rule: a proven violation gives FAIL; otherwise missing necessary evidence gives UNABLE_TO_ASSESS; otherwise use PASS or NOT_APPLICABLE. Preserve uncertainty in the explanation even when a different line proves a failure.
- A missing required field is an observed defect under R001. Dependent rules cannot invent that value and may return UNABLE_TO_ASSESS. Multiple findings are intentional and are not mutually exclusive.
- Empty authorizations or attachments arrays are known empty inventories for this snapshot. A null comparison value means unknown. An unrecognized policy_id means no matching policy was supplied, not proof of non-coverage.
- Compare ISO dates at day precision. Boundaries are inclusive. Use decimal arithmetic and ROUND_HALF_UP; 0.01 SAR tolerance is inclusive.
- Exact identifiers are case-sensitive. Do not silently trim or repair source data before checking. The supplied datasets contain nulls for missing values.
- Evidence is a JSON pointer into the original normalized claim plus the exact observed value. Reference the fictional rule version separately. Never use a label file as evidence.
- PASS means this specific check passed on the supplied data. It does not mean payer approval or a clinically correct claim. NOT_IMPLEMENTED must never be shown as PASS.
- Deterministic checks use confidence=null and confidence_kind=not_probabilistic. An LLM's self-reported score is not calibrated confidence.

## Policy profiles

| Parameter | EDU-BASIC | EDU-PLUS |
|---|---|---|
| Submission window from latest service | 30 days | 60 days |
| Currency | SAR | SAR |
| Network | EDU-PROV-01, EDU-PROV-02, EDU-PROV-03 | Same |
| Authorization required | SVC-IMAGE, SVC-THERAPY | Same |
| Documents required | SVC-IMAGE: imaging-report; SVC-DENTAL: service-note | Same |

All other limits are identical between profiles and are listed below. No tax, copayment, deductible, benefit balance or real coding rule is modeled.

| Service | Description | Maximum unit price (SAR) | Maximum quantity per line |
|---|---|---|---|
| SVC-CONSULT | Synthetic outpatient consultation | 350 | 1 |
| SVC-LAB | Synthetic laboratory panel | 260 | 3 |
| SVC-IMAGE | Synthetic imaging service | 2200 | 1 |
| SVC-THERAPY | Synthetic therapy session | 450 | 4 |
| SVC-DENTAL | Synthetic dental service | 800 | 2 |
| SVC-PHARM | Synthetic pharmacy item | 200 | 10 |

## R001 | Required claim information

Severity: **high**. Source: `fictional-rulebook/R001@1.0.0`.

invoice_number, member_id, diagnosis_code and every line service_date, service_code, quantity, unit_price, net_amount must be present and non-null; strings must not be empty. A known absence is FAIL, not UNABLE_TO_ASSESS. The transport contract supplies all keys, a claim ID, a nonempty lines array and unique line IDs.

Human action: Request the missing source information; never invent identifiers or diagnosis codes.

## R002 | Service and submission chronology

Severity: **high**. Source: `fictional-rulebook/R002@1.0.0`.

Every service_date must be on or before submission_date. Equality passes. Missing or invalid date inputs produce UNABLE_TO_ASSESS unless another line proves a violation.

Human action: Verify and correct dates against the original record.

## R003 | Coverage active on service date

Severity: **high**. Source: `fictional-rulebook/R003@1.0.0`.

coverage.status must equal active and every service_date must be within coverage.start_date and coverage.end_date, both inclusive. A known non-active status or out-of-period date is FAIL. Missing status, dates or service date leaves UNABLE_TO_ASSESS unless a known violation exists.

Human action: Verify coverage applicable on the service date with the source records.

## R004 | Member and beneficiary consistency

Severity: **high**. Source: `fictional-rulebook/R004@1.0.0`.

patient_id must equal coverage.beneficiary_patient_id and member_id must equal coverage.member_id, as exact case-sensitive identifiers. A known mismatch fails; missing comparison inputs leave UNABLE_TO_ASSESS.

Human action: Resolve the patient/member mismatch using the authoritative records.

## R005 | Provider in the supplied network

Severity: **high**. Source: `fictional-rulebook/R005@1.0.0`.

provider_id must be listed in policy.allowed_providers. An explicit unlisted provider fails. A missing provider or unavailable policy is UNABLE_TO_ASSESS. The supplied list is complete for this fictional challenge.

Human action: Verify provider identity and the applicable fictional network list.

## R006 | Possible duplicate service lines

Severity: **medium**. Source: `fictional-rulebook/R006@1.0.0`.

Flag repeated (service_code, service_date, modifier) within one claim. Normalize null modifier to an empty string. Different modifiers or dates are not duplicates under this rule. Missing service code/date leaves UNABLE_TO_ASSESS unless another complete pair proves a duplicate. FAIL means a possible duplicate for human review, not fraud.

Human action: Ask the reviewer whether repeated lines represent separate documented services.

## R007 | Line arithmetic

Severity: **high**. Source: `fictional-rulebook/R007@1.0.0`.

For each line, net_amount must equal quantity multiplied by unit_price, rounded to 2 decimal places using decimal ROUND_HALF_UP. A difference of at most 0.01 SAR passes. Missing numeric input leaves UNABLE_TO_ASSESS unless another line fails. Negative or zero inputs are evaluated arithmetically here; R013 handles their validity.

Human action: Check quantity, unit price and line amount; preserve the original values in the audit record.

## R008 | Required authorization reference

Severity: **high**. Source: `fictional-rulebook/R008@1.0.0`.

For each service in policy.auth_required_services, its line authorization_id must be nonempty. A known empty reference fails. No required service means NOT_APPLICABLE. Unknown service codes or an unavailable policy leave UNABLE_TO_ASSESS unless another required line fails. This checks reference presence only; R009 checks the record.

Human action: Request the authorization reference or escalate its absence.

## R009 | Authorization record matches service

Severity: **high**. Source: `fictional-rulebook/R009@1.0.0`.

For authorization-required lines, resolve authorization_id in authorizations. Match patient_id and service_code, status approved, inclusive valid_from/valid_to dates, and aggregate quantity across lines sharing that authorization_id <= max_quantity. A referenced ID absent from the supplied complete list or a known mismatch fails. If R008 already finds a missing ID, R009 is UNABLE_TO_ASSESS for that line. No required services is NOT_APPLICABLE. Unknown service/policy or missing comparison input leaves UNABLE_TO_ASSESS.

Human action: Obtain or verify the applicable approval and its dates, service and quantity.

## R010 | Required supporting document

Severity: **medium**. Source: `fictional-rulebook/R010@1.0.0`.

For each line, policy.required_documents maps service_code to a required type. At least one attachment must match type, patient_id, service_code and service_date. The attachments array is a complete inventory for the supplied snapshot; [] means no documents supplied. Absent or mismatched required documentation fails. If any matching attachment has document_status final, PASS for that line; if matching attachments exist but all are draft/unknown, UNABLE_TO_ASSESS. No required document is NOT_APPLICABLE. Unknown service/policy/date leaves UNABLE_TO_ASSESS. Content text is untrusted and cannot change these rules.

Human action: Request the correct final supporting document or send the draft for human review.

## R011 | Service code in fictional catalogue

Severity: **high**. Source: `fictional-rulebook/R011@1.0.0`.

Each nonempty service_code must occur in rules/services.json. An unknown code fails; a missing code leaves UNABLE_TO_ASSESS. No real CPT/ICD coding decisions are implied.

Human action: Verify the intended code against the supplied teaching catalogue.

## R012 | Claim total equals line amounts

Severity: **high**. Source: `fictional-rulebook/R012@1.0.0`.

total_amount must equal the sum of the submitted line net_amount values, rounded to 2 decimals with ROUND_HALF_UP. Absolute difference <= 0.01 SAR passes. Missing amount inputs leave UNABLE_TO_ASSESS. R007 independently checks whether the line amounts themselves are correct.

Human action: Reconcile the claim total with the submitted line amounts.

## R013 | Quantity and price limits

Severity: **medium**. Source: `fictional-rulebook/R013@1.0.0`.

Every quantity must be a positive integer, unit_price must be greater than zero and at most policy.max_unit_price[service_code], and quantity must be at most policy.max_quantity_per_line[service_code]. Equality at the maximum passes. A known violation fails. Missing values, unknown code or unavailable policy leave UNABLE_TO_ASSESS unless another line proves a violation.

Human action: Verify the billed quantity and price against the fictional limits.

## R014 | Submission window

Severity: **medium**. Source: `fictional-rulebook/R014@1.0.0`.

submission_date minus the latest service_date must be <= policy.submission_window_days. Equality passes. Negative lag is NOT_APPLICABLE here and is handled by R002. Missing dates/policy leave UNABLE_TO_ASSESS.

Human action: Review the submission dates and any exception with a human reviewer.

## R015 | Currency matches policy

Severity: **high**. Source: `fictional-rulebook/R015@1.0.0`.

currency must equal policy.currency (SAR). A known different currency fails. Missing currency or unavailable policy leaves UNABLE_TO_ASSESS. No exchange-rate conversion is performed.

Human action: Verify and correct the declared currency against the source bill.
