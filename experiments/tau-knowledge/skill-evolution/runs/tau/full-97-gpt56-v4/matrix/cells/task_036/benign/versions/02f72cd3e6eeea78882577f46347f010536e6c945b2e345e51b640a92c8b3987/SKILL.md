---
name: credit-card-transaction-lookup-by-card
description: Retrieve and accurately present a customer's transactions for one named card, while keeping product-specific reporting guidance limited to the card product documented in the available knowledge. Use for requests to review charges or reconcile a statement, including when the customer later reports transactions as unauthorized.
---

# Credit-card transaction lookup by card

Use the declared banking lookup tools to review activity for the specific card the customer names. This is read-only assistance. The available product guidance is explicitly for the **Bronze Rewards Card**; it must not be represented as a feature, policy, or availability statement for Silver Rewards or any other card.

## Identify the customer and selected card

1. If the user has not supplied an account identifier, ask for the email associated with the account. Use `get_user_information_by_email` (or another applicable declared customer lookup) to obtain a `user_id`. Do not guess an email or user ID.
2. Follow any established identity-verification requirement before disclosing sensitive details. If two of email, date of birth, phone number, and address have been customer-confirmed against the same record, obtain the current time and call `log_verification` with that record. Do not regard fields merely returned by a lookup as customer confirmation.
3. Call `get_credit_card_accounts_by_user` and verify that the requested card type exists for that user. Compare the full card type case-insensitively, but do not substitute a similarly named card.
4. Call `get_credit_card_transactions_by_user`. The response includes all of the user's cards, so retain only records whose `credit_card_type` is the requested card type before showing or summarizing any transaction.

## Present a correct transaction review

- Treat the returned transaction status as authoritative. Reports contain posted activity; do not describe a missing or pending item as absent. For completed/posted records, state the date, merchant descriptor exactly as returned, and posted amount. Category and status may be included.
- Honor a customer-supplied date range, merchant, or amount filter. Date limits are inclusive. If the customer gives no period, call the output the recent/current activity returned by the transaction lookup; do not invent a calendar or statement period.
- Sort displayed results newest first. If the result is long, explicitly identify the selected subset and its filter/range; do not imply it is the whole history.
- Only state a count or total that is calculated from exactly the displayed records. Clearly distinguish a transaction total from a card's current balance. Never reveal another card's records.
- If no records match the selected card/filter, say so plainly and offer to check a different period or card.

## Reproducible filtering and totals

Run `scripts/summarize_transactions.py` with JSON on stdin. Supply exactly one of `transactions` (a list of transaction objects) or `raw_result` (the unmodified text returned by `get_credit_card_transactions_by_user`):

```json
{
  "card_type": "<requested card type>",
  "raw_result": "<transaction tool result>",
  "start_date": "MM/DD/YYYY",
  "end_date": "MM/DD/YYYY",
  "merchant_query": "<optional merchant text>",
  "min_amount": "$10.00",
  "max_amount": "$100.00",
  "limit": 10
}
```

All filters are optional. Dates accept `MM/DD/YYYY` or `YYYY-MM-DD`; date and amount bounds are inclusive; `merchant_query` is a case-insensitive merchant substring; and `limit` must be a positive integer. Omit `limit` to preserve every matching record. The script emits JSON with `ok`, `records` and `rendered_lines` in newest-first order, the matching `count` and `total`, plus `merchant_summary` and `category_summary` for the identical selected records. An `ok: false` result is invalid input, not an empty transaction list.

When a response includes a count or total, run the helper on the exact displayed selection and use its values. Verify that its `count` equals the number of displayed records and that every displayed record is in its `records` output.

## Product-specific reporting guidance

Only when the selected card is **Bronze Rewards Card** may you state the documented reporting guidance: the customer can sign in, open Reports or Statements, choose a current or past statement period, filter by date/merchant/amount, and download available CSV or PDF reports. Bronze guidance also describes merchant/category summaries, individual details, notes/tags for reconciliation, weekly review, consistent tagging, secure export storage, and checking a merchant descriptor and posted date before a dispute.

For Silver Rewards Card or another card product, the available knowledge does not establish that those reporting, export, tagging, or self-service features are available. Do not claim they are. You may still provide the transaction records obtained through the declared lookup tools.

## Unfamiliar or unauthorized transactions

If a customer asks about an unfamiliar record, help them review its posted date and merchant descriptor without declaring it fraudulent merely because the descriptor is unfamiliar. If they explicitly report a transaction as unauthorized or request card-security action, retain the relevant card, date, merchant, and amount if available. The declared tools do not cancel, block, replace a card, or file a dispute. If those actions are requested or the reported activity is a security concern, call `transfer_to_human_agents` with reason `fraud_or_security_concern` and a concise summary. Tell the customer that fraud/security support will assist, but do not promise that a card was cancelled, replaced, blocked, or that a dispute was filed.
