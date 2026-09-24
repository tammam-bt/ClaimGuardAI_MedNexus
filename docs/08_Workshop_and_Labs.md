# 08 | Kickoff workshop and practical labs

Suggested duration: 5.5 hours plus breaks. Existing Python and AI knowledge is assumed. The objective is to help students understand the domain, contracts and validation logic before adding a model.

| Session | Minutes | Practical outcome |
|---|---|---|
| Claim lifecycle and boundaries | 45 | Explain a claim and distinguish pre-validation from payer approval. |
| Data and FHIR orientation | 60 | Locate fields, join CSVs and trace a FHIR resource reference. |
| Rules with bounded AI | 75 | Run baseline; implement one rule; ground one explanation. |
| Trust and evaluation | 60 | Compare statuses, test false alarms and inspect an injection case. |
| Team exercise | 90 | Show findings, evidence and a recorded human decision. |

## Before the workshop: readiness check

Read JSONL, count claims, print a service date and report a missing invoice_number. Explain null versus an empty array. Use a short Python/JSON refresher if needed.

## Lab 1: understand before coding

Open the worked examples. Predict the outcome for a clean claim, a clear issue and an unknown case. Trace the fields before reading the answers.

## Lab 2: implement R012

Sum the submitted line net_amount values with decimal arithmetic and compare against total_amount. Test exact equality, a difference of 0.01, a difference of 0.02, and a missing amount. Explain why R007 and R012 answer different questions. Return evidence pointers and all required output fields.

## Lab 3: authorization and dependencies

Implement R008, then design R009. Compare an absent authorization ID, a referenced but absent record, a denied authorization, an expired approval and a shared authorization with excess total quantity. Avoid double-counting the same authorization allocation.

## Lab 4: explain without inventing

Start with the mock, then add your model adapter. Supply the rule and validated finding. Require JSON and reject invented citations. Test untrusted instructions and record unsupported facts.

## Lab 5: review and audit

In the review page, record one confirmed issue, one dismissal with reason and one information request. Export decisions and append them to the audit log. Verify the chain, then edit a copied log entry and demonstrate detection. Discuss why hashing alone cannot stop a person replacing an entire log.

## End-of-day exit criteria

Each team reproduces a run, explains three cases, implements one new rule and shows a reviewer action. Agree the next three tasks, owners and one mentor question.
