---
name: credit-card-transaction-history
version: 1.0.0
description: Retrieve and clearly present a customer's requested recent credit-card transactions for one specified card, while keeping results limited to that card. Use for read-only transaction-history requests, including requests to review charges that may explain a balance.
---

# Credit-card transaction history

Use this Skill when a customer asks to see charges or recent transactions on a named credit card. It handles the normal banking tools' text responses and produces a card-scoped, date-sorted list suitable for a customer-facing reply.

## Required information

Obtain:

1. An account lookup identifier: the customer's full name or email address.
2. The requested card type, if it is not already clear.
3. How many transactions to show. Interpret an unambiguous request for all available transactions as `all`; otherwise ask for a count when the customer has not supplied one.

Do not invent an identity field or a transaction limit. A name/email lookup is sufficient to locate the record for this read-only workflow. Only call `log_verification` after the customer has actually confirmed at least two of the four required identity fields; do not represent a database lookup as verification.

## Tool workflow

1. Look up the customer with `get_user_information_by_name` or `get_user_information_by_email` using the identifier supplied by the customer.
2. If there are no matches, ask the customer to check or provide the other identifier. If there are multiple matches, request enough information to select the correct customer without disclosing account data.
3. Use the selected `user_id` with `get_credit_card_accounts_by_user`. Confirm that the requested card type is among the returned accounts. If not, explain that no matching card is found and ask which listed card they mean; do not guess from a similar card name.
4. Call `get_credit_card_transactions_by_user` once for that `user_id`. Filter returned records by exact `credit_card_type` equality with the confirmed card type. Never include transactions belonging to another card.
5. Sort matching transactions by transaction date newest first. For equal dates, preserve the source order unless a more precise source timestamp exists. If the customer requested a numeric count, show only that many after sorting; if they requested all, show every matching record.
6. Give a concise reply that identifies the card, states how many records are being shown, and lists each selected transaction with date, merchant, amount, category, and status. Mention rewards only if the customer asks about rewards. Retain the transaction ID internally for follow-up but do not needlessly expose it in the customer-facing list.
7. If no matching transactions exist, say so plainly. Do not infer that the balance is wrong, attempt a dispute, or calculate a balance reconciliation merely from the transaction list. Offer help identifying a charge or reviewing a particular transaction.

When a large all-transactions request makes the reply unwieldy, still provide all records through a clearly continued, chronological list rather than silently truncating it. Do not duplicate rows due to repeated tool calls.

## Formatting guidance

Use a readable heading followed by bullets or a compact table. Money should preserve two decimal places and status should be shown as returned. Example template (placeholders only):

```text
Here are the [N] available transactions for your [card type], newest first:
- [MM/DD/YYYY] — [merchant] — $[amount] — [category] — [status]
...
```

If the customer specifically asks why a balance seems high, frame the history as information to review, not a conclusion: offer to help investigate any transaction they do not recognize.

## Parser helper

`scripts/prepare_transactions.py` accepts a JSON object on stdin:

```json
{
  "transactions_text": "raw result from get_credit_card_transactions_by_user",
  "card_type": "requested card type",
  "limit": "all"
}
```

`limit` may be `"all"`, a positive integer, or a numeric string. It emits JSON containing `ok`, `transactions` (newest first), `shown_count`, and an optional `error`. Each transaction contains only the fields needed for presentation. It parses the normal multiline tool response, filters on exact card type, deduplicates repeated transaction IDs, and validates dates and limits. Use its structured output to compose the customer-facing list; it does not call bank tools and does not perform any bank action.

Run it from the Skill root with:

```text
python scripts/prepare_transactions.py < input.json
```

Before replying, validate that every displayed record has the requested card type, that the count agrees with the selected limit/all request, and that dates are newest-first. If the tool response cannot be parsed reliably, use the original returned records directly and do not manufacture fields.
