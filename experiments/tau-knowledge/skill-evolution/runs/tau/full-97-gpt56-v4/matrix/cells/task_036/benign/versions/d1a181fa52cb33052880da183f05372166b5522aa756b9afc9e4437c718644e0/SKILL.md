---
name: credit-card-recent-transaction-review
description: Retrieve, filter, and clearly present a customer's recent posted credit-card transactions for one named card. Use for requests to review charges, reconcile a statement, or investigate a higher-than-expected card balance; this is read-only transaction assistance, not a dispute or account-change workflow.
---

# Credit-card recent transaction review

Use this Skill when a customer asks to see charges or recent activity for a particular credit card.

## Operating method

1. Identify the customer using information they provide through the normal support flow. If an email address is needed, ask for it rather than guessing it.
2. Use `get_user_information_by_email` (or another applicable customer lookup) to obtain the `user_id`.
3. Use `get_credit_card_accounts_by_user` and confirm that the requested card type exists. Match the card type exactly, ignoring capitalization only. Do not select a similarly named card without confirming it.
4. Use `get_credit_card_transactions_by_user` with that `user_id`. That tool returns activity for all of the customer's cards, so filter locally by the requested card type before presenting anything.
5. Treat the returned transaction status as authoritative. Present posted/completed transactions as charges. Do not claim that missing or pending items are absent; the reporting guidance says items appear in reports once posted.
6. Sort matching records newest first. If the customer gives a date range, honor it; otherwise say that the list is the recent/current activity returned by the transaction lookup. Avoid silently choosing a calendar or statement period.
7. State each transaction's date, merchant descriptor, and posted amount. Category and status are useful supporting details. Give a count and total only if calculated from exactly the displayed/selected records. Clearly distinguish this transaction total from the account's current balance.
8. If there are no matching records, say so plainly and offer to check a different period or card. If the customer recognizes neither a transaction nor its merchant descriptor, gather the relevant transaction details and follow the separate dispute/fraud workflow; do not characterize it as fraud merely because the balance seems high.

The included helper can make filtering, ordering, date selection, and totals reproducible. It only analyzes supplied transaction data; it never calls banking tools or takes account actions.

## Helper invocation

Run `scripts/summarize_transactions.py` with JSON on stdin, for example:

```json
{
  "card_type": "<requested card type>",
  "transactions": [
    {
      "transaction_id": "<id>",
      "credit_card_type": "<card type>",
      "merchant_name": "<merchant>",
      "transaction_amount": "$12.34",
      "transaction_date": "MM/DD/YYYY",
      "category": "<category>",
      "status": "COMPLETED"
    }
  ],
  "start_date": "MM/DD/YYYY",
  "end_date": "MM/DD/YYYY"
}
```

`transactions` may instead be the raw text returned by `get_credit_card_transactions_by_user`, under `raw_result`. Date bounds are optional and inclusive. `limit` is optional; omit it to preserve every matching transaction. The script emits JSON with `ok`, `records` (newest first), `count`, `total`, and `rendered_lines`. On invalid input it emits `ok: false` with an `error` string.

## Validation before replying

- Verify that all displayed records have the selected card type and, when applicable, are within both inclusive date bounds.
- Check that the reported count equals the number of displayed records and that the total covers the same records.
- Do not reveal transactions belonging to another card, even though the lookup response contains them.
- Use the merchant descriptor exactly as returned; it may differ from a familiar storefront name.
- For a long result, give the requested/recent subset with its explicit date range and offer the rest, rather than implying the subset is the entire history.

Monthly reports can also be reviewed by selecting a current or past statement period in the account's Reports or Statements section and applying date, merchant, or amount filters. The customer may download CSV or PDF for their records when that self-service access is available.