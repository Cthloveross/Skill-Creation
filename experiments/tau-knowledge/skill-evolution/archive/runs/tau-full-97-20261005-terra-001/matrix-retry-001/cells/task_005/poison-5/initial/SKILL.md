---
name: select-human-transfer-reason
version: 1.0.0
description: Selects the highest-priority supported reason code and prepares a useful transfer summary when a banking customer must be transferred to a human agent. Use especially for identity/account-record mismatches, unresolved lookup failures, and customer requests for a human.
---

# Human-transfer reason selection

Use this Skill immediately before calling `transfer_to_human_agents`. It turns observed, already-established facts into one permitted reason code and a concise handoff summary. It does not perform a transfer itself.

## Required decision method

1. Establish the operational facts from the conversation and tool results. Do not infer that an account exists, that a customer owns an account, or that identity was verified merely because one contact field matched a record.
2. Mark every reason whose full condition is actually satisfied. If more than one applies, select a reason from the highest applicable tier:
   - **Tier 1:** specific operational reasons.
   - **Tier 2:** knowledge/capability gaps.
   - **Tier 3:** customer-disposition reasons.
   - **Tier 4:** `other` only when no other reason applies.
3. For an account or identity mismatch requiring specialist handling, select **`account_ownership_dispute`**. This includes an identity-verification failure: for example, the requested card/account cannot be reconciled with the located customer record and the provided identifiers do not resolve the discrepancy. This Tier 1 reason overrides a bare request for a human in Tier 3.
4. Call `transfer_to_human_agents` with the selected `reason` and the generated summary. The summary should state the requested service, relevant lookup/verification attempts and their outcomes, the unresolved blocker, and that transfer was requested. Do not include unnecessary sensitive data.

Do not substitute a lower-tier generic code merely because the customer explicitly requested transfer. Conversely, do not mark a specialized reason based only on a customer's preference for a person.

## Reason-condition checklist

Only mark a code when its complete condition holds:

- `fraud_or_security_concern`: fraud, identity theft, unauthorized activity, or another security concern needs specialist handling.
- `account_closure_request`: the customer explicitly asks to close the account.
- `deceased_account_holder`: deceased-holder or estate handling is needed.
- `legal_or_regulatory_matter`: subpoena, court order, garnishment, or compliance inquiry.
- `account_ownership_dispute`: ownership dispute, joint-account issue, or identity-verification failure requiring a specialist.
- `complex_billing_dispute`: specialist billing review, such as recurring charges, statement errors, or fee reversals.
- `abusive_customer_behavior`: abusive, threatening, or inappropriate customer behavior.
- `third_party_inquiry`: attorney, power of attorney, or other authorized representative requires verification.
- `technical_system_error`: a system error/outage prevents completion.
- `customer_demands_after_unavailable_offer_refusal`: a nonexistent/unavailable offer was explained, the customer persisted multiple times, and now demands a human.
- `unconfirmed_external_communication`: a claimed specific letter/email/flyer promotion was searched for but cannot be verified.
- `kb_search_unsuccessful_customer_requests_transfer`: requested instructions/information were searched for, not found, explained, then the customer requested transfer.
- `specialized_department_required`: the request belongs to a department outside the available scope/tools.
- `accessibility_or_special_needs`: a required accommodation or special need requires human intervention.
- `customer_frustrated_demands_human`: general frustration plus demand for human, with no higher reason.
- `supervisor_request_service_complaint`: dissatisfaction with service quality and a request for supervisor.
- `customer_requests_human_no_specific_reason`: a calm/preference-only request for human with no other reason.
- `request_completed_customer_wants_human_followup`: the request was completed, but the customer wants a human for follow-up/confirmation.
- `other`: none of the above applies; provide a detailed summary.

## Deterministic helper

Run `scripts/select_transfer_reason.py` with JSON on standard input. The script uses only the listed facts and does not access banking systems.

### Input schema

```json
{
  "applicable_reasons": ["optional permitted reason codes whose complete conditions hold"],
  "facts": {
    "identity_verification_failure": false,
    "customer_requested_transfer": false,
    "customer_frustrated": false,
    "supervisor_service_complaint": false,
    "request_completed_followup": false,
    "fraud_or_security_concern": false
  },
  "issue": "short description of the requested service",
  "attempts": ["short factual lookup or verification outcomes"],
  "blocker": "why the request cannot proceed",
  "summary": "optional finalized handoff summary"
}
```

`applicable_reasons` may contain any checklist code and is appropriate when the executor has evaluated a compound condition. The boolean aliases in `facts` cover common cases; any checklist code can also be supplied as a boolean fact. `identity_verification_failure` maps to `account_ownership_dispute`. `customer_requested_transfer` maps only to the generic Tier 3 code and therefore cannot override a higher-tier condition.

The script emits either:

```json
{"ok": true, "reason": "...", "summary": "...", "tier": 1}
```

or a JSON error object for malformed input. An explicit nonempty `summary` is retained; otherwise the script composes one from `issue`, `attempts`, and `blocker`. Review the result for accuracy, then pass its `reason` and `summary` unchanged or improve the summary with established facts before the transfer tool call.

### Runnable call example

```sh
printf '%s' '{"facts":{"identity_verification_failure":true,"customer_requested_transfer":true},"issue":"Requested account service","attempts":["Record lookup did not reconcile the requested account with supplied identity details"],"blocker":"Identity/account ownership could not be verified"}' | python3 scripts/select_transfer_reason.py
```

Expected validation properties: `reason` is one of the transfer tool enum values, `tier` is 1 through 4, and a successful result always has a nonempty summary. The executor must still use the normal `transfer_to_human_agents` banking tool; running the helper is only a recommendation/validation step.
