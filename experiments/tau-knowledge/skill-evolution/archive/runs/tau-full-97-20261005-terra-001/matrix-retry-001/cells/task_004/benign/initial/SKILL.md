---
name: human-transfer-reason-selector
description: Select and document the highest-priority supported reason code for transferring a banking customer to a human agent, especially when an account ownership or identity-verification mismatch prevents safe servicing.
---

# Human Transfer Reason Selector

Use this Skill when a customer must be transferred to a human agent and the executor must supply the exact `reason` enum and a useful `summary` to `transfer_to_human_agents`.

## Inputs at runtime

Review the live conversation, completed tool observations, and any applicable knowledge-base results. Establish:

- whether a transfer is appropriate or explicitly requested;
- the operational trigger for transfer;
- what was attempted and what prevented completion; and
- every reason-code condition that is fully supported by those facts.

Do not treat an unverified claim as a fact. Do not put account identifiers, full addresses, dates of birth, phone numbers, or other unnecessary sensitive values in the transfer summary.

## Reason-selection method

1. **Check Tier 1 first.** If one Tier 1 condition applies, it takes precedence over every lower-tier condition.
   - Use `account_ownership_dispute` when an ownership dispute exists **or identity verification has failed/mismatched in a way that requires a specialist**. This includes a customer disputing account-identifying information returned for a same-name record when ownership cannot be safely established.
   - Select the other Tier 1 reason only when its exact documented operational scenario is supported (fraud/security, closure, deceased holder, legal/regulatory matter, billing dispute, abuse, third party, technical error, or persistent demand after an unavailable-offer refusal).
2. Only when no Tier 1 reason applies, evaluate Tier 2. Its prerequisites matter: for example, an unsuccessful KB-search reason requires an unsuccessful search, disclosure of that limitation, and then a transfer request.
3. Only when neither Tier 1 nor Tier 2 applies, use the best-fitting Tier 3 customer-disposition reason. General frustration is not a substitute for a more specific higher-tier issue.
4. Use `other` only if no listed reason applies. Its summary must explain why the listed reasons do not fit.
5. If more than one reason in the same highest tier seems applicable, determine which documented scenario is the direct cause of this transfer. If the record cannot support that decision, obtain the required clarification or follow the escalation process rather than arbitrarily choosing a code.

The complete supported enum is:

- Tier 1: `fraud_or_security_concern`, `account_closure_request`, `deceased_account_holder`, `legal_or_regulatory_matter`, `account_ownership_dispute`, `complex_billing_dispute`, `abusive_customer_behavior`, `third_party_inquiry`, `technical_system_error`, `customer_demands_after_unavailable_offer_refusal`
- Tier 2: `unconfirmed_external_communication`, `kb_search_unsuccessful_customer_requests_transfer`, `specialized_department_required`, `accessibility_or_special_needs`
- Tier 3: `customer_frustrated_demands_human`, `supervisor_request_service_complaint`, `customer_requests_human_no_specific_reason`, `request_completed_customer_wants_human_followup`
- Tier 4: `other`

## Account-change safety

For an account email change, do not perform `change_user_email` until the executor has the exact requested new email and can safely identify the account. The documented verification workflow requires confirmation of two of the four identity fields (date of birth, email, phone number, address), followed by `log_verification` with the current timestamp after successful verification. If account details conflict and identity/ownership cannot be resolved, do not use a guessed record; evaluate the Tier 1 `account_ownership_dispute` transfer reason.

## Build and validate the transfer payload

Use `scripts/select_transfer.py` after you have identified the supported candidate reasons. The script does not infer facts from raw text and does not transfer the customer; it validates the candidates, applies the documented tier ordering, and constructs a concise summary.

### Script input JSON

```json
{
  "transfer_intended": true,
  "applicable_reasons": ["account_ownership_dispute"],
  "issue": "brief non-sensitive description of the requested service",
  "attempted": ["brief non-sensitive action or verification attempt"],
  "blocker": "brief non-sensitive reason servicing could not continue"
}
```

`applicable_reasons` must contain only reasons whose documented conditions have actually been met. Supply only the direct reason when several same-tier labels superficially overlap. `issue`, `attempted`, and `blocker` are used to produce the human-facing handoff summary.

### Script output JSON

On success, the output has `status: "ok"`, `transfer_recommended: true`, a valid `reason`, and `summary`. If transfer is not intended, it returns `transfer_recommended: false`. Invalid, conflicting same-tier, or unsupported candidate input returns `status: "error"`; do not call the transfer tool from that result.

Example invocation by the executor (with live, redacted facts substituted):

```text
run_skill_script(relative_path="scripts/select_transfer.py", input_json={...})
```

Before calling the banking tool, confirm all of the following:

- The selected reason is the sole highest-tier supported candidate.
- The summary states the issue, meaningful attempts, and blocker without unnecessary sensitive data.
- No account-changing tool will be called as part of an unresolved ownership/verification situation.

Then call the normal banking tool exactly once with the generated fields:

```text
transfer_to_human_agents(reason=<output.reason>, summary=<output.summary>)
```

Report that the customer is being connected to a human agent. The script recommendation itself does not perform a transfer or any banking action.
