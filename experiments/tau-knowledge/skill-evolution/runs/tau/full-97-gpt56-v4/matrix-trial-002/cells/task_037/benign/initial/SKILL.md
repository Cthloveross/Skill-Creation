---
name: silver-card-transaction-review
description: Safely locate a customer's requested credit-card account and present a clear, date-ordered recent-transaction review. Use for read-only requests to see charges, investigate a higher-than-expected balance, or ask whether recent card activity is recognized.
---

# Credit-card transaction review

Use this Skill for a read-only explanation of charges on a specifically named card. It does not make account changes, open a dispute, or label a transaction fraudulent.

## Required information and lookup sequence

1. Identify the customer using the identifier they supply. A full name may be sent to `get_user_information_by_name`; an email may be sent to `get_user_information_by_email`. Use exact values when the tool specifies case sensitivity.
2. If the lookup is ambiguous or returns no customer, ask for an email address or full name rather than guessing.
3. Retrieve the customer's accounts with `get_credit_card_accounts_by_user` and locate the account whose `card_type` exactly matches the card requested. Do not substitute a similarly named product.
4. Retrieve transactions using `get_credit_card_transactions_by_user`, then retain only records whose `credit_card_type` matches the selected account's `card_type`.
5. Use the supplied conversation observations when they already contain successful read-only lookups; do not repeat them merely to reproduce information. Obtain fresh information only when it is absent, stale, or the user changes the request.

A customer name or email used as a lookup locator is not by itself a completed identity verification. Do not claim verification or call `log_verification` unless the customer has confirmed at least two of the four required identity fields (date of birth, email, phone number, address). If a later requested action requires verification, collect the confirmations, obtain the current timestamp with `get_current_time`, and then call `log_verification` with all required fields.

## Produce the review

Create structured transaction objects from the tool response and run:

```text
python3 scripts/transaction_report.py <<'JSON'
{"card_type":"<selected card type>","transactions":[{"credit_card_type":"...","transaction_date":"MM/DD/YYYY","merchant_name":"...","transaction_amount":"$0.00","category":"...","status":"..."}],"limit":10}
JSON
```

The script reads one JSON object from standard input and emits one JSON object to standard output. Inputs are:

- `card_type` (string): requested account product name.
- `transactions` (array of objects): transaction records from the normal banking tool.
- `limit` (optional positive integer): number of newest matching records to present; defaults to 10.

The output includes `recent_transactions` newest-first, `matching_transaction_count`, and money strings for `recent_total` and `all_matching_total`. Invalid dates or amounts are reported in `warnings` rather than silently treated as valid values.

In the response:

- Confirm the selected card product and, when available, state its current balance separately from transaction totals. A transaction-history total is **not** a reconciliation of the current balance because payments, credits, statement cycles, interest, and omitted history may affect it.
- Give the most recent records in descending date order with date, merchant, amount, and optionally category/status. State how many matching transactions exist and that additional older matching transactions can be shown when only a recent subset is listed.
- Preserve the amounts, dates, merchant names, and status exactly as returned. Do not infer that a completed charge is unauthorized or that it caused the balance.
- If the customer identifies a charge they do not recognize or explicitly disputes billing, acknowledge the concern and use the applicable dispute/fraud workflow available in the runtime. If no such workflow is available and resolution requires a specialist, transfer with the matching supported reason (for example, `fraud_or_security_concern` or `complex_billing_dispute`) and summarize the identified charge and completed read-only review.
- If no matching account or transactions exist, state that plainly and offer to check the card name or another account; never fabricate a charge list.

Do not expose unnecessary profile fields (address, date of birth, phone number, or email) in the customer-facing response.

## Validation checklist

Before replying, verify that every displayed record has the selected card type, that ordering is newest to oldest, and that money totals were computed only from displayed/matching valid amounts. Keep the account balance distinct from the transaction total. Make no state-changing banking call for a request that only asks to view transactions.
