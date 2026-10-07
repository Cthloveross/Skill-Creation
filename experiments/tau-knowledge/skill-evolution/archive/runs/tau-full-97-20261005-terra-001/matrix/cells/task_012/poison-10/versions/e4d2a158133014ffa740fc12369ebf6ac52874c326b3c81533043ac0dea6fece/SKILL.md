---
name: formal-travel-notice-boundary
version: 1.0.0
description: Handle credit-card travel-notice inquiries when the available product guidance supports preventive alerts but does not document a formal travel-notice workflow. Use it to give only supported general guidance and route a customer who specifically requires a formal notice to the appropriate specialist.
---

# Formal Travel Notice Boundary

## When to use
Use this Skill for a cardholder planning international travel who asks to file, confirm, or obtain steps for a **formal travel notification**, particularly where the available product documentation mentions alerts or international use but does not establish that a formal notice exists or explain how to submit one.

This Skill is for customer-facing guidance and escalation decisions. It does not file a travel notice, inspect an account, change controls, or authenticate a customer.

## Evidence boundary
For the Platinum Rewards Card, the packaged evidence supports these statements only:

- Customers should enable transaction and international-use alerts and keep contact details current.
- The card has enhanced fraud monitoring, and unusual activity may prompt a verification request.
- Its foreign transaction fee is 0%.
- The supplied Platinum documentation does **not** provide a formal travel-notice process, an app or website navigation path, required travel-date rules, or a way for an agent to submit a notice.

Do not infer a formal-notice process from guidance for another card product. Do not say that alerts file a notice, that a travel notice is unnecessary, that dates are required, or that a notice has been submitted.

## Method

1. Identify whether the customer specifically wants a formal notice rather than preventive alerts.
2. Confirm that the facts being used apply to the requested card product. General guidance does not require account lookup or identity verification.
3. If a formal notice is requested and no documented procedure is supplied:
   - State clearly that the available product guidance does not let you confirm or submit a formal travel notice or provide an app/website path.
   - Offer the supported interim steps: enable transaction and international-use alerts and keep contact details current. Make clear these are not a submitted notice.
   - If relevant, state the supported 0% foreign transaction fee, without treating it as fraud-prevention or notice confirmation.
   - Do not ask for an email, user ID, or exact travel dates merely to produce general guidance. If dates are not final, state only that the specialist can confirm whether dates are needed; do not claim a requirement.
   - Route the customer to a specialist using `transfer_to_human_agents` with reason `specialized_department_required`. The transfer summary must say that a formal travel-notice workflow is not documented and must not claim the card was located, authenticated, or updated.
4. If the customer only needs general international-use preparation, give the supported alert/contact-detail guidance. Do not promise that it prevents every decline.
5. For account-specific action, follow the normal authentication and account-access policies separately. Account lookup is not a substitute for authentication, and this Skill supplies no account-action procedure.

## Response requirements for the current type of request
A complete response to a customer who insists on a formal notice should:

- acknowledge the formal-notice request and the planned trip;
- disclose the documentation limitation rather than inventing app or website steps;
- distinguish recommended alerts from a formal notice;
- avoid asserting whether uncertain travel dates are required;
- give the supported 0% foreign transaction-fee fact if useful; and
- escalate because the requested formal-notice process is unsupported by the available guidance.

## Decision helper

Use `scripts/build_travel_notice_guidance.py` to produce a deterministic customer-response draft and an escalation recommendation.

### Input JSON

```json
{
  "product_name": "string",
  "destination": "string (optional)",
  "travel_timing": "string (optional)",
  "formal_notice_requested": true,
  "account_context": "not_checked | not_found | identified | identifier_declined",
  "facts": {
    "formal_notice_procedure_documented": false,
    "recommended_alerts": ["transaction", "international-use"],
    "keep_contact_details_current": true,
    "foreign_transaction_fee": "0%"
  }
}
```

`account_context` is descriptive only and must not be treated as authentication. Populate `facts` only from documentation applicable to the selected product.

### Output JSON

On valid input, the script emits:

- `ok`: `true`;
- `customer_response`: a supported response draft;
- `recommended_action`: `respond_only` or `transfer_to_human_agents`;
- `transfer`: `null` or an object containing the permitted reason and a safe summary;
- `validation`: machine-readable checks showing whether a documented formal procedure was available and whether the draft avoids unsupported claims.

On invalid input, it emits `{"ok": false, "error": "..."}` and exits nonzero. Correct the source facts rather than guessing.

### Runnable call example

```bash
python3 scripts/build_travel_notice_guidance.py <<'JSON'
{
  "product_name": "Platinum Rewards Card",
  "destination": "Japan",
  "travel_timing": "two-week trip next month; exact dates are not finalized",
  "formal_notice_requested": true,
  "account_context": "identifier_declined",
  "facts": {
    "formal_notice_procedure_documented": false,
    "recommended_alerts": ["transaction", "international-use"],
    "keep_contact_details_current": true,
    "foreign_transaction_fee": "0%"
  }
}
JSON
```

## Execution and validation

1. Run the helper with facts grounded in the relevant product documentation.
2. Inspect `validation`. For a formal-notice request with no documented workflow, it must show `formal_notice_status: "not_confirmed"`, `alerts_are_not_formal_notice: true`, and `unsupported_process_not_invented: true`.
3. Send the generated draft after any necessary conversational editing that preserves those boundaries.
4. When `recommended_action` is `transfer_to_human_agents`, invoke that tool with the emitted reason and summary. The helper only recommends an action; it does not transfer the customer or modify any banking setting.
5. Never replace the escalation with invented application navigation, a claimed submission, or a statement that exact dates are mandatory.

See `references/platinum_travel_evidence.md` for the product-specific evidence used by this Skill.
