---
name: credit-card-transaction-dispute-filing
description: Safely prepares and files one or more credit-card transaction disputes when the customer, transaction records, account details, and discovered banking tools are available. Use for unauthorized charges, duplicate charges, billing errors, delivery issues, subscription charges, and missing refunds, including provisional-credit determinations.
---

# Credit-card transaction dispute filing

Use this Skill to file each disputed transaction separately through the internal dispute tool. It supports a batch of disputes, but a batch is a set of independent filings: never combine multiple transaction IDs in one filing.

## Required prerequisites

Before any filing:

1. Identify the customer and obtain the canonical `user_id`.
2. Verify the customer's identity by having them confirm at least two of date of birth, registered email, registered phone, and registered address. Retrieve the registered profile, obtain the current time, and call `log_verification` only after two fields are confirmed.
3. Retrieve the customer's credit-card accounts and transaction history. Match every requested dispute to a completed transaction using its transaction ID, card type, merchant, amount, and purchase date. Do not file against an ambiguous or unmatched transaction.
4. For each account involved, obtain only its last four digits. Use the documented discovered tool `get_card_last_4_digits` with `credit_card_account_id`; do not request or expose a full card number.
5. For a business-card dispute, confirm the requester is authorized by the business resolution or comparable authorization to act for the business. Do not file the business-card dispute if this cannot be confirmed.
6. Retrieve the customer’s dispute history with `get_user_dispute_history_7291`. It is required to determine the prior-dispute eligibility criterion; a customer’s inability to recall the count is not a substitute for the history lookup.

When the tool platform requires discovered agent tools to be unlocked, unlock `get_card_last_4_digits` and `get_user_dispute_history_7291` before calling them through `call_discoverable_agent_tool`. Use their documented argument names: `credit_card_account_id` and `user_id`, respectively.

## Collect and normalize each dispute

For every transaction, collect or confirm:

- `transaction_id`, the matched card’s last four digits, and purchase date;
- date the customer noticed the issue, in `MM/DD/YYYY`; when they say “today,” obtain the current date with `get_current_time` and use that date;
- whether they contacted the merchant (`true` or `false`);
- one reason code:
  - `unauthorized_fraudulent_charge`
  - `duplicate_charge`
  - `incorrect_amount`
  - `goods_services_not_received`
  - `goods_services_not_as_described`
  - `canceled_subscription_still_charging`
  - `refund_never_processed`
- one resolution:
  - `full_refund`
  - `partial_refund` (also collect a positive dollar `partial_refund_amount`)
  - `reversal_of_charge`
- one card action:
  - `keep_active`
  - `cancel_and_reissue`

Do not infer a partial-refund amount from an approximate normal bill. Obtain the exact requested amount. Do not silently choose a card action. For an unauthorized charge, explain the replacement option and record the customer’s choice. Use `cancel_and_reissue` when the card is being replaced, including when a replacement was already ordered; otherwise use `keep_active` only when the customer has chosen to retain the card.

For non-fraud reasons, merchant contact is necessary for provisional-credit eligibility, but a dispute can still be filed with `contacted_merchant: false` if the customer wants to proceed. Fraud does not require merchant contact.

## Determine provisional credit before filing

Calculate eligibility per transaction from the account and transaction data, using a snapshot of **pre-existing** disputes in the preceding 12 months (before the current set of filings). A transaction is eligible only if all conditions hold:

1. The card account has been open at least 60 days.
2. The reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`. The last reason additionally requires the purchase to be more than 30 days old at the time of filing.
3. The transaction amount is at least $25.00 and no more than the card-tier limit.
4. The customer has not filed more than two disputes during the preceding 12 months.
5. For every non-fraud reason, the customer contacted the merchant.

Tier limits are Entry $2,500 (Bronze Rewards, EcoCard, Business Bronze Rewards, Crypto-Cash Back); Mid $5,000 (Silver Rewards, Business Silver Rewards, Green Rewards, Silver Zoom); Premium $10,000 (Gold Rewards, Business Gold Rewards); Elite $15,000 (Platinum Rewards, Business Platinum Rewards); and Invitation $25,000 (Diamond Elite).

A requested priority does not alter these rules or a tier limit. If the history lookup, account-open date, card tier, amount, or relevant dates are unavailable, do not guess `eligible_for_provisional_credit`; obtain the missing information first.

## Validate with the packaged planner

Prepare a runtime JSON file matching the schema implemented by `scripts/dispute_planner.py`, then run:

```text
python3 scripts/dispute_planner.py < runtime_input.json
```

The script reads one JSON object from stdin and emits one JSON report to stdout. It does not contact banking systems or file disputes. Its primary input fields are:

- `as_of_date`: filing date in `MM/DD/YYYY`.
- `identity_verified`: `true` only after the verification log succeeds.
- `user`: object with `full_name`, `user_id`, `phone`, `email`, and `address`.
- Either `prior_disputes_past_12_months` (integer) or `prior_disputes` (history records containing `dispute_date`).
- `business_authorization_confirmed`: boolean, required as `true` for card types containing `Business`.
- `transactions`: array of objects containing `transaction_id`, `card_type`, `card_last_4_digits`, `amount`, `account_open_date`, `purchase_date`, `issue_noticed_date`, `contacted_merchant`, `dispute_reason`, `resolution_requested`, `card_action`, and `partial_refund_amount` when applicable.

Review `validation_errors` and correct every error. Submit only payloads in `filings` when `ready` is `true`. Each payload includes the required boolean `eligible_for_provisional_credit` and has `partial_refund_amount` only for a partial-refund request.

## File the disputes

1. Unlock `file_credit_card_transaction_dispute_4829` using `unlock_discoverable_agent_tool`.
2. For every validated planner payload, call `call_discoverable_agent_tool` with:
   - `agent_tool_name`: `file_credit_card_transaction_dispute_4829`
   - `arguments`: a JSON string containing exactly that filing payload.
3. Process each response independently and record the transaction and returned dispute reference/status. A failure for one transaction must not be represented as success for another.
4. If a discovered tool cannot be unlocked, a call rejects the payload, or required evidence is unavailable, do not fabricate a result or retry a state-changing call blindly. Tell the customer which filings succeeded, which did not, and what follow-up is required.

The filing payload has this shape:

```json
{
  "transaction_id": "string",
  "card_action": "keep_active | cancel_and_reissue",
  "card_last_4_digits": "string",
  "full_name": "string",
  "user_id": "string",
  "phone": "string",
  "email": "string",
  "address": "string",
  "contacted_merchant": true,
  "purchase_date": "MM/DD/YYYY",
  "issue_noticed_date": "MM/DD/YYYY",
  "dispute_reason": "allowed reason code",
  "resolution_requested": "full_refund | partial_refund | reversal_of_charge",
  "partial_refund_amount": 0.0,
  "eligible_for_provisional_credit": false
}
```

`partial_refund_amount` is omitted unless `resolution_requested` is `partial_refund`.
