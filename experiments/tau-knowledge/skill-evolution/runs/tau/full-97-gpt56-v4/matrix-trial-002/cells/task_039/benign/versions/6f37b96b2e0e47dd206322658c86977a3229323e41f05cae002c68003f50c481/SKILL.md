---
name: credit-card-dispute-and-fraud-replacement
version: 1.0.0
description: Process one or more credit-card transaction disputes, determine provisional-credit eligibility, and coordinate a fraud-related replacement card when requested. Use when a verified customer identifies specific credit-card transactions and wants disputes, a replacement, or both.
---

# Credit Card Dispute and Fraud Replacement

Use this Skill for a verified customer's credit-card disputes. A dispute is filed separately for each transaction. Do not invent transaction IDs, card digits, customer fields, dates, merchant-contact status, desired resolution, prior-dispute count, or eligibility facts.

## Required inputs and safe prerequisites

1. Identify the customer and their relevant credit-card account. Confirm the disputed transactions belong to that card/account, including merchant, amount, date, and transaction ID.
2. Verify identity using the normal standard: confirm at least two of date of birth, email, phone number, and address against the customer record. Obtain the current timestamp with `get_current_time`, then call `log_verification` with all required record fields. Do this before filing a dispute or ordering a replacement.
3. Obtain or confirm all dispute facts per transaction:
   - transaction ID and purchase date;
   - date the customer noticed the problem, in `MM/DD/YYYY`;
   - one supported dispute reason;
   - whether they contacted the merchant;
   - requested resolution, plus a numeric partial-refund amount only for a partial refund.
4. Get the card's last four digits rather than guessing or asking the customer to reveal a full card number. Unlock and call `get_card_last_4_digits` with the applicable credit-card account ID, using the normal discoverable-agent-tool workflow.
5. Get the customer's actual credit-card dispute history: unlock and call `get_user_dispute_history_7291` with `user_id`. Count disputes filed in the 12 months preceding the eligibility evaluation date. Do not rely on an unavailable customer recollection when this documented lookup is available.

If an account, transaction, or required fact cannot be reliably identified, ask a focused clarification and do not file that transaction yet. Keep separately identified card accounts separate; never apply a card's digits or account status to a different card.

## Dispute field mapping

For each requested transaction, use exactly one of:

- `unauthorized_fraudulent_charge`
- `duplicate_charge`
- `incorrect_amount`
- `goods_services_not_received`
- `goods_services_not_as_described`
- `canceled_subscription_still_charging`
- `refund_never_processed`

Use exactly one resolution:

- `full_refund`
- `partial_refund` (requires `partial_refund_amount`, a positive number that does not exceed the transaction amount)
- `reversal_of_charge`

Set `contacted_merchant` from the customer's answer. A fraud dispute may validly have `false`; never change it merely because merchant contact is generally recommended.

Set `card_action` to:

- `keep_active` when the customer will retain and use the present card;
- `cancel_and_reissue` when the card is being cancelled and a replacement is being issued, whether the replacement was already ordered or cancellation/reissue is part of this dispute workflow.

The customer identity fields (`full_name`, `user_id`, registered `phone`, `email`, and `address`) must come from the verified record. Dates passed to the filing tool must be `MM/DD/YYYY`.

## Provisional credit determination

Determine this independently for each transaction; do not assume every dispute under the same card has the same result. Use `scripts/provisional_credit.py` to make the deterministic assessment once the necessary facts are available.

Eligibility is true only if **all** of these hold:

1. The account was open at least 60 days as of the evaluation date.
2. The reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`.
3. For `goods_services_not_received`, the purchase is more than 30 days before the evaluation date.
4. The amount is at least $25.00 and no greater than the limit for the actual card tier.
5. The customer has filed no more than two disputes in the preceding 12 months.
6. For any non-fraud eligible reason, the customer contacted the merchant.

Limits are Entry $2,500; Mid $5,000; Premium $10,000; Elite $15,000; Invitation $25,000. Determine the tier from the documented card product, not its balance. Reasons outside the three eligible reasons always yield false. `eligible_for_provisional_credit` is an assessment flag, not a promise that a temporary credit has been posted.

## File each complete dispute

For each transaction whose facts are complete:

1. Validate the input with `scripts/validate_dispute.py`. Resolve every reported error before any filing call.
2. Unlock `file_credit_card_transaction_dispute_4829` if needed.
3. Call `call_discoverable_agent_tool` with `agent_tool_name` set to `file_credit_card_transaction_dispute_4829` and `arguments` set to a JSON string containing:

```json
{
  "transaction_id": "string",
  "card_action": "keep_active or cancel_and_reissue",
  "card_last_4_digits": "four digit string",
  "full_name": "verified customer name",
  "user_id": "verified user ID",
  "phone": "registered phone",
  "email": "registered email",
  "address": "registered address",
  "contacted_merchant": true,
  "purchase_date": "MM/DD/YYYY",
  "issue_noticed_date": "MM/DD/YYYY",
  "dispute_reason": "supported reason",
  "resolution_requested": "supported resolution",
  "eligible_for_provisional_credit": false
}
```

For `partial_refund`, add `partial_refund_amount` as a JSON number. Omit it for the other resolutions unless the tool explicitly requires otherwise. Record each tool result. If one filing fails, explain the failure for that transaction and continue only with other complete, independently valid transactions; do not claim a failed or unattempted filing was submitted.

## Replacement-card branch

A fraud-related replacement is a separate action and should be performed only if the customer requests it (or policy otherwise requires it). Before ordering:

1. Complete verification and identify the account.
2. Confirm the full shipping address, including unit/suite when applicable.
3. Obtain one replacement reason: `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`. For fraud, use `fraud_suspected` only when it accurately reflects the report.
4. Ask whether standard (7–10 business days, no fee) or expedited (2–3 business days) shipping is wanted. Explain any applicable expedited fee and capture consent if a fee applies: Entry $15, Mid $10, Premium and above $0.
5. Check pending orders by unlocking/calling `get_pending_replacement_orders_5765` with the credit-card account ID. A pending or shipped order blocks another replacement. Also determine the customer's replacement count in the prior 60 days and ensure it is within the tier limit: Entry 2, Mid 3, Premium and above 4. If eligibility cannot be established, do not unlock/order; explain or escalate for manual review.
6. If eligible, unlock `order_replacement_credit_card_7291` and call it with the documented account identifier, reason, confirmed `shipping_address`, `shipping_speed`, fee-consent value when applicable, and relevant notes.

After a successful order, advise that the old card is cancelled for new purchases, the replacement has a different number/CVV, the account number remains the same, and the expected delivery window. Advise the customer to watch for placement/shipping emails, update stored card details after receipt, and review additional activity for fraud. A replacement request does not replace the need to file each desired dispute.

## Customer-facing completion

Summarize only confirmed results: which transactions were filed, their requested resolutions, whether the card will remain active or be replaced, and that provisional credit (if eligible) is temporary pending investigation. For an incomplete case, explicitly list only the missing facts or blocked prerequisite and the next action.

## Helper scripts

Both scripts read one JSON object from standard input and emit one JSON object to standard output. They use only Python's standard library and make no bank-tool calls.

- `scripts/provisional_credit.py`: deterministic eligibility assessment. Input fields: `account_open_date`, `evaluation_date`, `purchase_date`, `reason`, `amount`, `card_tier`, `prior_disputes_12_months`, and `contacted_merchant`. Dates are `MM/DD/YYYY`; `amount` may be a number or currency-like string. Output includes `eligible_for_provisional_credit`, `reasons`, `normalized_amount`, and `maximum_limit`.
- `scripts/validate_dispute.py`: validates a filing payload and, when supplied, checks that `partial_refund_amount` is sensible relative to `transaction_amount`. Input is the intended filing payload plus optional `transaction_amount`. Output has `valid` and `errors`.

Example assessment invocation:

```sh
printf '%s' '{"account_open_date":"01/01/2024","evaluation_date":"03/15/2025","purchase_date":"01/10/2025","reason":"duplicate_charge","amount":"50.00","card_tier":"mid","prior_disputes_12_months":1,"contacted_merchant":true}' | python3 scripts/provisional_credit.py
```

Before filing, require the validator to return `"valid": true` and manually verify that the transaction ID, card digits, account, and facts correspond to the same requested charge.
