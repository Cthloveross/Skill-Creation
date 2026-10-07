---
name: credit-card-transaction-review
description: Retrieve, filter, and clearly present recent activity for a specified credit card, including transaction dates, merchant descriptors, amounts, status, category, and recorded rewards. Use when a customer asks to see or review card charges, especially when comparing activity with a balance.
---

# Credit Card Transaction Review

Use this skill for a **read-only** transaction review. It does not change the account, file a dispute, or decide that a charge is unauthorized.

## Required runtime data

Obtain the customer identity and then retrieve:

1. The customer's credit-card accounts (`get_credit_card_accounts_by_user`) to confirm that the requested card exists and to obtain its displayed current balance and rewards balance.
2. The customer's transaction history (`get_credit_card_transactions_by_user`).
3. Current time only when it is needed to define a relative request (for example, “this month” or “last 30 days”).

Use the requested card type as the filter. Do not mix transactions from another card, even if they belong to the same customer. Do not infer a card from a transaction alone when multiple accounts could match.

If the requested card is absent, say so and ask the customer which available card they meant. If no matching transactions are returned, say that no matching posted/completed transactions were found for the stated period. Do not invent activity.

## Scope and presentation

1. Honor an explicit date range, merchant, amount, or transaction-status filter from the customer.
2. For an ambiguous request such as “recent transactions,” show the most recent available matching activity in descending date order. State the date range covered. If the returned history is long, show a manageable most-recent set and offer a specific time range, merchant filter, or full monthly report; do not conceal that the list is truncated.
3. For each displayed record provide: date, merchant descriptor, amount, category when supplied, status when supplied, and transaction ID when the customer may need to identify a particular charge. Include recorded rewards when supplied.
4. Clearly label the account's current balance separately from the sum of the displayed transactions. A current balance may include transactions outside the displayed period, payments, credits, interest, fees, or statement-cycle effects, so do not claim that it equals the displayed total.
5. Sum only the displayed positive/negative transaction amounts, preserving credits/refunds as negative values if they are supplied that way. Label this “total of transactions shown,” not “amount owed.”

For cash-back cards whose transaction data stores rewards as points, explain only if useful: 1 recorded point represents $0.01 of cash back. For a Silver Rewards Card, posted purchases categorized as Travel or Software may earn the enhanced 4% rate; other categories should not be represented as eligible for that rate. Recorded points and merchant classification control the actual result.

## Using the formatter

Normalize tool results into the JSON schema accepted by `scripts/format_transactions.py`, then run it. The script reads one JSON object from stdin and writes one JSON object to stdout.

Input schema:

```json
{
  "requested_card_type": "<card type>",
  "transactions": [
    {
      "transaction_id": "<id>",
      "credit_card_type": "<card type>",
      "merchant_name": "<descriptor>",
      "transaction_amount": "<amount such as $12.34 or -5.00>",
      "transaction_date": "<MM/DD/YYYY or YYYY-MM-DD>",
      "category": "<optional category>",
      "status": "<optional status>",
      "rewards_earned": "<optional points value>"
    }
  ],
  "date_from": "<optional MM/DD/YYYY or YYYY-MM-DD>",
  "date_to": "<optional MM/DD/YYYY or YYYY-MM-DD>",
  "limit": 0
}
```

`limit` is optional; omit it or use `0` for every matching transaction. Positive limits retain the newest matching records. The output contains `transactions`, `matched_count`, `shown_count`, `shown_date_range`, `total_amount`, and `total_rewards_points`. Amounts are decimal strings rounded to cents; reward totals are emitted only when every shown transaction has a parseable recorded reward.

Runnable invocation pattern:

```text
python3 scripts/format_transactions.py <<'JSON'
{"requested_card_type":"<requested card>","transactions":[...],"limit":0}
JSON
```

Before communicating the result, validate that every displayed item has the requested card type, falls within any requested dates, and that the displayed total equals the formatted transaction amounts. The helper performs these filter and sum operations deterministically; still compare its `matched_count` with the retrieved data and disclose any chosen truncation.

## Balance concern and possible disputes

A request to review charges alone is not a dispute request. After showing activity, invite the customer to identify any unfamiliar, duplicate, or incorrect transaction. If they do, ask whether they recognize it and collect the appropriate dispute information before taking a formal dispute action. Do not file a dispute merely because the balance seems high. For a missing transaction, note that pending items may not appear until posted.

Do not expose full sensitive account data unnecessarily; card type and any available last four digits are sufficient for a review. Do not fabricate a last four digits value.
