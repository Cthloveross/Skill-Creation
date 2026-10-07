---
name: credit-card-transaction-review
description: Assist a verified credit-card customer who asks to review charges or a balance by locating the requested card, retrieving its transaction history, and giving a concise, accurate recent-transaction summary. Use for read-only transaction and balance inquiries; do not use it to dispute, reverse, or alter transactions.
---

# Credit-card transaction review

## Purpose and boundaries

Use this Skill for a customer asking what has been charged to a named credit card, especially when they believe a balance is higher than expected. This is a read-only review: do not change account information, initiate a dispute, or imply that a charge is erroneous merely because it looks unfamiliar.

Use only the normal banking tools provided in the task runtime. The supplied observations may be used as evidence, but do not treat values from a prior instance as reusable facts. Obtain account and transaction data for the current customer at runtime when it has not already been supplied.

## Workflow

1. **Identify the customer.** If a user ID is not already available from the live conversation, ask for the account holder's full name or email address. Use the matching lookup tool (`get_user_information_by_name` is case-sensitive; use `get_user_information_by_email` when email is supplied). If no single record is found, ask for a corrected identifier rather than guessing.
2. **Apply the runtime's verification process when required.** The available `log_verification` tool specifies that successful verification consists of confirming two of date of birth, email, phone number, and address. Ask the customer to confirm the required fields; do not expose unconfirmed fields as prompts. Once two fields match, obtain the current timestamp with `get_current_time` and call `log_verification` with all required fields from the matched user record. If verification cannot be completed, explain that account-specific details cannot be reviewed and do not make account changes.
3. **Locate the requested card.** Call `get_credit_card_accounts_by_user` and match the card type exactly when the customer names one. If there are multiple plausible matches, list only the card-type choices necessary to clarify; do not guess. If no matching account exists, say so.
4. **Retrieve and filter charges.** Call `get_credit_card_transactions_by_user`, retain only records whose `credit_card_type` exactly matches the selected card, and sort by `transaction_date` descending. Keep transaction IDs available for a later inquiry, but do not include them in the ordinary customer-facing list unless useful.
5. **Present a useful answer.** State the selected card and its current balance as shown by the account tool. For an unqualified request for “recent” transactions, show the latest 10 dated transactions (or all if fewer than 10). For each, provide date, merchant, amount, category, and status. Say how many were shown and offer to show older transactions or filter by merchant/date. Do not call transactions “fraudulent,” “duplicated,” or “pending” unless the returned status/data supports that statement.
6. **Handle a charge concern.** If the customer flags a specific transaction, acknowledge it and ask which date, merchant, and amount they want to examine. Follow only an explicitly available dispute/fraud procedure; this Skill does not authorize an alteration. If no such procedure is available, offer appropriate human assistance, using the runtime transfer tool only when a transfer is requested or necessary.

## Using the formatter

The helper turns the text returned by the account and transaction tools into a deterministic review object. Run it from the package root after collecting both tool results:

```bash
python3 scripts/summarize_card_transactions.py <<'JSON'
{
  "card_type": "<exact selected card type>",
  "accounts_result": "<verbatim get_credit_card_accounts_by_user result>",
  "transactions_result": "<verbatim get_credit_card_transactions_by_user result>",
  "limit": 10
}
JSON
```

It writes JSON to stdout with `ok`, `card`, `transactions`, `shown_count`, and `total_matching_count`. On malformed or incomplete source data it writes `ok: false` and an `error`; do not invent missing charges or balances. A successful result must have a non-null `card`, a nonempty selected `card_type`, and every displayed transaction must have that same card type. The output is ordered newest first using `MM/DD/YYYY` dates.

If scripting is unavailable, perform the same exact-card filter and date sort manually. The helper is a formatter only: it does not call banking tools and cannot authorize any action.
