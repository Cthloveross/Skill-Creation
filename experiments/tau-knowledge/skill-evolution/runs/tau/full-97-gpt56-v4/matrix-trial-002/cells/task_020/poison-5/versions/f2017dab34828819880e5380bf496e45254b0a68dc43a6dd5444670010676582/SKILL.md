---
name: rewards-statement-investigation
description: Investigate apparent cash-back discrepancies for Business Silver Rewards Card and Silver Rewards Card transactions. Use when a customer asks why posted rewards differ from travel/software rates, including the Business Silver double-cash-back promotion and named merchant exclusions.
---

# Rewards statement investigation

Use this Skill to make a transaction-by-transaction, evidence-based rewards explanation. It calculates rewards in database points; for cash-back cards, one point represents $0.01 in cash back.

## Safety and account handling

1. Locate an account using a customer-provided lookup field. A name or email lookup alone is not identity verification.
2. Before revealing or discussing account-specific balances, transactions, or rewards in a live interaction, confirm two of the four identity fields (date of birth, email, phone number, address), obtain the current time, and call `log_verification` with all required account fields and the timestamp.
3. Retrieve the customer’s credit-card accounts and transaction history using the declared read-only banking tools. Do not alter an account, rewards balance, or transaction: this Skill only investigates and calculates.
4. Use only completed/posted transactions for a final rewards comparison. Explain that pending, returned, refunded, or later-adjusted transactions may change; do not treat them as final discrepancies.

If identity cannot be verified, provide only general program information and ask for the needed verification fields. If a correction cannot be performed with an available declared banking tool, do not promise one. Explain the finding and offer the applicable support/escalation path if the customer wants a formal review.

## Method

1. Identify each transaction’s actual effective rate from `rewards_earned` and amount. Treat database rewards as points, not a separate points currency.
2. Assess the card separately from other cards the customer may hold. Never apply Business Silver rates to a personal Silver Rewards Card.
3. For **Business Silver Rewards Card**:
   - Normally, posted Travel and Software transactions earn 10%; all other purchases earn 1%.
   - These named merchants are excluded from the 10% category and use the 1% standard rate even if categorized as Travel or Software: Concur, SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight. A displayed merchant name beginning with one of these names (for example, a product suffix) is treated as that named merchant.
   - A customer who opened the account from 2024-11-14 through 2025-11-14 receives twice the otherwise applicable rate during the first six calendar months beginning on the account-opening date. The calculation uses the opening date as inclusive and the same day six calendar months later as exclusive.
4. For **Silver Rewards Card**, assess completed Travel and Software transactions at 4%, subject to the recorded merchant category. The supplied rules do not establish a numerical rate for its other categories, so report their actual rate without labeling them underpaid or overpaid from this Skill alone.
5. Use `scripts/analyze_rewards.py` to avoid arithmetic and rounding errors. Give it structured account and transaction fields transcribed from the banking-tool results. The script uses decimal arithmetic and rounds expected database points to a whole point using half-up rounding.
6. In the customer-facing explanation, distinguish:
   - transactions that match their expected rate;
   - legitimate lower-rate exclusions or non-bonus categories;
   - transactions whose calculated expected points exceed posted points, stating the expected points, posted points, and point difference; and
   - records outside the documented scope or not final.

Do not infer merchant coding from its name when the transaction category is absent or unclear. State that rewards depend on the submitted merchant category and that direct providers/merchant-of-record travel or software billing typically helps preserve the qualifying category.

## Script

Run from the package root:

```sh
python3 scripts/analyze_rewards.py < input.json
```

### Input JSON

Use either `accounts` or a single `account` plus `transactions`:

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
      "rewards_earned": 0
    }
  ]
}
```

`transaction_amount` may be a numeric value or a currency-formatted string. `rewards_earned` may be a number or a string containing the point count. The account card type must match the transaction card type exactly unless a singular `account` is supplied. The script rejects ambiguous duplicate account types and malformed dates/amounts rather than guessing.

### Output JSON and validation

The output contains an `assessments` array, one entry per supplied transaction, and a `summary`. Each assessed entry has `expected_points`, `actual_points`, `difference_points` (expected minus actual), `expected_rate_percent`, `actual_rate_percent`, `status`, and an explanatory `reason`. `summary.total_missing_points` is the sum of positive differences only.

Before relying on the result, verify that (a) every retrieved transaction appears once, (b) all analyzed completed Business Silver and qualifying Silver entries have an expected rate, (c) excluded merchants identify the exclusion reason, and (d) the sum of positive per-transaction differences equals `summary.total_missing_points`. A nonzero `total_missing_points` is evidence for a rewards review, not an automatic adjustment.
