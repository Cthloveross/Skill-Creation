---
name: credit-card-transaction-report
version: 1.0.0
description: Retrieve and present posted recent transaction activity for a customer's specified credit card, including a clear reconciliation-friendly list and optional total. Use when a customer asks to see charges, review a statement, or investigate an unexpectedly high card balance.
---

# Credit-card transaction report

Use this Skill to provide an accurate, read-only report of activity on one specified credit card. Do not treat transactions from another card as belonging to the requested card, and do not characterize a charge as unauthorized unless the customer says it is unfamiliar.

## Procedure

1. Identify the customer using the account identifier supplied during the conversation (such as an email), then call `get_user_information_by_email` (or the matching available user lookup) to obtain the `user_id`.
2. Call `get_credit_card_accounts_by_user` and confirm that an account with the requested `card_type` exists. If more than one card could match the customer's wording, ask which card they mean. Do not expose activity before identifying the requested card.
3. Call `get_credit_card_transactions_by_user` with that `user_id`. The result is user-wide, so filter strictly on exact `credit_card_type` equality with the selected card.
4. Report the filtered transactions in descending transaction-date order. Include at least date, merchant, posted amount, category, and status. Include transaction IDs only when useful for reconciliation or when the customer asks for them.
5. State the selected card's current balance from the account lookup separately from transaction totals. A transaction-list total is the sum of returned matching transactions, not necessarily the statement balance; do not imply that it reconciles the balance unless the statement period, payments, credits, and pending items are known.
6. If the user meant a particular statement month or date range, filter by that inclusive range and say exactly what range was used. Otherwise, show all matching returned activity as the available recent history; do not silently choose an arbitrary cutoff.
7. If no matching account or transaction is found, say so plainly. Suggest checking the card name, statement period, or pending activity. The available reporting guidance says transactions appear in reports after posting.
8. Offer a narrower merchant/date/category review or a monthly CSV/PDF export. Per the available guidance, the customer can sign in, open Reports or Statements, select a month, apply filters, and download the report.

## Optional deterministic formatter

`scripts/format_card_transactions.py` parses the plain-text result returned by `get_credit_card_transactions_by_user`, selects one exact card type, sorts it newest first, and calculates an exact decimal total. It is useful when the tool returns many mixed-card records.

Input JSON on stdin:

```json
{"raw_transactions":"<verbatim transaction tool result>","card_type":"<requested card type>","start_date":"MM/DD/YYYY optional","end_date":"MM/DD/YYYY optional"}
```

`start_date` and `end_date` are optional inclusive bounds; omit both to retain every matching returned record. The script emits JSON containing `transactions`, `transaction_count`, `total_amount`, `card_type`, and `errors`. It returns an error rather than guessing if the input is malformed or a date bound is invalid.

Example invocation after copying the transaction tool's textual result into JSON:

```sh
python scripts/format_card_transactions.py <<'JSON'
{"raw_transactions":"Found 0 record(s) in 'credit_card_transaction_history':","card_type":"Example Card"}
JSON
```

Validate before using the report: ensure every output transaction has the selected exact card type, the output dates satisfy any requested bounds, the list is newest-first, and `total_amount` equals the sum of listed amounts. The script's output is an aid; the customer-facing response must remain grounded in the actual account and transaction tool results.

## Customer-facing response shape

Use a brief, readable heading naming the requested card, then a dated list or table of matching charges. State the number of returned posted transactions and, if helpful, their summed amount. Mention the current card balance separately. Avoid revealing unrelated-card activity, unrelated profile fields, or internal database identifiers unnecessarily. End by asking whether the customer wants a specific statement month, merchant review, or help with a particular unfamiliar transaction.
