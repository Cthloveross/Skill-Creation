---
name: credit-card-monthly-transaction-review
description: Review a customer's reported credit-card activity for a named card, present the correct card's posted charges, and explain the available monthly reporting and reconciliation options. Use when a customer asks to see recent charges, reconcile a statement, investigate a higher balance, or asks what to do with an unfamiliar transaction.
---

# Credit-card monthly transaction review

Use this Skill for read-only transaction-reporting help. It works with the declared account and transaction lookup tools and never treats analysis as an account action.

## Scope and supported actions

The reporting capability supports month-to-date or past-period review by merchant and category, individual transaction details (date, merchant descriptor, and posted amount), transaction notes/tags, and CSV/PDF exports. The declared agent tools in this runtime only retrieve card accounts and transactions; they do **not** add a note/tag, create/download an export, cancel a card, replace a card, or file a dispute. Do not claim that any of those actions occurred.

Use the normal customer-identification flow before retrieving a person's data. When an established support flow requires identity verification, obtain the required customer confirmation, use the lookup result to verify it, and call `log_verification` only after two of date of birth, email, phone number, and address have been confirmed. Do not manufacture confirmation from a field merely returned by a lookup. An email supplied by the customer may be used with `get_user_information_by_email` to find the `user_id`.

## Retrieve and select the right activity

1. Determine the requested card type and user. If necessary, ask for the account email rather than guessing it, then use the applicable customer lookup tool.
2. Call `get_credit_card_accounts_by_user` with the resulting `user_id`. Confirm that the named card type exists. Match card type exactly other than capitalization; do not substitute a similar card.
3. Call `get_credit_card_transactions_by_user` with that same `user_id`. It returns every card's activity, so select only records whose `credit_card_type` matches the requested card before communicating records.
4. Use the returned status as authoritative. Transactions appear in reports once posted; a missing or pending item must not be described as absent. Describe completed/posted records as charges and retain the merchant descriptor exactly as returned.
5. Apply a customer-supplied date range, merchant, or amount filter exactly. Date boundaries are inclusive. If no period is specified, do not silently label the result a statement period; call it the recent/current activity returned by the lookup. Sort the selected records newest first.
6. State each selected record's date, merchant descriptor, and posted amount. Category and status can be included. When useful, provide a count and total only for exactly the records shown, and make clear that a transaction total is not the current balance. A merchant/category summary may be calculated from the same selected records if requested.
7. If there are no matching selected-card records, say so and offer another period or card. Never expose a different card's records.

## Reproducible filter and total

Run `scripts/summarize_transactions.py` with JSON on stdin. Supply exactly one of `transactions` or `raw_result`:

```json
{
  "card_type": "<requested card type>",
  "transactions": [
    {
      "transaction_id": "<id>",
      "credit_card_type": "<card type>",
      "merchant_name": "<merchant descriptor>",
      "transaction_amount": "$12.34",
      "transaction_date": "MM/DD/YYYY",
      "category": "<category>",
      "status": "COMPLETED"
    }
  ],
  "start_date": "MM/DD/YYYY",
  "end_date": "MM/DD/YYYY",
  "limit": 10
}
```

`transactions` is a list of transaction objects. `raw_result` may instead be the unmodified line-oriented result from `get_credit_card_transactions_by_user`. `start_date` and `end_date` are optional inclusive dates in `MM/DD/YYYY` or `YYYY-MM-DD`; `limit` is an optional positive integer. Omit `limit` to include all matching records.

For any reply that states a transaction count or total, run this helper on the exact records that will be displayed and copy its `count` and `total`; do not hand-count or total a separately selected list. The script emits JSON with `ok`, `card_type`, `date_range`, `count`, `total`, `records`, and `rendered_lines`; `records` and lines are newest first. A malformed input or an end date before the start date emits `{"ok": false, "error": "..."}`. Treat that as an error to correct, not as proof of no transactions. Before replying, compare `count` with `len(records)`, verify every displayed record is in `records`, and check that every displayed record has the selected card type and requested date range. Do not state a count or total if this validation cannot be completed.

## Reconciliation, reports, and unfamiliar charges

For self-service reporting, direct the customer to sign in, open **Reports** or **Statements**, choose the current or a past statement period, apply date/merchant/amount filters, then download a CSV or PDF if available. They can use transaction notes or tags there to aid reconciliation. Recommend checking activity weekly, using tags consistently for month-to-month category totals, and storing exports securely for budgeting or tax records.

If a transaction looks unfamiliar, first help the customer review its posted date and merchant descriptor. Do not call it fraudulent solely because a balance is unexpected or a descriptor is unfamiliar. If the customer explicitly says a listed transaction is unauthorized or requests urgent card security action, capture the relevant card and transaction details without exposing other-card records. Card cancellation, blocking, replacement, and disputes are outside the declared reporting tools. If those actions are unavailable, use `transfer_to_human_agents` with reason `fraud_or_security_concern` and a concise summary of the reported charge(s) and requested action; tell the customer a fraud/security specialist will assist. Do not promise that the card was cancelled, replaced, blocked, or disputed unless an authorized tool has actually completed that action.
