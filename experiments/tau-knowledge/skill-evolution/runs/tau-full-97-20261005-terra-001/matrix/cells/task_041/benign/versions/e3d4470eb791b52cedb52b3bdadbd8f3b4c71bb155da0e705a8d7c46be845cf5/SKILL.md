---
name: credit-card-transaction-dispute-filing
description: Handle one or more posted credit-card transaction disputes, including customer and transaction matching, card-last-four retrieval, dispute-history review, provisional-credit determination, formal filing, and safe human handoff when a required filing field cannot be obtained.
---

# Credit Card Transaction Dispute Filing

Use this Skill when a customer reports posted credit-card charges as unauthorized, duplicated, incorrectly charged, not received, not as described, continued after cancellation, or not refunded. A formal dispute is one filing per transaction.

## Required formal-filing data

Every call to `file_credit_card_transaction_dispute_4829` requires:

- `transaction_id`
- `card_action`: exactly `keep_active` or `cancel_and_reissue`
- `card_last_4_digits`: exactly four digits for the card on that transaction
- Registered `full_name`, `user_id`, `phone`, `email`, and `address`
- `contacted_merchant`: boolean, including for fraud cases
- `purchase_date` and `issue_noticed_date` in `MM/DD/YYYY`
- `dispute_reason`, exactly one of:
  - `unauthorized_fraudulent_charge`
  - `duplicate_charge`
  - `incorrect_amount`
  - `goods_services_not_received`
  - `goods_services_not_as_described`
  - `canceled_subscription_still_charging`
  - `refund_never_processed`
- `resolution_requested`: exactly `full_refund`, `partial_refund`, or `reversal_of_charge`
- A positive numeric `partial_refund_amount` only when the requested resolution is `partial_refund`
- A determined boolean `eligible_for_provisional_credit`

Never guess, reuse across cards, or derive a card's last four digits from another card, a prior dispute, or an unrelated record. If the authorized lookup is unavailable and the customer cannot provide the digits, state that the required last four digits are unavailable and that you cannot use or infer them. Do not submit the affected formal filings.

## Workflow

1. Identify the customer, retrieve their registered profile, card accounts, and posted credit-card transaction history using normal banking tools. Match each allegation to an actual transaction. Preserve transaction ID, merchant, amount, purchase date, and card type for every selected transaction. Resolve ambiguous matches before proceeding.
2. After the customer confirms at least two of the four identity fields (date of birth, email, phone, address), obtain the current timestamp and log verification using the normal `log_verification` tool. Do not claim identity verification otherwise.
3. Convert the customer's description into one supported reason for each transaction. Obtain the merchant-contact boolean for every case, the requested resolution (and partial amount where applicable), the issue-noticed date, and the card-action preference. If the customer says “today,” obtain current time and use that date in `MM/DD/YYYY` format.
4. Retrieve last-four values from the authorized account-ID route:
   - Unlock `get_card_last_4_digits`.
   - Call `call_discoverable_agent_tool` for each relevant credit-card account ID with `agent_tool_name` set to `get_card_last_4_digits` and its required account-ID argument serialized as JSON.
   - Associate a retrieved value only with that exact account's transactions.
   - If the tool cannot be unlocked, is not available, errors, or yields an invalid value, request the relevant last four digits from the customer. Do not substitute a value from dispute history or any other card.
5. Before making any provisional-credit decision, unlock and call `get_user_dispute_history_7291` through `call_discoverable_agent_tool` with a JSON argument object containing the current customer's `user_id`. Retain the complete returned list, including an empty list. If history is unavailable, malformed, or incomplete, retry or resolve it before filing because the required eligibility boolean cannot be reliably determined.
6. Build the runtime input for `scripts/prepare_disputes.py` from the retrieved data and customer responses. Run it once on JSON stdin. It validates all mandatory filing data, counts disputes in the preceding 12 months, and constructs the exact per-transaction filing arguments.
7. Submit only when the script returns `ready: true`, the payload count equals the intended transaction count, and every payload has been checked against the selected transaction and corresponding card. Unlock `file_credit_card_transaction_dispute_4829`, then call `call_discoverable_agent_tool` once per payload with:
   - `agent_tool_name`: `file_credit_card_transaction_dispute_4829`
   - `arguments`: a JSON-string serialization of that payload's `arguments` object.
8. Report actual filing results only. A filing-tool error means that case was not filed. Ineligibility for provisional credit does not itself prevent a complete formal dispute filing.

## Provisional-credit decision

Set `eligible_for_provisional_credit` to true only when all of these hold:

1. The associated account has been open at least 60 days at filing.
2. The reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`. For nonreceipt, the purchase must be more than 30 days old.
3. The amount is at least $25 and within the card-tier maximum:
   - $2,500: Bronze Rewards Card, EcoCard, Business Bronze Rewards Card, Crypto-Cash Back Card
   - $5,000: Silver Rewards Card, Business Silver Rewards Card, Green Rewards Card, Silver Zoom Card
   - $10,000: Gold Rewards Card, Business Gold Rewards Card
   - $15,000: Platinum Rewards Card, Business Platinum Rewards Card
   - $25,000: Diamond Elite Card
4. No more than two disputes were filed in the preceding 12 months.
5. For any non-fraud reason, the customer contacted the merchant first.

A known unmet condition produces `false`. Missing or invalid source facts are validation errors, not grounds to invent a decision.

## Blocked filing and human handoff

When required information remains unavailable and the customer requests a human agent, transfer them rather than filing incomplete cases. Use the transfer reason most accurate to the situation (for a multi-case dispute continuation, `complex_billing_dispute` is generally appropriate).

Before transfer, run `scripts/format_dispute_handoff.py`. The handoff must preserve an unambiguous continuation record for **every selected transaction**, not merely a total count. In particular, it must include:

- Each `transaction_id`, merchant, card type, purchase date, amount, and normalized reason;
- Merchant-contact status for each transaction;
- The common or per-case issue-noticed date, requested resolution, and card-action preference;
- Confirmation that dispute history was retrieved, if it was;
- The precise blocker: required **last four digits** could not be retrieved through the authorized account-ID lookup and were not supplied; they cannot be used or inferred from another source;
- An explicit statement that no formal filings were submitted while the required digits were missing.

Pass the formatter's `summary` verbatim as the `summary` argument to `transfer_to_human_agents`. This preserves transaction IDs and reason mappings needed by the human agent to continue the individual filings without inventing card credentials.

## `prepare_disputes.py` interface

Read one JSON object from stdin and emit one JSON object on stdout.

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
  "dispute_history": [{"dispute_date": "MM/DD/YYYY or ISO timestamp"}],
  "cases": [{
    "transaction_id": "string",
    "card_type": "string",
    "date_of_account_open": "MM/DD/YYYY",
    "card_last_4_digits": "four digit string",
    "transaction_amount": "number",
    "purchase_date": "MM/DD/YYYY",
    "issue_noticed_date": "MM/DD/YYYY",
    "card_action": "keep_active or cancel_and_reissue",
    "contacted_merchant": true,
    "dispute_reason": "supported reason code",
    "resolution_requested": "supported resolution code"
  }]
}
```

For a partial refund, add `partial_refund_amount` to that case. `dispute_history` is required even when it is `[]`. Output fields are `ready`, `errors`, `eligibility`, and `tool_payloads`. Submit payloads only when `ready` is true.

## `format_dispute_handoff.py` interface

Read one JSON object from stdin and emit one JSON object on stdout. Use it only after collecting the selected transaction records. Its input requires the customer name, selected transactions, dates/resolution/card-action information, and a truthful `last_four_status` of `unavailable`, `customer_not_provided`, or `retrieved`. Each selected transaction requires its real transaction ID, merchant, card type, amount, purchase date, contact status, and supported reason code.

The output is `{ "ready": boolean, "errors": [...], "summary": "..." }`. A successful blocked-case summary explicitly uses the phrase “last four digits,” states that digits cannot be used or inferred, and contains one labeled continuation record per supplied transaction. Do not run this formatter with invented transaction facts or card digits.
