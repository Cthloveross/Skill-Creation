---
name: rewards-discrepancy-audit
version: 1.0.0
description: Audit posted Business Silver Rewards Card and Silver Rewards Card transactions against documented cash-back rules, identify reward shortfalls, and safely guide a customer-service response or escalation.
---

# Rewards Discrepancy Audit

Use this Skill when a customer says that cash back or rewards on a Silver Rewards Card or Business Silver Rewards Card appears incorrect. It calculates expected *points* from posted transactions, where one point is one cent for these cash-back cards, and distinguishes legitimate exclusions from discrepancies.

## Privacy and support workflow

1. Locate the customer and their card accounts with the normal banking lookup tools.
2. Before revealing transaction-level account information or taking account-specific action, verify two of the four registered identity fields (date of birth, email, phone, address). After the customer confirms two matching fields, obtain the current timestamp and call `log_verification` with all required account fields and that timestamp.
3. Retrieve all credit-card accounts and transaction history for the verified user. Audit only transactions whose status is `COMPLETED` (posted). Do not treat pending, returned, or refunded transactions as earned rewards.
4. Convert the lookup results into the JSON schema below and run `scripts/reward_audit.py`. The script is analytical only: it never changes rewards or performs banking actions.
5. Explain the result clearly in cash and points. State that the database's points on these cards represent cash back at **100 points = $1.00**.
6. If discrepancies exist and no documented rewards-adjustment tool is available, do not claim that an adjustment was posted. Transfer the case using `transfer_to_human_agents` with reason `complex_billing_dispute`, including the affected transaction IDs, expected and recorded points, and total shortfall. The rewards review team can verify merchant coding and apply any warranted correction.
7. If no discrepancy exists, explain the applicable rate and any exclusion. Offer a merchant-category review if the customer believes the recorded category is wrong.

## Policy encoded by the auditor

- **Business Silver Rewards Card:** 10% on eligible Travel or Software purchases and 1% otherwise.
- Business Silver excludes Concur, SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight from the 10% category; these earn the 1% base rate.
- The Business Silver double-cash-back offer applies only to accounts opened from 2024-11-14 through 2025-11-14. It doubles both the 10% and 1% base rates for the first six calendar months beginning on the account-open date. The opening date is included and the six-month anniversary is excluded.
- **Silver Rewards Card:** 4% on eligible Travel or Software purchases and 1% otherwise. No double-cash-back offer is assumed for this card.
- Eligibility relies on the posted merchant category. The script treats category values `Travel` and `Software` case-insensitively as qualifying categories; ambiguous or missing categories must be reviewed rather than assumed eligible.
- Expected rewards are rounded to the nearest whole point using conventional half-up rounding, consistent with transaction records that store whole points.

## Script input and output

Run, for example:

```sh
python scripts/reward_audit.py <<'JSON'
{"accounts":[{"card_type":"Business Silver Rewards Card","date_of_account_open":"YYYY-MM-DD"}],"transactions":[{"transaction_id":"...","credit_card_type":"Business Silver Rewards Card","merchant_name":"...","transaction_amount":"12.34","transaction_date":"YYYY-MM-DD","category":"Travel","status":"COMPLETED","rewards_earned":0}]}
JSON
```

Input is one JSON object with:

- `accounts`: array of objects containing `card_type` and `date_of_account_open` (`YYYY-MM-DD`).
- `transactions`: array of objects containing `transaction_id`, `credit_card_type`, `merchant_name`, `transaction_amount`, `transaction_date`, `category`, `status`, and `rewards_earned`.
- Optional `as_of_date` is accepted for recording context but does not alter the audit of posted historical transactions.

The script emits JSON with `audited_transactions`, `discrepancies`, `review_needed`, `summary`, and `errors`. Each audited transaction provides the applied base rate, promotion multiplier, expected points, actual points, and point/cash difference. A positive `point_shortfall` means the recorded reward is below the documented calculation. `review_needed` identifies records the script deliberately did not judge because required dates, amounts, account data, or category information were absent or invalid.

## Validate before communicating

- Confirm every completed transaction for one of the two supported cards appears either in `audited_transactions`, `review_needed`, or `errors`.
- Confirm a Business Silver promotion is tied to the individual account's opening date, never simply to the current date.
- Check each named excluded merchant before calling a Software purchase eligible for 10%.
- Reconcile `summary.total_expected_points - summary.total_actual_points` with the sum of audited differences. Use the script's `total_positive_shortfall_points` for the amount that may warrant correction; do not offset a shortfall with an apparent over-credit.
- Mention that merchant category and posting status control the final review. Preserve receipts and confirmations if a category review is needed.
