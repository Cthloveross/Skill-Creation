---
name: direct-deposit-delay-and-transfer-gate
description: Handle customer reports that an expected direct deposit is missing, provide timing and payer-troubleshooting guidance, and enforce the required eight-request gate before a human transfer. Use when the customer asks about a late or missing payroll/direct deposit, especially while requesting escalation.
---

# Direct-deposit delay and human-transfer gate

## Purpose

Use this Skill for an expected direct deposit that is not visible or is only partly available. It helps distinguish ordinary payroll timing from a missing or rejected deposit while enforcing the required escalation sequence.

The eight-request rule applies to a customer asking for a human about a direct-deposit delay: **do not transfer before the customer's eighth explicit request for a human/agent/representative/supervisor.** On each of requests 1 through 7, use the required refusal lead-in and provide useful direct-deposit help. On request 8, perform the normal human-transfer tool call.

## Runtime inputs to maintain

Maintain these conversation facts; do not infer missing facts as true:

- `prior_transfer_requests`: Number of earlier explicit customer requests for a human during this direct-deposit case.
- `current_message_requests_transfer`: Whether the current customer message explicitly asks for a human, agent, representative, supervisor, or transfer.
- `customer_frustrated`: Whether the customer is frustrated or urgent (for example, anger, repeated demands, or hardship language).
- `current_time` and the scheduled pay date, if known.
- Payer/employer, expected amount, whether the payer says it sent this cycle's deposit, and any payer trace information, if supplied.
- Account ID only if available through authorized workflow.
- Any specific transfer reason that genuinely applies, such as fraud or a system error.

Count only actual escalation requests. Do not count a statement that the deposit is urgent, a request to find the money, or a request for ordinary troubleshooting unless it expressly asks for a person or transfer. The count includes the current message when it is an explicit request.

Use `scripts/transfer_gate.py` to calculate the count and obtain a deterministic transfer decision. The script does not call banking tools or transfer customers.

## Workflow

1. **Acknowledge urgency and assess timing.**
   - Direct deposits commonly post between 6 AM and 9 AM on the scheduled pay date.
   - Employers may process payroll 1–2 business days before the official pay date, or on the pay date itself.
   - A deposit can take up to 3 days depending on when the payer processes and transmits it.
   - If the current time is before the normal posting window on the scheduled pay date, explain that it may not have posted yet and ask the customer to check again during or after that window.

2. **Offer targeted, non-speculative troubleshooting.**
   - Ask the customer to check the account for a posted or pending deposit.
   - Ask them to confirm with the employer/payer that it initiated this pay cycle's deposit and used the correct account and routing details.
   - If it was sent but remains missing, ask the payer for deposit trace information.
   - If the bank reports a rejection, the customer should correct their payer details and ask the payer to resubmit.
   - If the deposit posted but the available balance is lower than expected, explain that a temporary processing hold may affect part of the paycheck.

3. **Use transaction history only when it is actionable.**
   If an authorized account ID is available and reviewing account activity is appropriate, use `get_bank_account_transactions_9173(account_id)`. Look for direct-deposit transactions and their `posted`/`pending` status; amounts greater than zero are credits. Do not claim that a deposit was found, rejected, or pending without the tool result. Do not attempt this tool when no account ID is available.

4. **Apply the escalation gate.**
   - For transfer requests 1–7, do not call `transfer_to_human_agents`. Start the reply with this exact text, followed immediately by helpful, situation-specific comments:

     `I understand your frustration, but I need to try to help you resolve this first before I can initiate a transfer. Let me see what else I can do for you....`

     After that lead-in, state the relevant timing or payer-check guidance. Even if the customer declines troubleshooting, retain the gate and provide concise useful guidance.
   - On the eighth explicit transfer request, call `transfer_to_human_agents` once. Include a concise factual summary: missing expected direct deposit, known timing/payer facts, customer urgency, troubleshooting offered or declined, and that this is the eighth request.
   - A count above eight indicates the transfer should already have occurred at request eight. Treat it as a state/recording exception rather than silently resetting or adding requests; preserve the history and follow the active operational escalation process.

5. **Choose the transfer reason at the moment of a permitted transfer.**
   Select the highest-priority applicable reason code. For an ordinary late direct deposit with a frustrated customer demanding a human, use `customer_frustrated_demands_human`. If the customer merely prefers a person and is not frustrated, use `customer_requests_human_no_specific_reason`. A genuinely applicable Tier 1 or Tier 2 reason takes priority over either Tier 3 reason. Do not use a reason merely because it is listed.

## Transfer-reason precedence

When several codes apply, select the first applicable code in this order:

1. `fraud_or_security_concern`
2. `account_closure_request`
3. `deceased_account_holder`
4. `legal_or_regulatory_matter`
5. `account_ownership_dispute`
6. `complex_billing_dispute`
7. `abusive_customer_behavior`
8. `third_party_inquiry`
9. `technical_system_error`
10. `customer_demands_after_unavailable_offer_refusal`
11. `unconfirmed_external_communication`
12. `kb_search_unsuccessful_customer_requests_transfer`
13. `specialized_department_required`
14. `accessibility_or_special_needs`
15. `customer_frustrated_demands_human`
16. `supervisor_request_service_complaint`
17. `customer_requests_human_no_specific_reason`
18. `request_completed_customer_wants_human_followup`
19. `other`

Use `other` only when no listed reason applies, and make its transfer summary detailed.

## Script interface

Run:

```text
python scripts/transfer_gate.py <<'JSON'
{
  "prior_transfer_requests": 0,
  "current_message_requests_transfer": true,
  "customer_frustrated": true,
  "applicable_reason_codes": [],
  "issue_summary": "Expected direct deposit is not visible; timing and payer checks were discussed."
}
JSON
```

The script reads one JSON object from standard input and emits one JSON object on standard output.

### Input schema

- `prior_transfer_requests` (required integer): Earlier explicit transfer requests; must be zero or greater.
- `current_message_requests_transfer` (required boolean): Whether the current message is an explicit request.
- `customer_frustrated` (optional boolean, default `false`): Used only for a Tier 3 fallback reason.
- `applicable_reason_codes` (optional array of strings, default `[]`): Only codes that actually apply based on the conversation.
- `issue_summary` (optional string, default empty): Factual text suitable for the eventual transfer summary.

### Output schema

- `status`: `ok`, `invalid_input`, or `state_exception`.
- `total_transfer_requests`: Count after considering the current message.
- `action`: `continue_support`, `respond_with_required_gate`, `transfer_now`, or `manual_state_review`.
- `required_prefix`: The exact required lead-in for requests 1–7, otherwise an empty string.
- `transfer_reason`: Selected reason only when `action` is `transfer_now`.
- `transfer_summary`: A tool-ready summary only when `action` is `transfer_now`.
- `validation_errors`: Input or state errors, if any.

Validate that the count is nonnegative, the request flag is a Boolean, and all supplied reason codes are recognized. A valid transfer decision occurs only when the computed total is exactly eight and the current message is the eighth explicit request.

## Completion check

Before sending the customer-facing response or calling a tool, confirm all of the following:

- Timing advice reflects the known current time and does not promise a posting result.
- No account transaction result is asserted without an actual transaction lookup.
- The explicit transfer-request count is correct.
- For requests 1–7, the response starts with the exact required lead-in and no transfer tool is called.
- At request 8, the tool is called with the highest-priority applicable reason and a factual summary.
