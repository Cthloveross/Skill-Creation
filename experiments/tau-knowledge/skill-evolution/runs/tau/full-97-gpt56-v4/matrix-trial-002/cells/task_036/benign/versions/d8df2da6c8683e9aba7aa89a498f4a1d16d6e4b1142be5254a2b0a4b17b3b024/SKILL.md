---
name: credit-card-transaction-report
version: 1.0.0
description: Retrieve and clearly present recent posted transactions for a customer-selected credit card, including a card-specific balance when available. Use for read-only credit-card statement or charge-review requests.
---

# Credit-card transaction report

Use this Skill for a customer who asks to see recent charges, review statement activity, or understand a credit-card balance. It is read-only: do not alter account details, file a dispute, or imply that an unfamiliar charge is fraudulent.

## Required runtime information

Obtain only what is needed through the normal banking tools:

1. Identify the customer using an identifier supplied by the customer (or request an exact full name, user ID, or email if none is available).
2. Call `get_credit_card_accounts_by_user` and locate the requested card by its exact `card_type`. If several cards could match, ask the customer which one they mean.
3. Call `get_credit_card_transactions_by_user` and retain only records whose `credit_card_type` exactly matches the selected card type.
4. Use the current time only when it is necessary to explain the reporting period or to determine recency. Do not claim a transaction is pending unless its returned status says so.

No identity verification or account-changing tool call is needed solely to provide this read-only transaction report unless a separately supplied policy requires it.

## Produce the response

State the selected card and, when returned, its current balance. List the matching records in descending transaction-date order. For each record, include:

- date,
- merchant descriptor,
- amount,
- category and status when returned.

Describe the list accurately as the matching activity returned by the transaction lookup, rather than claiming it is a complete billing-statement reconciliation. Do not mix transactions from the customer's other cards. If the list is long, show the newest useful subset, state exactly how many of the matching records are shown, and offer to narrow it by date, merchant, or amount. If no matching records are returned, say so and offer those filters.

For a balance concern, briefly note that the returned transactions alone may not explain the balance because a balance can also reflect earlier posted activity, payments, credits, fees, or interest; do not invent any of those items. If a charge looks unfamiliar, invite the customer to identify the date and merchant so it can be reviewed before a dispute is considered.

The supplied product information supports mentioning that monthly reports can be reviewed in the account's Reports or Statements section, filtered by date, merchant, or amount, and exported to CSV or PDF. Present that as an optional next step, not as a claim that an export was performed.

## Optional formatter

`scripts/format_transactions.py` accepts JSON on stdin and emits JSON on stdout. It performs deterministic filtering, date sorting, counting, and markdown generation.

Input schema:

```json
{
  "card_type": "requested exact card type",
  "accounts": [{"card_type": "...", "current_balance": "$0.00"}],
  "transactions": [{"credit_card_type": "...", "merchant_name": "...", "transaction_amount": "$0.00", "transaction_date": "MM/DD/YYYY", "category": "...", "status": "..."}],
  "max_items": 25
}
```

`max_items` is optional and defaults to 25. The output has `matched_count`, `shown_count`, `truncated`, `transactions`, and `markdown`. Supply structured records transcribed from normal tool results; never embed a customer's records in this package.

Example runtime call:

```sh
python3 scripts/format_transactions.py <<'JSON'
{"card_type":"Example Card","accounts":[],"transactions":[]}
JSON
```

Before sending, verify that every displayed record has the requested card type, dates are newest first, the displayed count agrees with the rows, and no transaction from another card or unsupported explanation is included.