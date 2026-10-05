---
name: credit-card-recent-transaction-report
description: Retrieve and clearly present the available posted transaction history for one identified credit card, including dates, merchant descriptors, posted amounts, and an optional charge total. Use when a customer asks to see, review, or reconcile recent credit-card charges.
---

# Credit Card Recent Transaction Report

Use this Skill after the customer has identified the account holder and the necessary account/transaction records have been retrieved through the normal banking tools. It is read-only: do not initiate disputes, alter account data, or infer that a charge is unauthorized merely because the customer says a balance looks high.

## Required runtime inputs

Obtain current data rather than relying on remembered values:

1. Identify the customer from the information they provided.
2. Retrieve that customer's credit-card accounts.
3. Confirm that the requested card type identifies exactly one account. If there is no matching card or more than one matching account, ask a focused clarification rather than exposing other-card activity.
4. Retrieve that customer's credit-card transactions.

Do not expose account-holder contact details, full identity fields, or transactions for a card other than the requested card. Follow any separate runtime authentication requirements if applicable; this Skill does not invent an authentication policy.

## Produce the report

1. Filter transactions to the selected card type. For a standard statement-style report, show transactions with a posted/completed status. If the user also asks about pending activity, retrieve or label pending records separately; do not mix them into a posted total.
2. Do not impose an unstated definition of “recent.” If the retrieved relevant history is short, present all of it, newest first, and call it the available history. If it is long, present a clearly stated newest subset and offer a date range, merchant, or amount filter for the remainder. Honor an explicit date range or count request instead.
3. For every displayed transaction, include at least **date, merchant descriptor, and posted amount**. Include category and status when supplied, as useful context. Keep refunds/credits signed; do not silently omit them.
4. State the selected card and, when supplied by the account record, its current balance. A sum of listed transactions is only the net of the displayed rows and is not necessarily the current balance: payments, prior-period activity, pending activity, interest, fees, and credits can make them differ.
5. If a merchant is unfamiliar, invite the customer to review its date and descriptor before proceeding with a dispute. Do not characterize it as fraud or open a dispute unless the customer requests that next step.

Use `scripts/build_transaction_report.py` to perform card selection, status filtering, date ordering, currency-safe net-total calculation, and schema checks.

## Script interface

Run:

```text
python scripts/build_transaction_report.py < request.json
```

The script reads one JSON object from stdin and emits one JSON object to stdout. Supply live normalized records in this schema:

```text
{
  "accounts": [
    {"account_id": "...", "card_type": "...", "current_balance": "$..."}
  ],
  "transactions": [
    {
      "transaction_id": "...",
      "credit_card_type": "...",
      "merchant_name": "...",
      "transaction_amount": "$...",
      "transaction_date": "MM/DD/YYYY or YYYY-MM-DD",
      "status": "COMPLETED"
    }
  ],
  "card_type": "requested card type",
  "posted_only": true,
  "recent_count": null,
  "start_date": null,
  "end_date": null
}
```

`accounts`, `transactions`, and `card_type` are required. `posted_only` defaults to `true`; recognized posted statuses are `COMPLETED` and `POSTED`. `recent_count`, `start_date`, and `end_date` are optional. Dates are inclusive and accept `MM/DD/YYYY` or ISO date strings. Leave `recent_count` absent or null to return every matching available transaction.

A successful output has `ok: true`, one `account`, a newest-first `transactions` array, `displayed_net_total`, and counts. Format that output as a customer-facing table or readable list. Check before responding that every row has a valid date, nonempty merchant, and parseable amount, that every row matches the selected card, and that the displayed net total is clearly labeled as a total of displayed posted transactions. If `ok` is false, use its error to request clarification or re-query the source; do not fabricate a report.

The script intentionally does not calculate rewards or decide whether a balance is correct. Those are separate questions requiring the relevant account and statement information.
