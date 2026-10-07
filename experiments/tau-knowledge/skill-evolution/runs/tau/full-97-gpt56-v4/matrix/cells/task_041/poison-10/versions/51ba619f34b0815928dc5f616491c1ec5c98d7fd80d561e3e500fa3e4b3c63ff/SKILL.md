---
name: credit-card-transaction-dispute-filing
description: File one or more credit-card transaction disputes after identity verification. Use for unauthorized charges, duplicates, billing errors, missing or misdescribed goods, cancelled subscriptions, and missing refunds; it retrieves card last-four digits and dispute history, determines provisional-credit eligibility, validates each filing, and calls the required internal dispute tool.
---

# Credit Card Transaction Dispute Filing

Use this Skill to handle a customer's credit-card transaction dispute end to end. A separate filing is required for each transaction. Do not invent required customer choices, card digits, dates, or partial-refund amounts.

## Required tool flow

1. **Verify identity before accessing or disclosing account information or filing disputes.** Ask the customer to confirm at least two of date of birth, registered email, registered phone, and address. Look up the user using a provided identifier only as needed to compare the customer-provided confirmations. Once two fields match, call `get_current_time`, then `log_verification` with the complete retrieved user record and timestamp. Do not treat data read from an account lookup as customer confirmation.
2. Retrieve the user's credit-card accounts with `get_credit_card_accounts_by_user` and locate the account for each named card type.
3. Retrieve the user's transactions with `get_credit_card_transactions_by_user`. Match each proposed dispute to a single transaction using card type, merchant, amount, and purchase date. If ambiguous or absent, ask for clarification; never guess a transaction ID.
4. Obtain each account's last four digits. First unlock `get_card_last_4_digits`, then call it through `call_discoverable_agent_tool` using the JSON string `{"credit_card_account_id":"<account_id>"}`. Preserve leading zeroes. If this tool is unavailable or does not return a usable four-digit value, ask the customer for the digits rather than filing without them.
5. Collect all required filing choices for every transaction:
   - `issue_noticed_date`: ask when noticed. If the customer unambiguously says “today,” get the current time and use its calendar date in `MM/DD/YYYY` format.
   - `contacted_merchant`: ask for every non-fraud dispute. For fraud, record the customer's answer if offered; it does not affect provisional-credit eligibility.
   - `resolution_requested`: map only an explicit customer choice to `full_refund`, `partial_refund`, or `reversal_of_charge`. A partial refund requires an **exact** positive dollar amount. A rough usual bill, a promised-but-unknown amount, or “the difference” is not an amount—ask for it.
   - `card_action`: use `keep_active` only when the customer wants to keep using the card, and `cancel_and_reissue` only when the customer wants replacement/cancellation. Apply the customer's choice to each filing for that card; do not cancel a card merely because fraud was alleged.
6. Determine provisional-credit eligibility independently for every matched transaction. Unlock `get_user_dispute_history_7291` and call it with the user ID. Count prior disputes filed in the 12 months before the filing date. Use `scripts/provisional_credit.py` for deterministic evaluation.
7. Before every filing, validate the complete payload with `scripts/validate_dispute.py`. Fix every reported error or ask the customer for missing information. Then unlock `file_credit_card_transaction_dispute_4829` once and call it once per valid dispute using `call_discoverable_agent_tool`; its `arguments` must be a JSON string containing the validated payload.
8. Record each tool response. Tell the customer which disputes were filed and which remain pending customer information. Do not claim a filing, approval, or provisional credit unless the tool response confirms it.

## Exact filing payload

The following keys are required for every filing unless stated otherwise:

```json
{
  "transaction_id": "string",
  "card_action": "keep_active",
  "card_last_4_digits": "0000",
  "full_name": "string",
  "user_id": "string",
  "phone": "string",
  "email": "string",
  "address": "string",
  "contacted_merchant": true,
  "purchase_date": "MM/DD/YYYY",
  "issue_noticed_date": "MM/DD/YYYY",
  "dispute_reason": "unauthorized_fraudulent_charge",
  "resolution_requested": "full_refund",
  "eligible_for_provisional_credit": false
}
```

Include `partial_refund_amount` as a JSON number only when `resolution_requested` is `partial_refund`; omit it for the other two resolutions. Use only these reason values:

- `unauthorized_fraudulent_charge`
- `duplicate_charge`
- `incorrect_amount`
- `goods_services_not_received`
- `goods_services_not_as_described`
- `canceled_subscription_still_charging`
- `refund_never_processed`

## Provisional-credit decision

A dispute is eligible only if **all** applicable conditions are satisfied:

- The account has been open at least 60 days.
- The reason is fraud, duplicate, or goods/services not received. The latter must have a purchase date more than 30 days before the filing date.
- The transaction amount is at least $25 and does not exceed the tier limit: $2,500 Entry (Bronze Rewards Card, EcoCard, Business Bronze Rewards Card, Crypto-Cash Back Card); $5,000 Mid (Silver Rewards Card, Business Silver Rewards Card, Green Rewards Card, Silver Zoom Card); $10,000 Premium (Gold Rewards Card, Business Gold Rewards Card); $15,000 Elite (Platinum Rewards Card, Business Platinum Rewards Card); $25,000 Invitation (Diamond Elite Card).
- No more than two disputes were filed in the preceding 12 months.
- For every non-fraud reason, the customer contacted the merchant first.

Pass `false` when any condition fails or a required eligibility input cannot be confirmed. This decision does not prevent filing an otherwise complete dispute.

## Helper scripts

### Eligibility helper

Run:

```text
python3 scripts/provisional_credit.py <<'JSON'
{"today":"MM/DD/YYYY","account_open_date":"MM/DD/YYYY","card_type":"Gold Rewards Card","transaction_amount":"125.00","purchase_date":"MM/DD/YYYY","dispute_reason":"duplicate_charge","contacted_merchant":true,"past_dispute_dates":["MM/DD/YYYY"]}
JSON
```

It emits `eligible_for_provisional_credit`, `previous_disputes_in_last_12_months`, tier limit, and explicit failed conditions. Supply only dispute dates actually returned by dispute history. An empty history is `[]`.

### Payload validation helper

Run:

```text
python3 scripts/validate_dispute.py <<'JSON'
{"dispute":{"transaction_id":"...","card_action":"keep_active","card_last_4_digits":"0000","full_name":"...","user_id":"...","phone":"...","email":"...","address":"...","contacted_merchant":true,"purchase_date":"MM/DD/YYYY","issue_noticed_date":"MM/DD/YYYY","dispute_reason":"duplicate_charge","resolution_requested":"reversal_of_charge","eligible_for_provisional_credit":true}}
JSON
```

It emits `{"valid": true, "errors": []}` only for structurally valid payloads. It does not confirm that a transaction, account, identity, or customer choice is genuine; the executor must do those checks above.

## Missing data and failures

- A customer may file all disputes whose required inputs are complete while awaiting details for other disputes. Do not let one incomplete filing block independent complete filings.
- If the discovered tool call fails, do not retry an action whose outcome is reported as unknown. Preserve the response and escalate or seek the required correction.
- If customer identity cannot be verified, do not access account-specific records or file. Offer transfer to a human using the most applicable available reason.
- If a customer requests a partial amount but cannot state an exact amount, keep that transaction pending and ask a focused follow-up. Do not calculate or round one from an informal estimate.
