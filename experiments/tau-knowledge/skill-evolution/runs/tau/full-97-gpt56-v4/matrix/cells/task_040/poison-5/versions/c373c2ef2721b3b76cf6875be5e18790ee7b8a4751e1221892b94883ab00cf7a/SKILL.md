---
name: credit-card-transaction-dispute
version: 1.0.0
description: File one or more credit-card transaction disputes after identity verification, transaction/account matching, required-detail collection, and a documented provisional-credit eligibility assessment. Use when a customer reports fraudulent, duplicate, billing, merchandise, subscription, or refund problems on a Rho-Bank credit card.
---

# Credit-Card Transaction Dispute

Use this Skill to safely prepare and file a separate dispute for each affected transaction. Do not combine several transactions into one filing and do not guess missing required values.

## Required sources and tools

Use the normal banking tools to locate the customer, cards, and transactions. The following discovered agent tools must be unlocked before use:

- `get_card_last_4_digits` — call with each matched `credit_card_account_id` to retrieve its last four digits.
- `get_user_dispute_history_7291` — call with the canonical `user_id` to assess the prior-disputes condition.
- `file_credit_card_transaction_dispute_4829` — use only after the individual filing has passed validation.

Unlock a discovered tool with `unlock_discoverable_agent_tool`, then invoke it through `call_discoverable_agent_tool` with a JSON-string `arguments` value. Tool recommendations in this Skill do not themselves perform bank actions.

## Workflow

1. **Verify identity before account-specific action.** Obtain and match any two of date of birth, registered email, registered phone number, and registered address against the selected customer profile. Obtain the current timestamp and call `log_verification` with all profile fields and that timestamp. Do not treat information merely retrieved from the profile as customer confirmation.
2. **Find and confirm targets.** Use the verified `user_id` to retrieve credit-card accounts and transactions. Match each reported item by card type, merchant, amount/date where available, and the customer’s description. If more than one transaction is plausible, ask the customer which specific transaction to dispute; do not select one based only on merchant name.
3. **Recover card digits instead of requiring the customer to supply them.** For every selected account, unlock/call `get_card_last_4_digits` using the account ID. Keep the returned digit string attached only to filings for that account.
4. **Collect filing facts for every transaction.** Record the customer’s explicit answer for merchant contact, issue-noticed date, permitted reason, requested resolution, and an exact partial-refund amount when applicable. A customer saying they noticed an issue “today” may be recorded as the date returned by the current-time tool. Use the transaction record’s date as `purchase_date` in `MM/DD/YYYY` form. Set `card_action` to `keep_active` only when the customer wants to retain that card; set `cancel_and_reissue` only when cancellation/replacement is requested or has been ordered.
5. **Assess provisional credit independently for each filing.** Retrieve dispute history and use `scripts/dispute_assessment.py` in `evaluate` mode. All criteria must be proven true; unavailable account tier, account-open date, transaction amount, merchant-contact answer, or history makes the eligibility result `false`, not assumed true.
6. **Validate, then file.** Assemble the exact filing payload, run the same script in `validate_payload` mode, and correct all reported errors. Unlock the filing tool and call it once for each valid complete payload. Preserve the tool response and tell the customer which disputes were submitted and which remain blocked.

## Filing payload

The agent tool requires these fields for each transaction:

- `transaction_id` (string)
- `card_action`: `keep_active` or `cancel_and_reissue`
- `card_last_4_digits` (four-digit string)
- `full_name`, `user_id`, `phone`, `email`, `address`
- `contacted_merchant` (boolean)
- `purchase_date`, `issue_noticed_date` (`MM/DD/YYYY`)
- `dispute_reason`, exactly one of: `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, `refund_never_processed`
- `resolution_requested`, exactly one of: `full_refund`, `partial_refund`, `reversal_of_charge`
- `partial_refund_amount` (number, required only for `partial_refund`)
- `eligible_for_provisional_credit` (boolean)

Do not submit a partial-refund filing without an exact amount. Do not invent a promised refund, infer a duplicate’s transaction identity, or convert a vague desired resolution into a different permitted value without customer confirmation.

## Provisional-credit rules

The customer is eligible only if all conditions hold: the card account has been open at least 60 days; the reason is fraud, duplicate charge, or goods/services not received; amount is at least $25 and does not exceed the tier limit; no more than two disputes were filed in the preceding 12 months; and, for every non-fraud reason, the customer contacted the merchant. For goods/services not received, the purchase also must be more than 30 days old.

Limits are $2,500 for Bronze Rewards Card, EcoCard, Business Bronze Rewards Card, and Crypto-Cash Back Card; $5,000 for Silver Rewards Card, Business Silver Rewards Card, Green Rewards Card, and Silver Zoom Card; $10,000 for Gold Rewards Card and Business Gold Rewards Card; $15,000 for Platinum Rewards Card and Business Platinum Rewards Card; and $25,000 for Diamond Elite Card.

## Script interface and validation

`scripts/dispute_assessment.py` reads exactly one JSON object from stdin and emits exactly one JSON object to stdout. It uses only the Python standard library.

- `{"mode":"evaluate", "as_of":"MM/DD/YYYY", "account":{"card_type":"...","date_of_account_open":"MM/DD/YYYY"}, "transaction":{"amount":"...","purchase_date":"MM/DD/YYYY"}, "dispute":{"reason":"...","contacted_merchant":true,"history":[{"dispute_date":"MM/DD/YYYY"}]}}` returns `eligible`, a list of failed `reasons`, and calculations.
- `{"mode":"validate_payload", "payload":{...}}` returns `ok`, `errors`, and `normalized_payload`. Use the normalized payload only when `ok` is true.

A runnable invocation is `python3 scripts/dispute_assessment.py < input.json`. Before calling the filing tool, require `ok: true`, ensure the assessment boolean is copied into `eligible_for_provisional_credit`, and ensure every date sent to the tool is formatted `MM/DD/YYYY`.

## Incomplete or failed cases

If a required value cannot be recovered from authorized records or obtained from the customer, clearly name the blocked transaction and missing field, submit no malformed filing for it, and continue with other complete independent disputes. If account/transaction lookup is ambiguous, ask a targeted clarification. If a normal or discovered tool fails, report the failure, do not claim a filing succeeded, and avoid retrying any action whose outcome is reported as unknown. Transfer only when a supported transfer reason applies; a missing amount or matching transaction normally requires clarification rather than transfer.
