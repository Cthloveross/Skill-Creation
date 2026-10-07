---
name: recent-credit-card-transactions
description: Retrieve and present a cardholder's recent posted transactions for one specified credit-card product, with accurate date, merchant, amount, category, and a total for a clearly stated reporting window. Use when a customer asks to review recent charges, reconcile a card balance, or inspect statement activity.
---

# Recent Credit-Card Transaction Review

Use this skill to give a customer a concise, account-specific view of posted activity on the requested card. It is read-only: do not dispute, modify, tag, export, or transfer anything merely because the customer asks to see transactions.

## Required inputs and prerequisites

1. Identify the customer using the identifier they provide and use the normal customer-service authentication process required by the active environment. Do not expose unrelated account or transaction data.
2. Obtain the customer's card accounts and select the account whose `card_type` exactly matches the requested product. If zero or multiple accounts match, explain the ambiguity and ask for clarification rather than guessing.
3. Retrieve that customer's transaction history. Use only records belonging to the selected card type.
4. Use posted activity only. In the supplied transaction service, treat `COMPLETED` and `POSTED` as posted statuses. Exclude `PENDING`, declined, and otherwise non-posted records. Include posted refunds or credits if present, since they can explain a balance difference.

The available read-only tools normally support the retrieval sequence:

- `get_user_information_by_name` or `get_user_information_by_email`
- `get_credit_card_accounts_by_user`
- `get_credit_card_transactions_by_user`

If the current interaction already contains successful read-only observations, reuse those results instead of making redundant calls. Account lookup is essential because transaction history is returned for all of a user's cards.

## Choosing “recent”

If the customer does not specify dates, use the trailing 30 calendar days ending on the current date, state that exact date range, and offer to show a different statement period. Get the current date from the runtime when it is not already supplied. If the customer supplies dates or asks for a statement month, use that requested inclusive period instead.

Do not claim that the resulting total equals the current balance: a balance can include older statement activity, payments, fees, credits, or transactions outside the chosen window.

## Formatting the response

Present a clear heading naming the requested card and reporting window. List records newest first, with at least:

- posted date,
- merchant descriptor,
- posted amount,
- category when returned by the service.

State the number of posted records and the net activity total. Label negative amounts as credits/refunds rather than charges. Do not include full account numbers, irrelevant personal profile fields, or other cards' activity. If no qualifying records are found, say so and give the window used. If a record is unfamiliar, invite the customer to review its date and merchant descriptor before deciding whether to dispute it.

## Deterministic formatter

Use `scripts/format_recent_transactions.py` after converting the tool results into the structured input below. The script filters one card, validates the requested window, orders transactions, calculates the net total exactly to cents, and produces a ready-to-send plain-text summary.

### Script input (JSON on stdin)

```json
{
  "card_type": "requested card product",
  "as_of": "YYYY-MM-DD or a timestamp containing YYYY-MM-DD",
  "transactions": [
    {
      "credit_card_type": "card product",
      "transaction_date": "MM/DD/YYYY or YYYY-MM-DD",
      "merchant_name": "merchant descriptor",
      "transaction_amount": "$12.34",
      "category": "optional category",
      "status": "COMPLETED"
    }
  ],
  "lookback_days": 30,
  "start_date": "optional YYYY-MM-DD",
  "end_date": "optional YYYY-MM-DD",
  "current_balance": "optional displayed balance",
  "limit": 25
}
```

`as_of` is required when neither `end_date` nor a requested explicit date range is supplied. An explicit range must provide both `start_date` and `end_date`; it overrides `lookback_days`. `lookback_days` defaults to 30 and `limit` defaults to 25. Dates are inclusive. `transactions` must be structured records, not the unparsed display text of a tool response.

### Script output (JSON on stdout)

On success the result has `ok: true`, `window`, `transaction_count`, `net_total`, `transactions`, `truncated`, and `response_text`. `response_text` is the customer-safe summary. On malformed input, impossible date ranges, or missing required transaction fields, it returns `ok: false` and an `error` message; correct the retrieval/extraction issue or explain the limitation rather than inventing data.

Example invocation by the executor:

```bash
python3 scripts/format_recent_transactions.py < input.json
```

## Validation before sending

Confirm that every displayed record matches the requested card and is in a posted status; that each displayed date falls in the stated inclusive window; that no more than `limit` records are shown; and that the net total is calculated from all matching records, not only the displayed subset. If output is truncated, say so and offer a narrower date range or the remaining records. Never treat unavailable pending activity as a missing posted transaction.
