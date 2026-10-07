---
name: credit-card-dispute-intake
summary: Safely gather, validate, and submit one or more credit-card transaction disputes, including provisional-credit determinations and card-replacement coordination for fraud.
description: Use for a customer reporting credit-card fraud, duplicate charges, billing errors, merchant disputes, or a fraud-driven request to replace a card. It prevents submitting disputes with guessed facts, uses the required internal dispute tool only after complete intake, and applies the documented provisional-credit rules per transaction.
---

# Credit Card Dispute Intake and Submission

Use this Skill when a customer wants to dispute one or more credit-card transactions. A dispute is **one tool submission per transaction**. Do not merge several transactions into one dispute or infer missing answers from transaction history.

## 1. Identify the customer and card

1. Locate the customer using the supplied normal banking lookup tools.
2. Follow standard identity verification: obtain and confirm at least two of date of birth, registered email, registered phone, and registered address. Retrieve the current time and call `log_verification` only after successful verification.
3. Look up the customer's credit-card accounts and transaction history. Confirm each requested transaction belongs to the customer and to the intended card account.
4. Obtain the card last four digits through the documented discovered tool `get_card_last_4_digits(credit_card_account_id)` rather than asking the customer to disclose the complete card number. Unlock it first if the runtime requires discovery tools to be unlocked.
5. If the customer reports fraud and asks to replace the affected card, record `card_action: "cancel_and_reissue"` for every dispute on that card. Otherwise use `"keep_active"`. Do not assume this action for a different card account.

## 2. Build a separate complete intake record for each transaction

For every requested transaction, record the transaction ID, purchase date, amount, card/account, and exactly one allowed reason:

- `unauthorized_fraudulent_charge`
- `duplicate_charge`
- `incorrect_amount`
- `goods_services_not_received`
- `goods_services_not_as_described`
- `canceled_subscription_still_charging`
- `refund_never_processed`

Ask for facts that are not provided, grouping questions efficiently while preserving per-transaction answers:

- the date the customer noticed the issue, in `MM/DD/YYYY`;
- whether they contacted the merchant first for **each non-fraud** transaction;
- the requested resolution for each dispute: `full_refund`, `partial_refund`, or `reversal_of_charge`;
- the partial-refund dollar amount if and only if the chosen resolution is `partial_refund`.

Do not turn “charged $X but it should have been $Y” into a partial-refund request without confirmation. Ask whether the customer wants a partial refund and, if so, the precise amount.

Use the registered full name, user ID, phone, email, and address obtained from the verified customer record. Verify dates and transaction facts against transaction history; if there is a mismatch, clarify it with the customer before submitting.

## 3. Determine provisional-credit eligibility independently for each dispute

Check dispute history with `get_user_dispute_history_7291(user_id)` (unlock first if required), count disputes filed within the prior 12 months, and calculate account age using the current date. Apply all requirements below; eligibility is true only if all apply:

1. The relevant card account has been open at least 60 days.
2. The reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`.
3. For `goods_services_not_received`, the purchase is more than 30 days old.
4. The amount is at least $25.00 and is no more than the card tier’s maximum:
   - Entry: $2,500
   - Mid: $5,000
   - Premium: $10,000
   - Elite: $15,000
   - Invitation: $25,000
5. The customer has not filed more than two disputes in the preceding 12 months.
6. For non-fraud eligible categories, the customer contacted the merchant first.

Reasons outside the three listed categories are not eligible. Do not use a requested refund amount in place of the actual disputed transaction amount. `scripts/evaluate_dispute.py` can calculate the eligibility result and validate required submission fields from a supplied case JSON; review its `reasons` and `missing` output before any submission.

## 4. Submit only when the record is complete

Do not unlock or call the filing tool while any required field remains unknown or invalid. After all records are complete:

1. Unlock `file_credit_card_transaction_dispute_4829`.
2. For each transaction, call `call_discoverable_agent_tool` with `agent_tool_name` set to that exact name and `arguments` set to a JSON string containing:
   - `transaction_id` (string)
   - `card_action` (`keep_active` or `cancel_and_reissue`)
   - `card_last_4_digits` (four-digit string)
   - `full_name`, `user_id`, `phone`, `email`, `address`
   - `contacted_merchant` (boolean)
   - `purchase_date` and `issue_noticed_date` (`MM/DD/YYYY`)
   - `dispute_reason` (one allowed code)
   - `resolution_requested` (one allowed code)
   - `eligible_for_provisional_credit` (boolean)
   - `partial_refund_amount` (number only when resolution is `partial_refund`)
3. Interpret and communicate the tool result accurately. If a call fails, report the failure and correct only the indicated missing or invalid information; do not claim the dispute was filed. Never retry a result reported as unknown.

## 5. Replacement-card coordination

A dispute with `cancel_and_reissue` means the old card will be cancelled and a replacement issued through the dispute workflow. Explain that the old card will no longer work for new purchases and the replacement will have a different card number and CVV.

If a separate replacement order is required or requested, use the replacement-card workflow separately: confirm eligibility first, including pending-order and replacement-limit checks; confirm the shipping address, exact reason, shipping speed, and any required expedited-fee acknowledgement; then unlock and call `order_replacement_credit_card_7291`. Do not create a duplicate replacement order merely because the dispute action is `cancel_and_reissue`.

For fraud or stolen cards, recommend expedited shipping. Standard is 7–10 business days and free; expedited is 2–3 business days. Fees depend on tier, with premium and higher cards receiving expedited shipping at no charge. Clearly state the selected delivery estimate after a successful separate replacement order.

## Handling incomplete or unsupported cases

- Continue intake by asking only for the remaining fields; do not guess noticed dates, merchant-contact answers, resolution, partial amount, last four digits, or dispute-history count.
- A customer may file a dispute even when provisional credit is false; submit it with `eligible_for_provisional_credit: false` once all filing fields are complete.
- If transaction ownership, identity, a tool response, or the account/card association is ambiguous, pause and clarify or use the appropriate escalation path rather than filing against a guessed transaction.
- Keep the customer informed of which disputes are awaiting information and which, if any, were successfully filed.

## Validator usage

Run the packaged validator with JSON on stdin:

```text
python3 scripts/evaluate_dispute.py <<'JSON'
{
  "as_of_date": "MM/DD/YYYY",
  "account_open_date": "MM/DD/YYYY",
  "card_tier": "premium",
  "prior_disputes_12_months": 0,
  "transaction_amount": 100.0,
  "purchase_date": "MM/DD/YYYY",
  "dispute": {"transaction_id": "...", "card_action": "keep_active", "card_last_4_digits": "1234", "full_name": "...", "user_id": "...", "phone": "...", "email": "...", "address": "...", "contacted_merchant": true, "purchase_date": "MM/DD/YYYY", "issue_noticed_date": "MM/DD/YYYY", "dispute_reason": "duplicate_charge", "resolution_requested": "full_refund"}
}
JSON
```

It emits JSON with `valid_for_submission`, `eligible_for_provisional_credit`, `missing`, `invalid`, and eligibility `reasons`. A valid result is necessary before constructing the tool arguments, but the executor must still perform the real normal-tool lookups and tool submission.
