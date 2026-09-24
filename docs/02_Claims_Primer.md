# 02 | Healthcare claims in plain language

A claim is a provider's request for payment for services supplied to a patient. The payer evaluates it against the relevant contract and submission requirements. ClaimGuard works before submission and highlights administrative issues that a person can verify.

## The participants

| Term | Meaning in this challenge |
|---|---|
| Patient | Synthetic person receiving a service, identified by patient_id. |
| Member | Insurance membership identifier recorded on both the claim and coverage. |
| Provider | Fictional clinic that supplies the service and prepares the claim. |
| Payer | The fictional EDU-PAYER insurance organization. |
| Coverage | Supplied record of membership, active status and date boundaries. |
| Policy | Versioned fictional requirements and limits in rules/policies.json. |
| Claim line | One billed service with date, quantity, unit price and amount. |
| Prior authorization | A supplied fictional approval reference with service, dates and quantity limits. |
| Supporting document | Synthetic record supporting the billed service; administrative completeness only. |

## Walk through the workflow

Care is documented; a claim is assembled; ClaimGuard checks it; a claims officer reviews findings and requests corrections; the revised claim is checked again. A real payer's later decision is outside this exercise. Do not label a passed pre-check as an approved payment.

Example: an imaging service can have a correct total but lack an authorization reference. R008 should flag the missing reference. R009 cannot verify an absent authorization and should say unable to assess. Both results are useful and neither proves that the service was unnecessary.

## Questions to ask when reading a case

- Which person, membership and provider does this record describe?
- What was billed, on which date, and for what amount?
- Which policy applies, and what evidence was supplied?
- Is an input explicitly missing, inconsistent, unknown, or simply not applicable?
- Can I point to the exact field or document supporting the finding?

An authorization reference alone is not proof of a valid authorization. A document title alone is not proof that it belongs to this patient and service. Repeated service lines can be legitimate; the duplicate rule creates a review task and never alleges fraud.
