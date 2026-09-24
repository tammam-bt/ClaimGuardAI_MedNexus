# 13 | Worked examples

These ten examples reuse public dataset records; they do not increase the dataset count. Each complete input and all 15 expected outputs appear in examples/worked_cases.json. Compare your manual prediction before inspecting the answer. For each case, locate the evidence, explain the rule and state the next human action. Preserve the original record.

## Clean claim

Claim: `CG-27BFD8541DEB`.

All applicable checks pass on the supplied evidence. This is not a payer approval.


## Coverage date issue

Claim: `CG-1CB04117F0CB`.

- **R003: FAIL** - service outside coverage period Evidence: `/coverage/status`, `/coverage/start_date`, `/coverage/end_date`, `/lines/0/service_date`.


## Missing authorization

Claim: `CG-B39790AC3604`.

- **R008: FAIL** - Required authorization ID missing Evidence: `/lines/0/service_code`, `/lines/0/authorization_id`.
- **R009: UNABLE_TO_ASSESS** - Cannot inspect authorization without an ID Evidence: `/lines/0/service_code`, `/lines/0/authorization_id`.


## Missing document

Claim: `CG-610536BBB38B`.

- **R010: FAIL** - Matching required document absent Evidence: `/attachments`, `/lines/0/service_code`, `/lines/0/service_date`.


## Possible duplicate

Claim: `CG-63A3C6B299C0`.

- **R003: FAIL** - service outside coverage period Evidence: `/coverage/status`, `/coverage/start_date`, `/coverage/end_date`, `/lines/0/service_date`.
- **R005: FAIL** - Provider absent from supplied network Evidence: `/provider_id`, `/policy_id`.
- **R006: FAIL** - Possible duplicate lines require review. Evidence: `/lines/0/service_code`, `/lines/0/service_date`, `/lines/0/modifier`, `/lines/1/service_code`.
- **R007: FAIL** - Line amount differs from quantity times price Evidence: `/lines/0/quantity`, `/lines/0/unit_price`, `/lines/0/net_amount`, `/lines/1/quantity`.


## Unknown coverage boundary

Claim: `CG-91E018F1841E`.

- **R003: UNABLE_TO_ASSESS** - coverage period Evidence: `/coverage/status`, `/coverage/start_date`, `/coverage/end_date`, `/lines/0/service_date`.


## Draft document

Claim: `CG-F5F2411AC3AD`.

- **R010: UNABLE_TO_ASSESS** - Only draft or uncertain matching documentation Evidence: `/attachments`, `/lines/0/service_code`, `/lines/0/service_date`.


## Untrusted document instruction

Claim: `CG-116C84D4774D`.

- **R012: FAIL** - Claim total differs from submitted line amounts Evidence: `/total_amount`, `/lines/0/net_amount`.


## Legitimate repeated service with modifier

Claim: `CG-64AD4A3E3A00`.

All applicable checks pass on the supplied evidence. This is not a payer approval.


## Unknown policy

Claim: `CG-128A977172C2`.

- **R005: UNABLE_TO_ASSESS** - No policy is supplied for this policy_id. Evidence: `/policy_id`.
- **R008: UNABLE_TO_ASSESS** - No policy is supplied for this policy_id. Evidence: `/policy_id`.
- **R009: UNABLE_TO_ASSESS** - No policy is supplied for this policy_id. Evidence: `/policy_id`.
- **R010: UNABLE_TO_ASSESS** - No policy is supplied for this policy_id. Evidence: `/policy_id`.
- **R013: UNABLE_TO_ASSESS** - No policy is supplied for this policy_id. Evidence: `/policy_id`.
- **R014: UNABLE_TO_ASSESS** - No policy is supplied for this policy_id. Evidence: `/policy_id`.
- **R015: UNABLE_TO_ASSESS** - No policy is supplied for this policy_id. Evidence: `/policy_id`.

