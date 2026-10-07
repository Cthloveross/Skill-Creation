---
name: credit-card-transaction-dispute
version: 1.0.0
description: File one formal dispute per affected credit-card transaction, retrieve card last-four digits and dispute history with discoverable tools, and determine provisional-credit eligibility from account, transaction, and customer facts. Use for unauthorized charges, duplicates, billing errors, fulfillment issues, subscriptions, and missing refunds.
---

# Credit Card Transaction Dispute

Use this Skill when a customer wants to formally dispute one or more credit-card transactions. A separate filing is required for each transaction; do not combine charges from different transactions or cards.

## Required banking actions

1. Identify the authenticated customer and obtain their registered `user_id`, full name, phone, email, and address. Follow the runtime's identity-verification policy before performing account-specific actions. If the policy requires confirmed identity fields, ask the customer to confirm two fields without unnecessarily exposing them, then call `log_verification` with the complete registered record and a current timestamp.
2. Retrieve the customer's credit-card accounts and transaction history. Match each requested dispute to exactly one transaction using card type plus merchant, date, and amount. If a match is ambiguous or absent, stop and clarify rather than guessing a transaction ID.
3. When the card last four digits are unavailable, do not require the customer to reveal a full card number. Unlock and call the discoverable `get_card_last_4_digits` tool for the matched credit-card account ID. Its argument JSON is `{"credit_card_account_id":"<account id>"}`. Use the returned last four digits only for filings on that card.
4. Obtain the customer’s prior credit-card dispute history: unlock `get_user_dispute_history_7291` if needed, then call it for the `user_id`. Count disputes filed in the twelve months ending on the filing/reference date. Treat an empty history as zero. If the history is unavailable or incomplete after an appropriate retry, do not assert eligibility based on an assumed count; resolve the tool issue or explain that eligibility cannot yet be determined.
5. For every transaction, collect or derive all filing fields below. Ask only for missing facts. A customer saying they noticed the issue “today” may use the current date obtained through `get_current_time`, formatted `MM/DD/YYYY`.
6. Determine provisional-credit eligibility independently for each filing. You may run `scripts/evaluate_provisional_credit.py` to make this calculation reproducible.
7. Unlock `file_credit_card_transaction_dispute_4829`, then call it once per complete dispute using `call_discoverable_agent_tool`. The `arguments` field must be a JSON string containing the required filing payload. Report each successful result clearly to the customer. Do not say a filing was submitted unless the tool reports success.

## Filing payload

Every tool call must include these exact keys:

```json
{
  "transaction_id": "string",
  "card_action": "keep_active | cancel_and_reissue",
  "card_last_4_digits": "four digit string",
  "full_name": "registered full name",
  "user_id": "registered user ID",
  "phone": "registered phone",
  "email": "registered email",
  "address": "registered address",
  "contacted_merchant": true,
  "purchase_date": "MM/DD/YYYY",
  "issue_noticed_date": "MM/DD/YYYY",
  "dispute_reason": "allowed reason code",
  "resolution_requested": "full_refund | partial_refund | reversal_of_charge",
  "eligible_for_provisional_credit": false
}
```

Add `"partial_refund_amount": <number>` only when `resolution_requested` is `partial_refund`. It is required in that case and must be the requested dollar amount. Do not send it for a full refund or reversal.

Allowed `dispute_reason` values are:

- `unauthorized_fraudulent_charge`
- `duplicate_charge`
- `incorrect_amount`
- `goods_services_not_received`
- `goods_services_not_as_described`
- `canceled_subscription_still_charging`
- `refund_never_processed`

Map the customer's requested outcome carefully: a request to reverse/reverse in full/a chargeback maps to `reversal_of_charge`; a request for a complete refund maps to `full_refund`; a requested dollar portion maps to `partial_refund`. If wording is genuinely unclear, ask which of these three outcomes they want.

Set `card_action` to `keep_active` only when the customer wishes to continue using that card. Set `cancel_and_reissue` when they want a replacement or the card will be cancelled as part of the dispute. Never silently cancel a card because a charge is fraudulent.

`contacted_merchant` records the factual answer. It is normally `false` for a fraud claim if no merchant contact occurred; fraud does not require merchant contact for eligibility. For every non-fraud claim, explicitly ask whether they tried to resolve it with the merchant if that fact has not already been supplied.

## Provisional-credit rules

The customer is eligible only if **all** conditions hold:

- the card account has been open at least 60 days on the reference/filing date;
- reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`;
- for `goods_services_not_received`, the purchase is more than 30 days old;
- transaction amount is at least $25.00 and no more than the card’s tier limit;
- the customer has filed no more than two disputes in the preceding 12 months; and
- for a non-fraud claim, the customer contacted the merchant.

Tier limits are $2,500 for Entry, $5,000 for Mid, $10,000 for Premium (Gold Rewards Card and Business Gold Rewards Card), $15,000 for Elite, and $25,000 for Invitation. The explicitly ineligible reasons are `incorrect_amount`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, and `refund_never_processed`.

Pass `eligible_for_provisional_credit: false` whenever any condition fails. The eligibility value is an internal filing determination, not a promise that the dispute will be decided in the customer’s favor.

## Missing information and failures

- Ask for an exact notice date if “today” cannot be resolved using the current-time tool.
- If an account, transaction, or last-four lookup fails, do not substitute an account ID, transaction ID, or guessed card digits. Retry only when appropriate, then explain what is needed.
- If the requested reason or resolution is outside the allowed values, ask the customer to choose an allowed category.
- If a partial-refund amount is absent, do not file that item until it is supplied.
- A customer can still file a dispute even when provisional credit is unavailable; send the filing with `eligible_for_provisional_credit: false` once all required filing information is present.
- If one of several requested disputes lacks information, file the complete independent disputes and keep the incomplete item pending, provided doing so matches customer intent and runtime policy.

## Eligibility helper

`scripts/evaluate_provisional_credit.py` reads one JSON object from standard input and emits a JSON result. It performs only the policy calculation; it does not look up records or submit bank actions.

Input schema:

```json
{
  "account_open_date": "MM/DD/YYYY",
  "reference_date": "MM/DD/YYYY",
  "purchase_date": "MM/DD/YYYY",
  "dispute_reason": "reason code",
  "transaction_amount": 0.0,
  "card_type": "Gold Rewards Card",
  "prior_disputes_last_12_months": 0,
  "contacted_merchant": true
}
```

Example runnable call (with runtime-supplied values, not fixed customer data):

```sh
printf '%s' '<JSON object matching the schema>' | python3 scripts/evaluate_provisional_credit.py
```

Validate the result before using it: `eligible` is a boolean and `failed_conditions` is an empty array exactly when `eligible` is true. Preserve the returned failed conditions in internal reasoning or customer-safe explanation, but submit only the boolean in the bank filing payload.
