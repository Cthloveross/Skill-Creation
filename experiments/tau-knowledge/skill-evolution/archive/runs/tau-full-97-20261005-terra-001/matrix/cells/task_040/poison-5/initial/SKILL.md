---
name: credit-card-transaction-dispute-filing
description: Prepare, determine provisional-credit eligibility for, and file one or more complete credit-card transaction disputes. Use when a customer identifies disputed credit-card charges and the agent must submit each dispute through file_credit_card_transaction_dispute_4829.
---

# Credit Card Transaction Dispute Filing

Use this Skill to safely turn one or more customer-reported credit-card problems into separate, complete dispute submissions. It supports fraud, duplicate charges, incorrect amounts, merchandise/service issues, continuing subscription charges, and missing refunds.

## Required runtime information

Obtain or confirm the following for **each** disputed transaction before filing:

- Transaction ID, matched to the customer's card, merchant, amount, and purchase date in transaction history.
- The relevant card's last four digits. If unavailable, retrieve them with `get_card_last_4_digits` using that card's account ID.
- Customer `full_name`, `user_id`, registered `phone`, `email`, and `address`.
- Whether the customer contacted the merchant. This is required even for fraud (normally `false` for fraud when the customer did not contact the merchant).
- Date the issue was noticed, in `MM/DD/YYYY`. If the customer says “today,” obtain the current date from the runtime and use it.
- One exact dispute reason:
  - `unauthorized_fraudulent_charge`
  - `duplicate_charge`
  - `incorrect_amount`
  - `goods_services_not_received`
  - `goods_services_not_as_described`
  - `canceled_subscription_still_charging`
  - `refund_never_processed`
- One exact resolution: `full_refund`, `partial_refund`, or `reversal_of_charge`.
- A positive numeric `partial_refund_amount` if, and only if, the requested resolution is `partial_refund`. Do not guess an amount described only as a promised or expected partial refund.
- Card action: `keep_active` if the customer wants to retain the card, or `cancel_and_reissue` only when the customer wants the card cancelled and replaced (including when a replacement has already been ordered).

A card number's last four digits are required submission data. Do not substitute an account ID, card type, or a guessed value.

## Read-only preparation workflow

1. Locate the customer and their credit-card accounts through normal read-only banking tools. Match every reported charge to a transaction record; do not file from merchant/date/amount descriptions alone where the match is ambiguous.
2. For every affected card whose last four digits are not already known, unlock and call the discovered agent tool `get_card_last_4_digits` with JSON arguments `{"credit_card_account_id":"<account-id>"}`. Use its returned last four digits only for that account's disputes.
3. Retrieve the customer's prior dispute records using `get_user_dispute_history_7291` with `{"user_id":"<user-id>"}`. In runtimes where it is a discoverable agent tool, unlock it before calling it. An empty result is a valid history; an unavailable, malformed, or partial result is not sufficient to determine eligibility.
4. Obtain the current date from the runtime. Use it for “today” issue-noticed dates and as the eligibility evaluation date.
5. Build one record per transaction and run `scripts/prepare_disputes.py`. The script validates tool fields and computes the required provisional-credit boolean. It produces ready submissions separately from blocked records.

## Provisional-credit decision

Set `eligible_for_provisional_credit` to true only if **all** are true:

1. The card account has been open at least 60 days.
2. The reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`.
3. For `goods_services_not_received`, the purchase was more than 30 days before the evaluation date.
4. The full disputed transaction amount is at least $25.00 and no greater than the applicable tier maximum.
5. The customer has filed no more than two disputes in the preceding 12 months, according to the retrieved history.
6. For every non-fraud reason, the customer contacted the merchant first.

Tier maxima are $2,500 (Entry), $5,000 (Mid), $10,000 (Premium), $15,000 (Elite), and $25,000 (Invitation). Gold Rewards Card and Business Gold Rewards Card are Premium. The helper contains the documented card-name mapping. The amount used for this decision is the transaction's amount, not a requested partial-refund amount.

Reasons outside the three listed eligible categories always receive `false`. An ineligible dispute may still be filed; provisional credit is simply false. Missing data that prevents a required tool argument or eligibility decision blocks that dispute until resolved.

## Helper interface

Run:

```text
python3 scripts/prepare_disputes.py < input.json
```

The script reads one JSON object from stdin and writes one JSON object to stdout. Input schema:

```json
{
  "as_of_date": "MM/DD/YYYY",
  "customer": {
    "full_name": "string",
    "user_id": "string",
    "phone": "string",
    "email": "string",
    "address": "string"
  },
  "card_action": "keep_active | cancel_and_reissue",
  "accounts": [
    {
      "account_id": "string",
      "card_type": "documented card type",
      "date_of_account_open": "MM/DD/YYYY",
      "card_last_4_digits": "four digits"
    }
  ],
  "dispute_history": [{"dispute_date": "date or timestamp"}],
  "disputes": [
    {
      "transaction_id": "string",
      "account_id": "string",
      "transaction_amount": 0,
      "purchase_date": "MM/DD/YYYY",
      "issue_noticed_date": "MM/DD/YYYY",
      "dispute_reason": "allowed reason",
      "resolution_requested": "allowed resolution",
      "partial_refund_amount": 0,
      "contacted_merchant": true
    }
  ]
}
```

`partial_refund_amount` must be omitted for non-partial resolutions. `dispute_history` must be present, including when it is an empty array. The output contains `ready_submissions`, whose elements are exactly the argument objects for the filing tool, plus `blocked` and `errors`. Only call the filing tool for entries in `ready_submissions`.

## Filing workflow

1. Resolve any `blocked` records. Ask focused follow-up questions for missing customer choices or amounts; re-query runtime records for unavailable transaction, account, last-four, or history data.
2. Unlock `file_credit_card_transaction_dispute_4829` using `unlock_discoverable_agent_tool` with `agent_tool_name` set to that exact tool name.
3. For each ready submission, call `call_discoverable_agent_tool` with `agent_tool_name` set to `file_credit_card_transaction_dispute_4829` and `arguments` set to a JSON string of that submission object.
4. Treat each disputed transaction as a separate filing. Record the result returned for each call and clearly report which filings succeeded or failed. Do not claim a filing succeeded unless the tool confirms it.

Do not cancel or replace a card merely because a transaction is fraud-related. Respect the customer's selected `card_action`; a replacement order is a separate workflow and must meet its own requirements.

## Validation expectations

Before any filing call, verify that each argument object has all required fields, uses allowed enums, has four numeric last digits, has dates formatted `MM/DD/YYYY`, and includes a partial amount exactly when partial refund is requested. The helper enforces these checks, confirms an account match, and reports the specific blocking fields rather than emitting an incomplete tool call.
