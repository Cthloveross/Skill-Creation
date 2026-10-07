---
name: credit-card-rewards-audit
description: Audit posted Silver Rewards Card and Business Silver Rewards Card transaction rewards against the documented rates, business-card promotional window, and documented Business Silver merchant exclusions. Use for a customer asking why cash-back/reward points look incorrect.
---

# Credit-card rewards audit

Use this Skill to perform a read-only, transaction-level rewards review. It is designed for cases where transaction history supplies the merchant category, transaction date, amount, status, and rewards earned.

## Policy encoded by this Skill

- Database `rewards_earned` units are points. For these cash-back cards, **100 points = $1.00**.
- **Silver Rewards Card:** 4% for transactions categorized as Travel or Software; 1% for other purchases.
- **Business Silver Rewards Card:** 10% for eligible Travel or Software purchases; 1% for other purchases.
- The Business Silver double-cash-back promotion applies only when the account was opened from 2024-11-14 through 2025-11-14. It doubles the otherwise applicable Business Silver rate for the first six calendar months after account opening. The promotion is not assumed to apply on or after the six-month anniversary.
- On Business Silver, Concur, SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight earn the standard 1%; during an active qualifying promo window this standard rate is doubled to 2%.
- Qualification depends on the merchant category submitted by the merchant. This audit uses the supplied `category` as that classification. It cannot establish whether a missing or inaccurate category should be changed.

The script uses the category values `Travel` and `Software` case-insensitively. It reports unsupported card types and non-completed transactions as not auditable instead of guessing.

## Procedure

1. Identify the customer with the normal banking lookup tools. For a broad review, retrieve all credit-card accounts and all credit-card transactions for that user. Do not request identity verification merely to provide this read-only explanation; obtain and log the required verification only if a later tool/action requires it.
2. Build JSON containing `accounts`, `transactions`, and an optional `as_of_date` and run:

   ```bash
   python3 scripts/audit_rewards.py <<'JSON'
   {"accounts": [{"card_type": "Business Silver Rewards Card", "date_of_account_open": "YYYY-MM-DD"}], "transactions": [{"credit_card_type": "Business Silver Rewards Card", "merchant_name": "Merchant", "transaction_amount": "0.00", "transaction_date": "YYYY-MM-DD", "category": "Travel", "status": "COMPLETED", "rewards_earned": 0}]}
   JSON
   ```

   The script reads one JSON object from standard input and emits one JSON object to standard output. It requires account `card_type` and `date_of_account_open`, plus transaction `credit_card_type`, `merchant_name`, `transaction_amount`, `transaction_date`, `category`, `status`, and `rewards_earned`. `transaction_id` is optional but should be included when available. Amounts may be JSON numbers or decimal strings. `as_of_date` is accepted for traceability but does not alter calculations.
3. Review `audited` rows. `outcome: match` means the recorded points equal the calculated points. `outcome: discrepancy` identifies a completed transaction whose recorded points differ, with `difference_points = expected - recorded`; a positive value is a shortfall and a negative value is an apparent over-credit. `outcome: not_auditable` explains why no conclusion was reached.
4. Explain the result in cash and points, naming only the transactions with discrepancies unless the customer asks for a full itemization. State the applicable rate and, where useful, the reason (such as a documented exclusion or the promotional window ending). Make clear that points equal one cent on these cash-back cards.
5. Do not claim that a category review, correction, or credit was submitted unless a declared banking tool actually completed it. If the customer asks for a correction and no authorized correction workflow is available, say that the review identifies the transaction(s) for rewards support; use a human transfer only when an applicable transfer policy or a customer request requires it.

## Validation

Before relying on the output, ensure that every row expected to be reviewed is either in `audited` or `input_errors`. Check that completed rows have a valid date, nonnegative amount, and integer recorded points. A normal rewards balance is not proof that the transaction-level sum is correct: balances can include activity, reversals, or redemptions not represented in the supplied history, so do not label a balance mismatch as an error from this audit alone.
