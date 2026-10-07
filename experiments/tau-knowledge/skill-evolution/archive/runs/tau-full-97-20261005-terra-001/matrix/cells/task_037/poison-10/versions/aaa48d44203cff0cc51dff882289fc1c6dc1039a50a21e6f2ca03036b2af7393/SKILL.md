---
name: verified-credit-card-transaction-review
description: Safely verify a cardholder and present a filtered, date-ordered review of recent posted credit-card transactions, including reported rewards context. Use for requests to view, reconcile, or question charges or balances on a specified credit card.
---

# Verified Credit-Card Transaction Review

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

This Skill is for read-only transaction review. It does not file disputes, alter accounts, block cards, or make payments.

## Required checks

1. Treat a name or email supplied to locate a record as a lookup aid, not identity verification.
2. Obtain and compare at least two of these four identity fields against the customer record: date of birth, email, phone number, and address.
3. After two fields match, get the current time and call `log_verification` with the complete user record and that timestamp. Do not disclose account balances, card details, or transactions before verification succeeds.
4. Fetch the user's credit-card accounts with `get_credit_card_accounts_by_user`. Confirm that the requested card type exists and belongs to the verified user. If several accounts could match the request, ask the customer to identify the intended card; never infer it from a different card's transactions.
5. Fetch transactions using `get_credit_card_transactions_by_user`, then include only records whose `credit_card_type` exactly matches the confirmed card. Never expose records for other cards returned by this user-level query.

If verification, authority, ownership, or exact card matching cannot be established, explain what is needed and stop. Do not guess from a partial name, an account identifier volunteered without verification, or transactions from another card.

## Review procedure

1. Clarify the desired period if the customer names one. For an unspecified request for “recent” transactions, state the number and period you will show (normally the most recent 10 posted transactions available) and offer to narrow it by date, merchant, or amount.
2. Restrict the display to posted/completed records. If the transaction source distinguishes pending items, label them separately rather than presenting them as posted statement charges.
3. Sort by transaction date descending. Show, for each displayed transaction: posted date, merchant descriptor, amount, category when supplied, status, and reported rewards when supplied. Include the current card balance only if it came from the confirmed card account record, label it as the current balance, and do not imply it equals the displayed transaction total.
4. Use `scripts/filter_card_transactions.py` when the records are available as JSON. It produces a validated exact-card, date-filtered, descending list and total. Its computed total applies only to the selected rows; do not describe it as a statement balance, amount due, or full-period total unless the selected period is the statement period.
5. For a Silver Rewards Card, travel and software/SaaS purchases may earn the enhanced 4.0% back rate when eligible and after posting. Merchant-submitted classification controls eligibility; third-party processors can change classification. State reported rewards as provided and do not recalculate them or promise an adjustment. Gift cards, person-to-person payments, fees, interest, bank-charged insurance premiums, and refunded/returned purchases typically do not qualify.
6. If the customer recognizes no transaction, first review the posted date and merchant descriptor with them. Ask which specific transaction is unfamiliar before beginning any dispute workflow. A dispute, blocking, or any account change requires its own applicable prerequisite and confirmation checks.

## Reports and filtering

Monthly reporting supports viewing transaction dates, merchant descriptors, and posted amounts. Offer available filters by date range, merchant, and amount. For records or bookkeeping, explain that the customer can open Reports or Statements, select the desired current or past statement period, apply filters, and download a CSV or PDF. Transactions appear in reports after they post; for apparently missing activity, check pending activity.

## Script interface

Run:

```text
run_skill_script(relative_path="scripts/filter_card_transactions.py", input_json={...})
```

The script reads one JSON object from standard input and writes one JSON object to standard output.

Input schema:

- `transactions` (required): array of transaction objects with `credit_card_type`, `transaction_date`, and `transaction_amount`. It normally also contains `merchant_name`, `status`, `category`, `rewards_earned`, and `transaction_id`.
- `card_type` (required): exact confirmed card type to retain.
- `limit` (optional): positive integer count of newest records; omit for all matches.
- `start_date` / `end_date` (optional): inclusive dates in `MM/DD/YYYY` or `YYYY-MM-DD` format.
- `merchant_contains` (optional): case-insensitive merchant substring.
- `min_amount` / `max_amount` (optional): inclusive monetary bounds, supplied as a number or a string such as `$12.34`.
- `posted_statuses` (optional): list of allowed status strings. The default is `["COMPLETED", "POSTED"]`.

Output schema: `{ "ok": true, "filters": {...}, "matched_count": integer, "displayed_count": integer, "display_total": "12.34", "transactions": [...] }`. On invalid input, it returns `{ "ok": false, "error": "..." }`. Each returned transaction retains its original supplied fields and adds normalized `parsed_date` and `parsed_amount` fields for transparent review.

Validate that the output is `ok`, every returned record has the confirmed card type, dates are descending, and the displayed count respects `limit`. If the result is empty, say that no posted matching transactions were found for the selected filters; do not claim there were no pending transactions or no activity outside the selected period.

## Completion response

Give a concise, readable list followed by the selected-row total and any important scope note (such as “posted transactions shown” or the requested date range). Invite the customer to identify a charge to review further or to request a different date, merchant, or amount filter. Do not claim that a balance discrepancy is resolved solely because transactions were displayed.
