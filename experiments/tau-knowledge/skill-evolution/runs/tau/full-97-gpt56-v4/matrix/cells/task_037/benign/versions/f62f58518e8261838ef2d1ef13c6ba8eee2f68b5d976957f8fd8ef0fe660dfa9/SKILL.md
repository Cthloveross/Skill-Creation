---
name: credit-card-recent-transaction-review
description: Retrieve and clearly present recent transactions for one specified credit-card type after the customer identifies the account and chooses all available recent activity or a date range. Use for read-only statement and balance-review requests.
---

# Credit-card recent-transaction review

Use this Skill when a customer wants charges or recent activity for a particular card. It is a read-only workflow: do not make account changes, file a dispute, or imply that a charge is unauthorized merely because the customer says their balance seems high.

## Required information and tool workflow

1. Identify the customer using an identifier they provide, such as email, with the normal customer lookup tool. If no usable identifier is available, ask for one.
2. Get the customer's credit-card accounts and confirm that the requested card type exists. If several cards could match the description, ask which card is intended.
3. Ask whether the customer wants all available recent activity or a date range unless that preference is already clear.
4. Retrieve the customer's credit-card transaction history. Keep only records whose `credit_card_type` exactly matches the selected card type. For a date range, include dates within the stated inclusive range. For an all-recent request, include every matching record returned by the tool; do not invent a rolling-day cutoff.
5. Treat `COMPLETED` records as posted transactions. If other statuses are returned, label and separate them rather than presenting them as posted. Do not mix transactions from another card into the answer.
6. Sort by transaction date, newest first, and present each matching posted item with its date, merchant descriptor, and posted amount. Include the card's current balance only if it was retrieved, and clearly distinguish it from the displayed activity; do not claim that the listed charges add up to the balance unless the request and data establish that.

The reporting information supports reviewing posted transaction date, merchant descriptor, and amount. If the customer finds an entry unfamiliar, suggest reviewing the posted date and descriptor before pursuing a dispute. If they need a statement-period report or export, explain that they can use the account's Reports or Statements area, select a month, filter by date/merchant/amount, and download CSV or PDF.

## Identity and safety

Only log identity verification after the customer has actually confirmed at least two of the four required fields (date of birth, email, phone number, address). Providing an email lookup value alone is not two-field verification, and possession of a requested card name is not one of those four fields. Do not claim verification occurred when it did not. This read-only reporting workflow does not itself require an account mutation.

## Formatting the reply

Use a short introduction such as “Here are the posted [card type] transactions returned for your requested period.” Then use a readable bulleted list:

`MM/DD/YYYY — Merchant descriptor — $amount`

State the number of posted transactions and the coverage dates based only on the returned records. If no matching records exist, say so plainly. Never expose internal user IDs or transaction record IDs in the customer-facing reply. Preserve duplicate merchants and duplicate amounts: each record is a distinct transaction.

Use `scripts/format_transactions.py` when tool data is available in structured JSON or in the normal human-readable transaction-tool result. It filters, sorts, validates, and creates a customer-ready draft. Review its JSON output, then send its `response` value (or a faithful rendering of it) to the customer.

### Script interface

Run `scripts/format_transactions.py` with one JSON object on stdin. Required fields are:

- `card_type` (string): selected card type, matched case-insensitively.
- One of `transactions` (a list of transaction objects) or `raw_transactions` (the text returned by the transaction lookup tool).

Optional fields:

- `current_balance` (string or number): balance retrieved for the selected card.
- `start_date` and `end_date`: inclusive boundaries in `MM/DD/YYYY` or `YYYY-MM-DD` form.

The script writes JSON with `ok`, `posted_count`, `pending_count`, `coverage`, `transactions`, and `response`. On invalid input or an inverted/invalid date range it writes `{"ok": false, "error": "..."}`. `transactions` contains only customer-safe fields: date, merchant, amount, category, and status.

Example invocation shape (replace all values with live tool results):

```json
{"card_type":"<requested card>","transactions":[{"credit_card_type":"<requested card>","merchant_name":"<merchant>","transaction_amount":"$12.34","transaction_date":"11/14/2025","status":"COMPLETED"}],"current_balance":"$100.00"}
```

Before responding, confirm the selected card type matches every presented record, each row has date/merchant/amount, dates are descending, and no internal IDs or other-card activity are included.