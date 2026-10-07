---
name: missing-direct-deposit-support
description: Respond to a customer whose expected direct deposit or paycheck has not arrived. Use for general troubleshooting, timing expectations, and safe handling of any account-specific investigation when the available banking tools are limited.
---

# Missing direct deposit support

## Purpose
Provide an empathetic, accurate response for a missing expected direct deposit without promising a deposit date, exposing personal information, or claiming that an account/deposit was checked when no authorized tool supports that check.

## Inputs
Use the live conversation, supplied clarifications, read-only observations, the available tool schemas, and the packaged knowledge available to the task. Do not treat an account-name lookup as identity verification.

## Workflow

1. **Acknowledge the urgency.** Briefly recognize the missed payday and its impact. Do not promise an immediate arrival, expedited posting, a fee waiver, or a rent-related accommodation unless a supported policy or tool explicitly permits it.

2. **Determine whether an account-specific check is possible.**
   - Inspect the tools actually available in the current runtime.
   - If a supported account/deposit-status tool exists and the customer is appropriately verified for that access, use it and report only its result.
   - If no such tool is available, do not state or imply that the deposit is absent, pending, rejected, or held. Give the general troubleshooting path instead.
   - A name, email, or other single identifying value is not sufficient verification for account-specific disclosure or changes. If an account-specific action is needed, request confirmation of two of the four identity fields (date of birth, email, phone number, address), compare them to the retrieved customer record, obtain the current timestamp, and call `log_verification` only after two fields match. Do not unnecessarily repeat sensitive values in the customer-facing reply.

3. **Give the supported timing expectation.** Explain that direct deposits can take up to 3 days to arrive, depending on when the payer processes payroll and transmits the funds. Posting is driven by the payer's processing/transmission schedule; it typically posts on the scheduled pay date once the bank receives it. Avoid presenting the three-day window as a guarantee or asserting that a particular deposit is still in it unless its transmission date is known.

4. **Give concrete next steps in order.** Ask the customer to:
   - Check whether the deposit appears in their account, including whether it posted with only part currently available.
   - Contact the employer or other direct-deposit payer to confirm they initiated this pay cycle's payment and the date/time it was transmitted.
   - Confirm that the payer has the correct routing number, account number, account type, and account-holder name.
   - Request the ACH/direct-deposit trace information from the payer; this enables a more efficient follow-up.
   - If the payer says the bank rejected the deposit, correct the details with the payer and ask for resubmission.
   - Contact bank support with the payer name, expected amount, expected date, and trace information if available.

5. **Address partial availability only conditionally.** If the customer says the deposit has posted but the available balance is lower than expected, explain that a temporary hold may apply to part of the paycheck while processing completes. Do not mention a hold when the deposit has not posted unless it helps distinguish this separate situation.

6. **Close with a focused follow-up question.** Ask for non-sensitive operational facts that help determine the next step, such as whether the payer confirmed transmission, when it was sent, or whether a trace number is available. Do not ask for account or routing numbers in chat.

## Customer-facing response pattern
Use concise, plain language similar to:

- Empathy: acknowledge that a missing Friday paycheck is stressful.
- Limitation/accuracy: say that deposit arrival depends on the payer's payroll transmission and can take up to three days; do not claim an unperformed account review.
- Actions: list confirmation with the payer, confirmation of submitted account details, and requesting a trace number.
- Escalation information: explain what details to provide to support if it remains missing.
- Question: ask whether the payer has confirmed sending the payment and can provide a trace number.

## Tool and safety rules

- Use only tools declared in the current task. Do not invent deposit lookups, payroll traces, transfers, or account-credit actions.
- Do not change customer profile information as part of deposit troubleshooting.
- Do not transfer merely because the situation is urgent. Transfer only when the customer requests a human or a supported transfer condition applies; select an available reason that precisely matches the request.
- Keep personally identifiable information out of the final response unless needed for a verified, authorized account-specific action.
- Never claim that a payer, bank, or account record confirmed something unless that confirmation appears in an actual tool result or the customer states it.

## Validation before sending
Confirm the response: (1) acknowledges the concern, (2) includes the payer-dependent timing caveat, (3) tells the customer to confirm initiation/transmission and request trace information, (4) mentions account-detail correction/resubmission when applicable, (5) does not promise timing or invent a deposit status, and (6) does not disclose private record details or perform unsupported actions.
