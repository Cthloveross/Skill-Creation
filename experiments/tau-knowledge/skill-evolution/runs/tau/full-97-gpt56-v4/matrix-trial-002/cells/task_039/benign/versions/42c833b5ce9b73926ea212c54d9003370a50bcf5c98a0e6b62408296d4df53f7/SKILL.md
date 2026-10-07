---
name: credit-card-dispute-and-fraud-replacement
version: 1.1.0
description: Safely handle one or more identified credit-card transaction disputes and a requested fraud replacement. Use this for a customer reporting unauthorized, duplicate, billing, merchant, subscription, delivery, or refund problems on a credit card.
---

# Credit-card dispute and fraud-replacement workflow

A dispute is one filing per transaction. Follow this workflow whenever a customer wants a dispute. Never infer a transaction ID, last four digits, merchant-contact answer, date noticed, resolution, identity field, or shipping choice from a similar transaction or card.

## 1. Identify and verify before taking action

1. Locate the customer from the full name (or another supplied identifier), then retrieve their card accounts and transaction list with the normal banking tools. Match every requested charge by account/card product, merchant, exact amount, date, and transaction ID. If more than one match is possible, ask the customer to disambiguate.
2. Before viewing additional sensitive information, filing a dispute, or ordering a card, confirm **two of four** values supplied by the customer against the record: date of birth, registered email, phone, and address. A name or data merely retrieved from the record is not a confirmation.
3. Once two match, obtain the current time with `get_current_time` and call `log_verification` with the complete customer record and timestamp. Use only the verified record for `full_name`, `user_id`, `phone`, `email`, and `address` in a filing.
4. If verification is incomplete, ask only for the missing identity confirmations. Do not log verification or perform a filing/replacement action yet.

## 2. Gather dispute facts for each charge

For every requested transaction, collect and normalize:

- `transaction_id` and the actual `purchase_date` (`MM/DD/YYYY`);
- `issue_noticed_date` (`MM/DD/YYYY`);
- `contacted_merchant` as a boolean; and
- exactly one reason and resolution below.

Supported reasons are exactly:

- `unauthorized_fraudulent_charge`
- `duplicate_charge`
- `incorrect_amount`
- `goods_services_not_received`
- `goods_services_not_as_described`
- `canceled_subscription_still_charging`
- `refund_never_processed`

Supported resolutions are exactly `full_refund`, `partial_refund`, and `reversal_of_charge`. A partial refund additionally requires a positive numeric `partial_refund_amount` no larger than the transaction amount. Merchant contact can be false for a fraud claim; do not demand it for fraud merely because contact is generally recommended.

Ask a compact, transaction-specific clarification only for facts that are not already supplied. A customer reporting several charges must not be forced into one aggregate dispute.

## 3. Obtain the required last four digits correctly

The documented `get_card_last_4_digits(credit_card_account_id: str)` is a **user-discoverable** tool, not an agent-discoverable tool.

- After the correct account is identified, use `give_discoverable_user_tool` with `discoverable_tool_name` `get_card_last_4_digits` and JSON arguments containing that account's `credit_card_account_id`.
- Tell the customer to run that exact tool and provide only the resulting four digits. Do **not** unlock or call it with `unlock_discoverable_agent_tool` or `call_discoverable_agent_tool`.
- If the tool is unavailable to the customer, provide the documented alternative: sign in to the app or website, open the correct credit-card account, select the card, choose **View card details** or **Reveal card number**, complete the identity confirmation if prompted, and provide only the last four digits.
- If the lookup reports an unknown-tool error and the customer also cannot use either app or website route, explain that no documented self-service alternative can safely supply the digits. Transfer the case to a human agent with reason `technical_system_error`, summarizing the failed lookup and the incomplete dispute/replacement prerequisites. Do not guess digits or retry the same failed lookup.
- Do not file until four numeric digits have been obtained. Never guess them, use a full card number, or reuse digits from a different account.

## 4. Check dispute history and provisional-credit eligibility

After identity verification, unlock `get_user_dispute_history_7291` and call it through `call_discoverable_agent_tool` with `{"user_id": "..."}`. Count disputes in the 12 months before the evaluation date from the returned history; do not ask the customer for a count when this lookup is available.

For each transaction, call `scripts/provisional_credit.py` with JSON:

```json
{
  "account_open_date": "MM/DD/YYYY",
  "evaluation_date": "MM/DD/YYYY",
  "purchase_date": "MM/DD/YYYY",
  "amount": 0.00,
  "card_tier": "entry|mid|premium|elite|invitation",
  "reason": "one supported reason",
  "prior_disputes_12_months": 0,
  "contacted_merchant": true
}
```

Use its `eligible_for_provisional_credit` result in the filing. It is true only when the account is at least 60 days old; the reason is fraud, duplicate, or goods/services not received; a non-fraud eligible reason involved merchant contact; goods-not-received was purchased more than 30 days ago; amount is at least $25 and within its tier limit; and the customer has no more than two disputes in the preceding 12 months. The tier limits are Entry $2,500, Mid $5,000, Premium $10,000, Elite $15,000, Invitation $25,000. Map the named product to its documented tier (Gold and Business Gold are Premium), rather than using balance or rewards.

If a required eligibility input is unavailable, do not claim eligibility; obtain it or leave that transaction unfiled. `false` is not an error when the facts establish ineligibility.

## 5. Validate and file each complete dispute

Set `card_action` to `cancel_and_reissue` if the customer wants this card cancelled and replaced; otherwise set it to `keep_active`. Validate each independently complete payload with `scripts/validate_dispute.py` before filing. The validator reads one JSON object on stdin and emits `{"valid": boolean, "errors": [string, ...]}`; include `transaction_amount` only to validate a partial-refund ceiling, then omit it from the filing payload.

Unlock `file_credit_card_transaction_dispute_4829`, then use `call_discoverable_agent_tool` once per transaction with a JSON-string argument containing exactly the required tool fields:

```json
{
  "transaction_id": "...",
  "card_action": "keep_active",
  "card_last_4_digits": "1234",
  "full_name": "verified record name",
  "user_id": "verified record ID",
  "phone": "verified registered phone",
  "email": "verified registered email",
  "address": "verified registered address",
  "contacted_merchant": true,
  "purchase_date": "MM/DD/YYYY",
  "issue_noticed_date": "MM/DD/YYYY",
  "dispute_reason": "duplicate_charge",
  "resolution_requested": "reversal_of_charge",
  "eligible_for_provisional_credit": false
}
```

Add numeric `partial_refund_amount` only for a partial refund. If a call fails, record and explain that transaction's failure; it is not filed. Continue with other separately complete, valid transactions rather than falsely treating the batch as all-or-nothing.

## 6. Separate fraud-replacement branch

Do a replacement only when requested. In addition to verification, obtain a confirmed complete shipping address, one reason (`fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`), and a shipping selection. Standard is 7–10 business days and free. Expedited is 2–3 business days; Entry costs $15, Mid costs $10, and Premium or higher is free. Record fee consent when a fee applies. For reported fraud, `fraud_suspected` is appropriate and expedited should be recommended, not imposed.

Before ordering, unlock and call `get_pending_replacement_orders_5765` with the account ID. A pending or shipped order blocks a new order. Also establish that the card's replacement count in the prior 60 days is within its tier limit (Entry 2, Mid 3, Premium and above 4). No replacement-history lookup is documented here: if that count cannot be established from available customer/account records, do not invent it or order; explain that manual review is needed.

Only if all replacement prerequisites are met, unlock and call `order_replacement_credit_card_7291` using the actual account identifier, confirmed address, selected speed, fee acknowledgement when relevant, and notes. After a successful order, state that the old card is cancelled for new purchases, the new card has a different number/CVV while the account number remains unchanged, the delivery window, and that placement/shipping emails will be sent. Remind a fraud victim to review other transactions and update saved card details after receipt.

## Completion and safe stopping

Report only successful filings and replacement orders. Mention each filed transaction, requested resolution, and that any eligible provisional credit is temporary while investigated. Clearly identify an unfiled transaction or unplaced replacement and its precise missing prerequisite. If the customer stops or does not supply required digits/choices, do not make further state-changing calls.

## Included scripts

- `scripts/provisional_credit.py`: JSON stdin schema is shown above; JSON stdout includes the boolean result, explanatory reasons, normalized amount, and maximum limit. A nonzero exit means the input was malformed and must be corrected.
- `scripts/validate_dispute.py`: accepts a prospective filing payload on JSON stdin and returns a validity flag and validation errors on JSON stdout. It performs no bank action.
