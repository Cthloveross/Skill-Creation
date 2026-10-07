---
name: credit-card-recent-transaction-review
description: Securely verify a customer and provide a read-only, card-specific review of recent credit-card transactions, including a clearly scoped summary for balance reconciliation. Use when a customer asks to see, review, or reconcile charges on a credit card.
---

# Credit Card Recent Transaction Review

Use this skill for a **read-only** review of credit-card transactions. It does not dispute charges, change an account, make a payment, block a card, or promise that transaction totals reconcile to the current balance.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this read-only workflow, apply the control as follows:

- Verify identity and authority before disclosing nonpublic account, balance, or transaction information.
- Verify that the requested card account belongs to the verified customer and that its card type matches the card the customer named.
- Verify that the requested reporting data is available through the supported account/transaction lookup tools. Do not claim a reporting feature is available for a product unless supported by returned data or applicable knowledge.
- Retrieve and report the returned balance only as a current snapshot. Do not infer available credit, fees, limits, statement cutoffs, payments, interest, credits, pending activity, or billing-cycle treatment when those facts are not supplied.
- This workflow has no recipient, transfer, payment, or account-change instruction. Those controls and any confirmation requirements become applicable only if the customer asks to take such an action; stop this workflow and follow the applicable action-specific procedure first.

## Required verification and lookup workflow

1. **Identify the requested scope.** Confirm the card type and ask for a date range or statement period if the customer needs more than a short recent-activity view. If no period is specified, state that “recent” will be the 10 newest returned transactions, and offer a full month or statement-period review.
2. **Verify the customer.** Obtain assertions for at least two distinct fields among date of birth, email, phone number, and address. Compare both assertions with the authoritative user record. Do not reveal the missing values or use a lookup result as the customer's assertion.
3. **Create the verification audit record.** After two fields match, obtain the current timestamp and call `log_verification` with the authoritative name, user ID, address, email, phone number, date of birth, and timestamp. Do not disclose account information if verification fails or cannot be logged.
4. **Verify ownership and requested card.** Call `get_credit_card_accounts_by_user` for the verified user. Find an account whose `user_id` is the verified user and whose `card_type` matches the requested card. If no exact match exists, explain that the requested card could not be confirmed; do not substitute another card.
5. **Retrieve data only after verification.** Call `get_credit_card_transactions_by_user` for the verified user. Keep only records with the requested `credit_card_type`, and ensure any returned record user ID matches the verified user.
6. **Apply the requested date scope.** Use transaction dates as returned. For a monthly or statement-period request, use inclusive start and end dates supplied by the customer or known from the statement; do not guess a statement closing date. For a recent-only request, sort newest first and use the declared limit.
7. **Summarize deterministically.** Run `scripts/summarize_card_transactions.py` on the filtered raw records. Give the script the verified user ID as `expected_user_id`, the exact requested card type, and the intended date/limit settings.
8. **Present the result clearly.** State the card type, scope, number of transactions, whether the list was truncated, and a table with date, merchant descriptor, amount, category, and returned status. Include the current balance separately if it was returned by the account lookup. Describe totals as totals of the displayed or scoped returned activity, not as the balance.
9. **Set reconciliation expectations.** Explain that a transaction review may not explain the balance because the supplied activity may omit payments, credits, refunds, interest, fees, balance transfers, and pending or differently posted items. Do not label a charge unfamiliar or fraudulent based only on its merchant descriptor. If the customer identifies a particular item as unfamiliar, first review its date and descriptor, then move to the supported dispute/security workflow rather than opening a dispute automatically.

## Handling incomplete or unsupported requests

- If identity is not verified, request another identity field and do not show the transactions, balance, account list, or card details.
- If the customer is not the account owner or lacks authority, decline disclosure and follow the organization’s authorized-party process if available.
- If there are no matching records, say no matching returned transactions were found for the specified card and scope; do not assert that no charge ever occurred.
- If a report is truncated, say so and offer a narrower date range, a full statement-period review, or the supported export/report route when available.
- If transaction data are malformed, mixed across users, or cannot be confidently scoped to the requested card, do not present a computed total. Explain the data limitation and use supported tools or escalation procedures.

## Summarizer interface

`scripts/summarize_card_transactions.py` reads one JSON object from standard input and writes one JSON object to standard output. It uses only the supplied records and performs no account action.

Input schema:

```json
{
  "transactions": ["raw transaction objects returned by the transaction lookup"],
  "card_type": "requested card type",
  "expected_user_id": "verified user ID",
  "start_date": "optional YYYY-MM-DD or MM/DD/YYYY inclusive start",
  "end_date": "optional YYYY-MM-DD or MM/DD/YYYY inclusive end",
  "recent_limit": 10
}
```

`transactions`, `card_type`, and `expected_user_id` are required. `recent_limit` defaults to 10 and must be a positive integer. A date range is inclusive; provide a sufficiently large limit for a complete date-range report when appropriate.

Success output has `ok: true`, a newest-first `transactions` list, count and truncation fields, and independently labeled totals. Each returned row preserves the transaction identifier when supplied and normalizes its amount to a two-decimal currency string. Failure output has `ok: false` and an `errors` list; do not use a failed output for customer disclosure.

Runnable invocation with a runtime-supplied request file:

```sh
python3 scripts/summarize_card_transactions.py < request.json
```

Before presenting a successful result, validate that `ok` is true, that every output row is for the requested card and verified user, that dates are within any requested range, and that the response labels a limited list as truncated. The executor, not the script, is responsible for identity verification, audit logging, tool calls, and the final customer-facing explanation.
