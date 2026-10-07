---
name: verified-credit-card-transaction-report
description: Safely retrieve and present recent or filtered credit-card transactions for a verified account holder, including when a customer asks about an unexpectedly high card balance. Use for read-only card transaction reporting; do not use to make payments, alter accounts, block cards, or file disputes.
---

# Verified Credit-Card Transaction Report

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and prerequisites

This is a read-only reporting workflow. It may disclose account and transaction information only after identity verification and account ownership/authority checks. A name, user ID, or email used to locate a record is not by itself identity verification.

1. Identify the customer using an available lookup identifier. If no identifier is supplied, request one. If lookup returns zero or multiple plausible people, do not disclose account information; request a disambiguating identifier.
2. Verify identity by having the customer confirm **two of four** record fields: date of birth, email, phone number, or address. Do not supply those values as prompts or reveal them in order to obtain confirmation. Compare the supplied values to the retrieved record.
3. After two fields match, obtain the current timestamp and call `log_verification` with the complete retrieved identity record and timestamp. If verification fails, is incomplete, or cannot be logged, stop before accessing or disclosing card information.
4. Verify authority and ownership. For a self-service customer, use the verified identity plus the account record's matching user ID. For a third party, representative, or ownership mismatch, do not disclose records unless the normal banking authorization process establishes authority; otherwise transfer or follow the applicable escalation process.
5. Identify the requested card by exact card type or another unambiguous card detail. Retrieve the customer's credit-card accounts and require exactly one matching account. If more than one card can match, ask the customer to clarify; never choose based on balance or recency.
6. For this read-only report, product eligibility, fees, payment/credit limits, payment cutoffs, recipient details, and change confirmation are not applicable. Do not invent values for them. Confirm that the request is only to view transaction information. If the customer requests any payment, transfer, dispute, card block, profile change, or other action, stop and use that action's separate procedure and prerequisites.

## Retrieve and filter

1. Retrieve the verified customer's card accounts and transaction history using the normal banking tools.
2. Retain only transactions whose card type matches the selected card. Never mix transactions from other cards belonging to the same user.
3. For a request for a statement period or a specified date range, apply those inclusive dates. The available reporting capability supports filtering by date range, merchant, and amount. Ask a clarifying question when the requested period or filter is ambiguous.
4. For an unqualified request for “recent transactions,” present a clearly labeled, bounded list of the most recent transactions (default: 10), sorted newest first, and offer to show a date range or more records. Do not claim that this list is a full statement period.
5. Reports are for posted transactions. When the data source explicitly identifies posted transactions, include only those. If a transaction source provides a status but does not establish that status as posted, preserve and display the returned status rather than relabeling it. Explain that pending activity must be checked separately and does not appear in monthly reports until it posts.
6. Use `scripts/prepare_card_transaction_report.py` to deterministically select, filter, sort, format, and total records after verification. The script does not verify identity and must not be run as a substitute for the prerequisite checks.

## Present the result

State the selected card and, if retrieved, its current balance as of the lookup. List each displayed transaction with date, merchant descriptor, amount, category when available, and returned status. Include the number of displayed items and the sum of those displayed items only. Explicitly say that this displayed-item sum is not a balance reconciliation and may not equal the current balance because statement periods, prior balances, payments, credits, fees, refunds, interest, and transactions outside the selected range can affect a balance.

Offer supported next steps: a different date range, merchant, or amount filter; individual transaction review; adding notes/tags when that capability is available; or exporting the monthly activity to CSV/PDF through the account's Reports or Statements section. If the customer reports an unfamiliar item, first review its posted date and merchant descriptor before beginning any dispute workflow.

## Script interface and validation

Run the helper with JSON on standard input and consume its JSON standard output:

```json
{
  "accounts": [{"account_id": "...", "user_id": "...", "card_type": "...", "current_balance": "$0.00"}],
  "requested_card_type": "...",
  "transactions": [{"credit_card_type": "...", "transaction_date": "MM/DD/YYYY", "merchant_name": "...", "transaction_amount": "$0.00", "status": "..."}],
  "limit": 10,
  "start_date": "optional MM/DD/YYYY or YYYY-MM-DD",
  "end_date": "optional MM/DD/YYYY or YYYY-MM-DD",
  "merchant_contains": "optional text",
  "min_amount": "optional amount",
  "max_amount": "optional amount",
  "posted_statuses": ["optional explicit source-defined posted statuses"]
}
```

`accounts`, `requested_card_type`, and `transactions` are required. Date, merchant, amount, and status fields should be passed from the banking results without alteration. `posted_statuses` is optional and should be supplied only when the source explicitly defines which returned statuses are posted. If omitted, the script does not infer that a status is posted.

A successful result has `ok: true`, exactly one `selected_account`, `transactions` sorted newest first, and `shown_total_amount`. Before presenting it, verify that the selected account belongs to the verified user, `transaction_count` equals the length of `transactions`, every transaction has the selected card type, and errors/warnings have been addressed. On `ok: false`, do not improvise a selection; resolve the reported ambiguity, malformed data, or filter problem with the customer or source system.

Example invocation (with runtime-supplied records, not hardcoded customer data):

```sh
python3 scripts/prepare_card_transaction_report.py <<'JSON'
{"accounts": [...], "requested_card_type": "...", "transactions": [...], "limit": 10}
JSON
```
