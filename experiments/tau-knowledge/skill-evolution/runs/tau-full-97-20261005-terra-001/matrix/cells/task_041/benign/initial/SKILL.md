---
name: credit-card-transaction-dispute-filing
description: File one or more formal credit-card transaction disputes after identifying the customer and transactions, retrieving card last-four values and dispute history, determining provisional-credit eligibility, and submitting each complete case through the required discoverable tool.
---

# Credit Card Transaction Dispute Filing

Use this Skill when a customer wants to dispute posted credit-card transactions for fraud, duplicate billing, incorrect amounts, nonreceipt, not-as-described goods/services, continued subscription charges, or an unprocessed promised refund. Submit one filing per transaction.

## Required data

Each filing requires all of the following:

- `transaction_id`
- `card_action`: `keep_active` or `cancel_and_reissue`
- Four-digit `card_last_4_digits`
- Customer `full_name`, `user_id`, registered `phone`, `email`, and `address`
- `contacted_merchant` boolean
- `purchase_date` and `issue_noticed_date`, both `MM/DD/YYYY`
- One reason code:
  - `unauthorized_fraudulent_charge`
  - `duplicate_charge`
  - `incorrect_amount`
  - `goods_services_not_received`
  - `goods_services_not_as_described`
  - `canceled_subscription_still_charging`
  - `refund_never_processed`
- Requested resolution: `full_refund`, `partial_refund`, or `reversal_of_charge`. A numeric `partial_refund_amount` is required only for `partial_refund`.
- A determined boolean `eligible_for_provisional_credit`

Do not guess missing values, especially transaction IDs, card last four digits, merchant-contact status, dates, resolution, or card action. Ask the customer for information that cannot be retrieved or inferred from their explicit statement. If the customer says they noticed the issue “today,” obtain the current time and format its date as `MM/DD/YYYY`.

## Execution workflow

1. Identify the customer and retrieve their registered profile, card accounts, and transaction list using the normal banking tools. Match every alleged merchant/amount/date to an actual transaction and retain its `transaction_id`, amount, date, and card type. Resolve ambiguous matches with the customer.
2. If the customer has confirmed at least two identity fields, log verification using the normal verification procedure and the current timestamp. Do not claim a verification was logged if this condition is not met.
3. Obtain the card last four digits rather than requiring the customer to supply them when an account ID is available:
   - Unlock `get_card_last_4_digits`.
   - Call it through `call_discoverable_agent_tool` once for each relevant `credit_card_account_id`.
   - Use the returned four digits only for the matching card's transactions. If no account ID or result is available, request the last four digits; do not file that card's cases without it.
4. Unlock `get_user_dispute_history_7291` and call it through `call_discoverable_agent_tool` with `{"user_id":"..."}`. Preserve the returned list, including an empty list. A missing, malformed, or unavailable history result means provisional-credit eligibility cannot be determined; resolve/retry it before filing because the filing tool requires the boolean.
5. Gather or confirm merchant-contact status for every non-fraud case, requested resolution, partial amount when applicable, and card action. Fraud does not require merchant contact for eligibility, but the required `contacted_merchant` field must still be a boolean.
6. Create a runtime JSON input for `scripts/prepare_disputes.py` from the retrieved facts and customer responses. Run it once. It validates filing fields, calculates the 12-month dispute count, and produces per-transaction filing payloads with the required eligibility boolean.
7. If the script reports any errors, correct them first. Explain eligibility accurately if asked: provisional credit is temporary and may be reversed after investigation. Ineligibility does not itself prevent filing a dispute.
8. Unlock `file_credit_card_transaction_dispute_4829` before its first use. For every object in `tool_payloads`, call `call_discoverable_agent_tool` with:
   - `agent_tool_name`: `file_credit_card_transaction_dispute_4829`
   - `arguments`: a JSON string serialization of that object's `arguments` value.

Submit each transaction separately. Report the actual tool result for each filing and do not represent a case as filed when its call failed.

## Provisional-credit decision

Set `eligible_for_provisional_credit` to true only if **all** conditions hold:

1. The relevant card account was open at least 60 days as of filing.
2. Reason is fraud, duplicate charge, or goods/services not received. Nonreceipt additionally requires the purchase to be more than 30 days old.
3. Amount is at least $25 and no more than the card-tier cap:
   - $2,500: Bronze Rewards Card, EcoCard, Business Bronze Rewards Card, Crypto-Cash Back Card
   - $5,000: Silver Rewards Card, Business Silver Rewards Card, Green Rewards Card, Silver Zoom Card
   - $10,000: Gold Rewards Card, Business Gold Rewards Card
   - $15,000: Platinum Rewards Card, Business Platinum Rewards Card
   - $25,000: Diamond Elite Card
4. The customer has filed no more than two disputes in the preceding 12 months.
5. For non-fraud cases, the customer contacted the merchant first.

Reasons outside the three eligible categories are not eligible. An amount outside the range, unknown tier, missing decision input, or failed requirement yields false only when the relevant facts are known; missing required source data must instead be treated as a validation error so it can be resolved.

## Script interface

Run `scripts/prepare_disputes.py` with one JSON object on stdin. It emits one JSON object on stdout.

Input schema:

```json
{
  "current_date": "MM/DD/YYYY",
  "customer": {
    "full_name": "string",
    "user_id": "string",
    "phone": "string",
    "email": "string",
    "address": "string"
  },
  "dispute_history": [
    {"dispute_date": "MM/DD/YYYY or ISO timestamp"}
  ],
  "cases": [
    {
      "transaction_id": "string",
      "card_type": "string",
      "date_of_account_open": "MM/DD/YYYY",
      "card_last_4_digits": "1234",
      "transaction_amount": 100.0,
      "purchase_date": "MM/DD/YYYY",
      "issue_noticed_date": "MM/DD/YYYY",
      "card_action": "keep_active",
      "contacted_merchant": true,
      "dispute_reason": "duplicate_charge",
      "resolution_requested": "full_refund"
    }
  ]
}
```

For a partial refund, include `partial_refund_amount` as a positive number in that case. `dispute_history` must be supplied even when empty. The output contains `ready`, `errors`, `eligibility`, and `tool_payloads`. Only submit `tool_payloads` if `ready` is true. Validate that its payload count equals the number of intended transactions and that every payload has the correct transaction ID, card digits, dates, action, reason, resolution, and provisional-credit boolean before calling the filing tool.
