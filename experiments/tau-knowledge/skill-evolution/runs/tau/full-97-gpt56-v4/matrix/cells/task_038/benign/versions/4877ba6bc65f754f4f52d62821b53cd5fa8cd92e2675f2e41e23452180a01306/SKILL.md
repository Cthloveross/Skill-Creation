---
name: credit-card-dispute-and-reissue
version: 1.0.0
description: Process one or more credit-card transaction disputes, determine provisional-credit eligibility per transaction, and coordinate a requested fraud-related card replacement using the available banking and discovered tools.
---

# Credit Card Dispute and Card Reissue

Use this Skill when a verified customer wants to dispute credit-card transactions, especially when fraud may require a replacement card. Process each disputed transaction separately. Do not file a dispute or order a replacement until identity verification and all required facts are complete.

## Required prerequisites

1. Locate the customer and relevant card account and transaction records using the normal banking lookup tools.
2. Verify identity by having the customer confirm **two of four** account fields: date of birth, registered email, registered phone, and registered address. Do not simply reveal account values and ask for confirmation in a way that supplies the answer.
3. Get the current timestamp and call `log_verification` with all required stored customer fields and that timestamp after successful verification.
4. Confirm the transaction belongs to the selected card and identify its transaction ID, amount, and purchase date.
5. Obtain the card last four digits. If unavailable, unlock and call the discovered `get_card_last_4_digits` tool with the credit-card account ID. If the runtime exposes it as a customer tool instead, provide the customer the exact `get_card_last_4_digits(credit_card_account_id)` tool. Do not guess the digits.

## Collect per-dispute facts

For every transaction, collect or establish:

- transaction ID and purchase date;
- issue-noticed date (convert to `MM/DD/YYYY`; resolve relative dates using the current time);
- one exact reason code: `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, or `refund_never_processed`;
- whether the customer contacted the merchant. Fraud does not require contact, but explicitly establish the boolean for every dispute;
- one exact resolution: `full_refund`, `partial_refund`, or `reversal_of_charge`; collect a positive numeric partial amount only for `partial_refund`;
- card action: `keep_active` or `cancel_and_reissue`.

Do not infer that a customer contacted a merchant for one transaction merely because they contacted the merchant about another transaction. If a statement is ambiguous, ask a focused follow-up.

## Determine provisional-credit eligibility

Before filing, retrieve the customer’s dispute history using the discovered `get_user_dispute_history_7291` tool (unlock it first if required) and count disputes filed in the 12 months before the filing date. Retrieve the card account opening date and card tier. Use `scripts/provisional_credit.py` to make the determination consistently.

Eligibility is true only if all applicable rules pass:

- account has been open at least 60 days;
- reason is fraud, duplicate, or goods/services not received; for non-receipt, purchase must be more than 30 days old;
- amount is at least $25 and within the tier maximum;
- no more than two prior disputes in the preceding 12 months;
- for every non-fraud reason, the customer contacted the merchant.

Tier maxima: Entry $2,500; Mid $5,000; Premium $10,000; Elite $15,000; Invitation $25,000. Silver Rewards is Mid tier. A reason not listed as qualifying is ineligible even if all other conditions pass.

Example helper call (do not use these values as case data):

```bash
printf '%s' '{"account_open_date":"2024-01-01","filing_date":"2025-01-01","purchase_date":"2024-10-01","amount":40,"card_tier":"Mid","prior_disputes_last_12_months":0,"contacted_merchant":true,"dispute_reason":"duplicate_charge"}' | python3 scripts/provisional_credit.py
```

The helper emits `{"eligible": boolean, "failed_rules": [...]}`. Treat invalid dates, unknown tier, missing facts, or malformed amounts as a stop condition rather than assuming eligibility.

## Replacement workflow

When the customer requests a replacement, use `cancel_and_reissue` for every dispute on that compromised card. Order only one replacement for that card, not one per dispute.

Before ordering:

1. Confirm the shipping address, including unit information if applicable.
2. Record one replacement reason (`fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`). For compromised-card reports use `fraud_suspected` when supported by the customer’s report.
3. Confirm standard versus expedited shipping. State standard is 7–10 business days and free. State expedited is 2–3 business days; Entry is $15, Mid is $10, Premium and above is free. Capture consent if a fee applies.
4. Check any available replacement-status/eligibility data. Do not order if a pending request exists or the applicable 60-day replacement limit has been exceeded. Escalate or explain the restriction instead.

Unlock `order_replacement_credit_card_7291`, then call it with the selected card account identifier, reason, confirmed address, shipping speed, fee acknowledgement, and relevant notes. A successful order cancels the old card and issues a new card number/CVV. If the replacement is successfully ordered before filing, disputes still use `cancel_and_reissue`.

## File disputes

After prerequisites are satisfied, unlock `file_credit_card_transaction_dispute_4829`. Call it once per transaction through `call_discoverable_agent_tool`, supplying a JSON string with:

```json
{
  "transaction_id": "string",
  "card_action": "keep_active or cancel_and_reissue",
  "card_last_4_digits": "4-digit string",
  "full_name": "string",
  "user_id": "string",
  "phone": "registered phone",
  "email": "registered email",
  "address": "registered address",
  "contacted_merchant": true,
  "purchase_date": "MM/DD/YYYY",
  "issue_noticed_date": "MM/DD/YYYY",
  "dispute_reason": "allowed reason code",
  "resolution_requested": "full_refund, partial_refund, or reversal_of_charge",
  "eligible_for_provisional_credit": false
}
```

Include `partial_refund_amount` only where `resolution_requested` is `partial_refund`. Never reuse a transaction ID or submit a dispute after a tool result reports failure or unknown status without first resolving that status. Report filed dispute confirmations, the replacement status/delivery window, and whether provisional credit is eligible (without promising it for ineligible cases). If a required fact cannot be obtained, explain precisely what is needed and do not call the filing tool.
