---
name: credit-card-recent-transaction-review
description: Securely verify a customer and provide a read-only, card-specific review of recent credit-card transactions, including clearly scoped activity totals for balance reconciliation and a safe fraud/security handoff. Use when a customer asks to see, review, reconcile, or report unfamiliar charges on a credit card.
---

# Credit Card Recent Transaction Review

Use this skill for a **read-only** review of credit-card transactions. It does not dispute charges, change an account, make a payment, block a card, cancel or replace a card, or promise that activity totals reconcile to the current balance. A suspected-fraud report may be handed off to a human agent only after the customer accepts that handoff.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this read-only workflow, apply the control as follows:

- Verify identity and authority before disclosing nonpublic account, balance, or transaction information.
- Verify that the requested card account belongs to the verified customer and that its card type matches the card the customer named.
- Verify that the requested reporting data is available through the supported account and transaction lookup tools. Do not claim a reporting feature is available for a product unless supported by returned data or applicable knowledge.
- Retrieve and report a returned balance only as a current snapshot. Do not infer available credit, fees, limits, statement cutoffs, payments, interest, credits, pending activity, or billing-cycle treatment when those facts are not supplied.
- This workflow has no recipient, transfer, payment, account-change, card-security, dispute, cancellation, or replacement instruction. Those controls and any confirmation requirements become applicable only if the customer asks to take such an action; do not perform the action through this workflow.

## Required verification and lookup workflow

1. **Identify the requested scope.** Confirm the card type and ask for a date range or statement period if the customer needs more than a short recent-activity view. If no period is specified, state that “recent” means the 10 newest returned transactions, and offer a full month or statement-period review.
2. **Verify the customer.** Obtain customer assertions for at least two distinct fields among date of birth, email, phone number, and address. Look up the customer by a customer-supplied full name or email when available. Compare both assertions with the authoritative user record. Do not reveal missing values or treat a lookup result as the customer's assertion.
3. **Create the verification audit record.** After two fields match, obtain the current timestamp and call `log_verification` with the authoritative name, user ID, address, email, phone number, date of birth, and timestamp. Do not disclose account information if verification fails or cannot be logged.
4. **Verify ownership and requested card.** Call `get_credit_card_accounts_by_user` for the verified user. Find an account whose `user_id` is the verified user and whose `card_type` matches the requested card. If no exact match exists, explain that the requested card could not be confirmed; do not substitute another card.
5. **Retrieve data only after verification.** Call `get_credit_card_transactions_by_user` for the verified user. Keep only records with the requested `credit_card_type`, and ensure every displayed record has the verified user ID.
6. **Apply the requested date scope.** Use transaction dates as returned. For a monthly or statement-period request, use inclusive start and end dates supplied by the customer or known from the statement; do not guess a statement closing date. For a recent-only request, sort newest first and use the declared limit.
7. **Summarize deterministically.** Run `scripts/summarize_card_transactions.py` on the filtered raw records. Give the script the verified user ID as `expected_user_id`, the exact requested card type, and the intended date and limit settings.
8. **Present the result clearly.** State the card type, scope, number of transactions, whether the list was truncated, and a table with date, merchant descriptor, amount, category, and returned status. Include the current balance separately if it was returned by the account lookup. Describe totals as totals of displayed or scoped returned activity, never as the balance.
9. **Set reconciliation expectations.** Explain that a transaction review may not explain a current balance because supplied activity can omit payments, credits, refunds, interest, fees, balance transfers, pending items, and differently posted items. Do not label a charge unfamiliar or fraudulent based only on a merchant descriptor.

## Recent-list and expansion presentation

For an unspecified recent request, show the newest 10 matching transactions. If more matching transactions exist, explicitly say that the displayed activity is truncated, state the number shown and the number available, and offer to show the remainder.

If the customer asks for the remainder, do not repeat the first page as though it were new activity. Show only the not-yet-shown matching records, newest first. State that the expanded review now contains all returned matching transactions and is not truncated. A total for the expanded review must be labeled as the total for all returned matching activity; do not manufacture a total for an unstated scope.

A structured customer-facing report, when the interaction requires machine-readable output, should use fields that match the scope being reported:

- Initial page: `card_type`, `scope`, `transactions`, `displayed_activity_total`, `message`, and `note`.
- Remainder page: `card_type`, `additional_transactions`, `expanded_scope`, `expanded_activity_total`, `all_returned_transactions`, and `message`.

Each transaction row should contain `date` (`YYYY-MM-DD`), `merchant`, and `amount`; include category and status when returned. The `message` must distinguish a current balance from transaction activity, and the `note` must say that displayed or expanded activity is not the card balance.

## Unrecognized-charge and security handoff

If the customer identifies a particular returned transaction as unfamiliar, acknowledge each identified merchant, date if known, and amount. Do not open a dispute, block the card, cancel the card, or arrange a replacement automatically.

When the customer asks to cancel or replace a card, use unambiguous customer-facing language such as:

> “I cannot cancel or replace your card through this transaction-review service, and I will not open a dispute automatically. I can transfer you to a human security specialist who can help secure the card and discuss the next steps.”

Do not imply that cancellation, replacement, card blocking, or dispute filing has happened. If the customer accepts the offered human handoff, call `transfer_to_human_agents` with reason `fraud_or_security_concern`. Its summary must include the requested card type, the identified merchant names and amounts, that the customer says the charges were not made by them or are unrecognized, and their request to cancel, replace, or secure the card. After a successful transfer result, tell the customer that they have been transferred to a human agent or security specialist. If the customer does not accept, continue only with read-only review or request clarification.

## Handling incomplete or unsupported requests

- If identity is not verified, request another identity field and do not show transactions, balance, account lists, or card details.
- If the customer is not the account owner or lacks authority, decline disclosure and follow the organization’s authorized-party process if available.
- If there are no matching records, say no matching returned transactions were found for the specified card and scope; do not assert that no charge ever occurred.
- If a report is truncated, say so and offer the remainder, a narrower date range, a full statement-period review, or the supported export/report route when available.
- If transaction data are malformed, mixed across users, or cannot be confidently scoped to the requested card, do not present a computed total. Explain the data limitation and use supported tools or escalation procedures.
- If a requested security or dispute action is not available, state the limitation, do not claim completion, and offer the appropriate human handoff.

## Summarizer interface

`scripts/summarize_card_transactions.py` reads one JSON object from standard input and writes one JSON object to standard output. It uses only supplied records and performs no account action.

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

Before presenting a successful result, validate that `ok` is true, that every output row is for the requested card and verified user, that dates are within any requested range, and that the response labels a limited list as truncated. The executor, not the script, is responsible for identity verification, audit logging, tool calls, security handoff, and final customer-facing explanation.
