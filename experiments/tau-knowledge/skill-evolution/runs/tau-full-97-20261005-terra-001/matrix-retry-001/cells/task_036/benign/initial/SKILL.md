---
name: credit-card-transaction-review
description: Review and clearly summarize recent or statement-period credit-card transactions for a specified card. Use when a customer asks what has been charged, wants to investigate a higher-than-expected balance, or needs a transaction list by date, merchant, and amount.
---

# Credit-card transaction review

Use this Skill to give a concise, accurate, read-only transaction report. It is suitable for a cardholder who asks to see charges, recent activity, or a monthly statement-period view.

## Required inputs and available tools

Obtain the customer identity needed by the runtime and identify the requested card:

1. If needed, use the supplied customer identifier (for example, email) with `get_user_information_by_email`, or another available user lookup, to obtain the `user_id`.
2. Call `get_credit_card_accounts_by_user` and match the requested card type exactly. Do not assume that another card belonging to the user is the requested card.
3. Call `get_credit_card_transactions_by_user` with that `user_id`.
4. Use `get_current_time` if a current-month or date-relative scope is requested.

The tool descriptions state that a verification audit must be logged **after** successfully verifying two of the four identity fields (date of birth, email, phone, address). If such verification is performed, obtain the current timestamp and call `log_verification` with every required field. Do not claim verification occurred when fewer than two fields were confirmed. No source supplied with this Skill establishes an additional mandatory verification rule for read-only reporting; follow any runtime/session controls that do apply.

## Scope selection

- Honor an explicit date range, statement month, merchant, amount, or number-of-transactions request.
- For “recent” with no stated period, present a clearly labeled limited view (normally the 10 latest completed transactions) and offer to show a particular statement month or a wider range.
- For a current-month request, filter using the current calendar month from the supplied current time.
- A monthly report contains posted/completed activity. Do not describe a transaction as posted if the returned data supplies only a generic transaction date. State the date field exactly as returned.
- Keep pending or non-completed items separate from the completed report. The reporting guidance says items appear in reports once posted; tell the customer to check pending activity if they believe something is missing.

Use `scripts/build_transaction_report.py` for repeatable selection, sorting, totals, and formatting. It accepts structured records, not the prose rendering of a tool response. Convert the selected account and transaction fields into the documented JSON shape without adding or guessing fields.

## Run the report helper

Run:

```text
python scripts/build_transaction_report.py
```

Send JSON on stdin with this schema:

```json
{
  "requested_card_type": "string",
  "accounts": [
    {"card_type": "string", "current_balance": "$0.00", "account_id": "optional"}
  ],
  "transactions": [
    {
      "credit_card_type": "string",
      "transaction_id": "optional string",
      "merchant_name": "string",
      "transaction_amount": "$0.00 or number",
      "transaction_date": "MM/DD/YYYY or YYYY-MM-DD",
      "category": "optional string",
      "status": "optional string"
    }
  ],
  "scope": {
    "mode": "last_n | date_range | calendar_month | all",
    "limit": 10,
    "start_date": "optional MM/DD/YYYY or YYYY-MM-DD",
    "end_date": "optional MM/DD/YYYY or YYYY-MM-DD",
    "month": "optional YYYY-MM",
    "statuses": ["COMPLETED"]
  }
}
```

`scope` is optional. Its default is the 10 latest transactions for the requested card with status `COMPLETED`. `calendar_month` requires `month`; date ranges require at least one boundary. Set `statuses` to `null` to include all statuses, or provide explicit statuses. The helper writes one JSON object to stdout:

- `ok: true` includes `card`, `scope`, `transactions` (newest first), `transaction_count`, `total`, `category_totals`, and `non_completed_matching_count`.
- `ok: false` includes a machine-readable `error` and explanatory `message`. Do not make up a report when this occurs.

The monetary `total` is the total of only the displayed transactions; it is not the account balance, statement balance, amount due, or a reconciliation.

## Customer-facing response

When the helper succeeds:

1. Confirm the requested card was found and give its returned current balance only if useful to the customer’s concern. Label it `current balance` and do not infer why it has that value.
2. State the report scope and transaction count.
3. List each selected transaction in a readable form: `date — merchant — amount` (optionally category). Preserve the returned merchant descriptor and amount.
4. Provide the displayed-transaction total with a limiting label, such as “Total of the 10 transactions shown.”
5. If the report found matching non-completed records excluded by the default completed-only view, say that pending/non-completed activity is separate and offer to review it. Never call it a posted charge.
6. Ask whether the customer recognizes the entries or wants a different date range, merchant filter, or statement-month view. If they flag an unfamiliar item, first review the date and merchant descriptor before beginning a dispute process.

Do not expose unrelated cards, unrelated transactions, full identity profile fields, or internal record IDs in the customer response. Do not assert that the displayed activity fully explains the balance: balances can include transactions outside the selected range and other statement activity.

For self-service exports, explain that the customer can sign in, open **Reports** or **Statements**, choose the current or past statement period, apply date/merchant/amount filters, and download CSV or PDF. Do not claim an export was created unless an available runtime tool actually created it.

## Validation before responding

Check that:

- exactly one requested-card account was matched;
- every displayed transaction has the requested card type;
- dates are sorted newest first and are within the selected scope;
- displayed total and category totals came from the selected items only;
- the current balance, if stated, came from the matched account rather than a transaction sum;
- no missing, malformed, or ambiguous result was silently substituted with a guess.

If the card cannot be matched, ask the customer to clarify the card name. If no records match, say no matching transactions were returned for that scope and offer another date range. If the transaction service or data is unavailable, explain that it could not be retrieved and do not invent charges.
