---
name: credit-card-cash-back-audit
version: 1.0.0
description: Audit posted Silver Rewards Card and Business Silver Rewards Card transactions for cash-back discrepancies, calculate expected whole reward points from merchant category, exclusions, and the Business Silver promotion, and guide the customer to submit a transaction-specific dispute.
---

# Credit-card cash-back audit

Use this Skill when a customer believes credit-card cash back is missing, incorrect, or based on the wrong merchant category. It supports the **Silver Rewards Card** and **Business Silver Rewards Card** rules documented for this task. It audits posted transactions; it does not itself alter rewards or issue credits.

## Required runtime information

Obtain or use the supplied runtime records for:

- the customer identity and `user_id`;
- each relevant card's `card_type` and `date_of_account_open`; and
- transaction history containing `transaction_id`, card type, merchant, amount, transaction date, posted category, status, and `rewards_earned`.

If the customer has not yet been located, ask for their full name or email and use the corresponding normal lookup tool. Do not treat a database lookup as identity verification. If identity verification is required by the surrounding workflow, ask the customer to confirm two of the four identity fields (date of birth, email, phone, address), then call `log_verification` with the confirmed fields and the current timestamp. Do not disclose unconfirmed sensitive identity fields merely to obtain confirmation.

Only audit transactions that are posted/completed. Explain that rewards depend on the merchant's posted category; do not promise a travel or software rate if the supplied category does not support it. Missing account dates, amounts, categories, earned-points values, or an unsupported card type make the calculation indeterminate and should be reported as such rather than guessed.

## Calculation rules

Rewards stored as `points` for both supported cards are cash back at **1 point = $0.01**. Calculate reward points as:

`floor(transaction_amount_in_dollars × applicable_cash_back_percent)`

For example, a 4.0% rate corresponds to 4 points per dollar. Always truncate fractional points; never round to nearest.

### Silver Rewards Card

- Eligible posted categories `Travel` and `Software` earn 4.0%.
- Every other category earns 1.0%.

### Business Silver Rewards Card

- Eligible posted categories `Travel` and `Software` normally earn 10.0%.
- Every other category normally earns 1.0%.
- The following merchant brands are exclusions and use the standard rate even when the posted category is Travel or Software: Concur/SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight.
- A 2x promotion applies only when the account was opened from 2024-11-14 through 2025-11-14 and the transaction falls in the first six calendar months after that account opening. It doubles whichever normal rate applies, including the standard rate used for an exclusion. No enrollment is needed.

Use the packaged calculator rather than hand-calculating a long history. It uses exact decimal arithmetic, case-insensitive merchant-brand matching, and a calendar-month promotion end date.

## Run the calculator

Create an input JSON object from the runtime records and run:

```sh
python3 scripts/audit_rewards.py < audit-input.json
```

The script receives JSON on standard input and writes one JSON object on standard output.

Input schema:

```json
{
  "accounts": [
    {"card_type": "...", "date_of_account_open": "YYYY-MM-DD"}
  ],
  "transactions": [
    {
      "transaction_id": "...",
      "credit_card_type": "...",
      "merchant_name": "...",
      "transaction_amount": "...",
      "transaction_date": "YYYY-MM-DD",
      "category": "...",
      "status": "COMPLETED",
      "rewards_earned": "... points"
    }
  ]
}
```

Numeric amounts and earned points may instead be JSON numbers. The accounts field may use `account_id`, but no account identifier is needed for the calculation. A card type may also be provided as `card_type` on a transaction.

Output schema:

- `audited`: calculations for usable completed transactions, including expected and recorded points, applied rate, and eligibility rationale;
- `shortfalls`: records where recorded points are lower than expected, with the positive `point_difference` and `cash_difference`;
- `overawards`: records where recorded points exceed the documented calculation;
- `matches`: records with the correct whole-point result;
- `skipped`: records not safely calculable, with a reason;
- `summary`: counts of all four outcomes.

Before relying on output, ensure every transaction intended for review appears in one of these lists and that its card opening date was available. Reconcile script `expected_points` and `recorded_points` against the source transaction record. A positive point difference is also the statement-credit equivalent in cents.

## Customer response and dispute handling

Give a concise, customer-friendly review: identify each material shortfall by date, merchant, and transaction ID; state the received and expected points (and the dollar equivalent when useful); and explain the applicable category, exclusion, or promotion rule. Tell the customer that a result higher than the documented calculation is not a missing-cash-back shortfall. Do not characterize an uncertain merchant category as an error; explain that supporting receipts may help a category review.

For a specific underpaid transaction, first confirm the exact `transaction_id` with the customer. The required submission path is customer-operated:

1. Use `give_discoverable_user_tool` to provide `submit_cash_back_dispute_0589`.
2. Supply arguments as a JSON string containing the customer's own `user_id` and the confirmed `transaction_id`.
3. Tell the customer to run that tool for the specific purchase. Repeat separately for each transaction they choose to dispute.

Useful context for the customer to retain is the transaction date, merchant, amount, received points/cash back, expected points/cash back, category expectation, and receipts or confirmations.

Do **not** use `update_transaction_rewards_3847` merely because this audit finds a discrepancy. That internal update is only for an already resolved and approved dispute after independently recalculating the reward. Do not substitute a statement credit for the documented cash-back dispute process.
