---
name: platinum-rewards-annual-fee-rebate-review
description: Review a Platinum Rewards Card annual-fee rebate inquiry by selecting the latest completed fee-billed cardmember year, assigning posted eligible transactions to monthly-anniversary windows, and explaining whether every window met the monthly threshold. Use for account-specific rebate-status questions; do not use it to initiate a credit or change an account.
---

# Platinum Rewards annual-fee rebate review

## Policy applied

For this product, the rebate is **$150** and the monthly threshold is **$7,500**. A cardmember must meet the threshold in **every** one of 12 consecutive monthly anniversary windows. One deficient window disqualifies the entire year; there is no prorated rebate.

A window starts on the account-opening day-of-month and ends the day before the next monthly anniversary. Use the **posting date**, not authorization date or statement cycle. Include net posted purchases (including authorized-user, virtual-card, and international purchases) and subtract returns/refunds/credits in the window in which they post. Exclude fees, interest, balance transfers, cash advances, cash-equivalent/funding/P2P transactions coded as cash equivalents, and unresolved disputes.

The promotional first-year waiver only applies if the application was submitted and approved between 2024-06-01 and 2024-12-31. A waived first year has no rebate. For a non-waived, eligible year, the credit posts after that year's annual fee is billed. The account must not have been closed or product-changed before evaluation/posting.

Policy sources: `doc_credit_cards_platinum_rewards_card_010`, `doc_credit_cards_platinum_rewards_card_007`, `doc_credit_cards_platinum_rewards_card_009`, and `doc_credit_cards_platinum_rewards_card_002`.

## Workflow

1. Identify the customer and select only their **Platinum Rewards Card**. Do not combine spending from another card. Obtain the opening date, account status, and posted transaction history through the normal banking tools.
2. Treat a name, email, or user ID used to locate an account as an account locator, not evidence to disclose unnecessary PII. Follow any applicable identity-verification workflow before disclosing protected account details; when two identity fields have been confirmed, call `log_verification` with the complete required record and the current time.
3. Determine the latest **fully completed** 12-window cardmember year as of the current date. Do not assess the current incomplete year as a final rebate result. Skip the opening-year interval only when the promo waiver actually applies. For older accounts, do not assume a current promotion applies retroactively.
4. Normalize transaction data into the script input. Confirm that the date field supplied is a posting date (or that the transaction-history `transaction_date` represents the posted date). Supply an explicit eligibility field or transaction type/coding when available. Do not silently classify an ambiguous cash-like or disputed transaction as a purchase.
5. Run `scripts/evaluate_rebate.py`. It produces the selected period, all 12 inclusive windows, totals, threshold gaps, and a spend qualification result.
6. Check the output before responding: there must be exactly 12 contiguous windows, each transaction must appear at most once, the selected end date must be before the as-of date, and all counted rows must be eligible posted transactions. If the script returns `needs_information` or `unsupported`, obtain the missing fact or explain that a definitive result cannot be confirmed.
7. Reply clearly and concisely: state the evaluated date range, the $7,500-each-window rule, the result, and (if qualified) that the $150 credit is applied after the annual fee is billed. If not qualified, identify only the deficient window(s) and totals. State relevant limitations, including incomplete current years, missing posting-date confirmation, waiver status, or closure/product-change information. Do not promise a credit or perform a bank action; this review only determines eligibility based on available records.

## Calculator interface

Run:

```sh
python3 scripts/evaluate_rebate.py < input.json
```

The program receives one JSON object on stdin and emits one JSON object on stdout.

Required fields:

- `account_open_date`: `YYYY-MM-DD` or `MM/DD/YYYY`.
- `as_of_date`: date on which the review is made.
- `transactions`: array of objects containing an amount and either `posting_date`, or `transaction_date` when `transaction_date_is_posting_date` is `true`.

Useful optional fields:

- `threshold` and `rebate_amount` (default to 7500.00 and 150.00).
- `card_type`: filters records whose `credit_card_type`/`card_type` is present and differs.
- `first_year_waived`: boolean, only after verifying promo eligibility.
- `account_active` and `product_changed_before_evaluation`: booleans. Set these from reliable account data rather than guessing.
- `transaction_date_is_posting_date`: boolean. This must be true only when the supplied transaction-date field is known to be the posting date.
- Per transaction: `eligible` (preferred explicit boolean), `transaction_type`, `category`, `status`, and an amount such as a number or `$1,234.56`. Negative eligible amounts reduce the relevant window total.

The script recognizes clearly excluded type/category labels and unresolved dispute statuses. With no explicit `eligible` value, it counts only completed/posted purchase-like entries and leaves ambiguous coding out, reporting it in `excluded_or_ambiguous_transactions`. Review those rows before giving a definitive answer.

The monthly-anniversary policy does not specify how to handle an opening day that does not exist in a later month (for example, a 31st). The script returns `unsupported` rather than inventing a clamping rule. Escalate to the product's official calculation rule in that circumstance.

A `qualified` spend result is still contingent on the selected year being fee-billed and on the account remaining active and unchanged through evaluation/posting. A `not_qualified` result is final for that cardmember year once any window is below threshold.
