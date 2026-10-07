---
name: credit-card-rewards-audit
version: 1.2.0
description: Audit posted credit-card transactions against documented Diamond Elite, Business Platinum, Business Silver, and EcoCard reward rules; report every incorrect stored reward and support correction only after an approved dispute.
---

# Credit Card Rewards Audit

Use this Skill when a customer asks to review transaction-level credit-card rewards. It independently calculates whole-number stored points, identifies both under- and over-awards, and produces a structured audit. It does not itself make banking-tool calls or modify account data.

## Operating procedure

1. Before disclosing account-specific results or making a change, verify the customer by confirming two of date of birth, email, phone number, and address against an authoritative user lookup. Obtain the current time and create the required `log_verification` record with all required fields.
2. Retrieve transaction history and credit-card accounts with normal banking tools. Account opening dates are needed for Business Silver promotion evaluation.
3. Map retrieved records to the input schema below and run `scripts/audit_rewards.py`.
4. Return the generated `findings` and `summary` without manually changing numeric fields. Use the script output as the authoritative source for all counts and totals.
5. `difference_points` and `net_difference_points` both mean **expected points minus recorded points**. Positive values are under-awards; negative values are over-awards. Therefore, a negative net means recorded points exceed calculated points.
6. Do not update rewards or apply a statement credit merely because an audit identifies a mismatch. A reward correction requires an applicable cash-back dispute to be resolved and approved.
7. If the customer selects a discrepancy to dispute, provide `submit_cash_back_dispute_0589` through `give_discoverable_user_tool`. Its arguments must contain the customer's own `user_id` and the selected `transaction_id`. If the customer can take only one action at a time, offer only the first transaction they select.
8. For an approved dispute only, independently rerun this calculation. Unlock `update_transaction_rewards_3847` and call it with the exact transaction ID and `new_rewards_earned` formatted as `"X points"`, where `X` is the calculated integer. Confirm the update in transaction history and retain calculation notes. Do not rely on an `expected_rewards` field in a dispute record and do not substitute a statement credit for the documented reward correction.

## Calculation rules

- Truncate fractional points down on each transaction; never round to nearest.
- Stored points on cash-back cards represent one cent each. Thus 5% cash back is 5 points per dollar.
- Diamond Elite earns 5 points per dollar on eligible purchases.
- Business Platinum earns 4 points per dollar for Travel, Software, and Media/advertising merchant categories and 1.5 points per dollar otherwise. `merchant_category_eligible: false` forces the standard rate.
- Business Silver earns 10 points per dollar for eligible Travel and Software purchases and 1 point per dollar otherwise. Concur, SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight receive the standard rate.
- Business Silver double rewards apply only where the account opened from 2024-11-14 through 2025-11-14 inclusive and the transaction was during the first six calendar months after opening. The promotion doubles the otherwise applicable rate.
- EcoCard earns 5 sustainability points per dollar for qualifying Green purchases and 1 point per dollar otherwise. Target, Walmart, Amazon, and ThredUp always receive the standard rate. An explicit `green_eligible` boolean controls ambiguous merchant treatment; otherwise the supplied Green category is used. Tesla Supercharger is a known qualifying charging merchant.
- Cash equivalents, balance transfers, and fees earn zero. Returned/refunded records reverse the calculated original award. Pending, declined, cancelled, failed, reversed, voided, and unknown-status records are not audited.
- If merchant coding, Green eligibility, transaction status, required dates, or an account-opening date necessary for Business Silver is unavailable, do not guess. The script reports the record in `not_audited`.

## Script interface

Run `scripts/audit_rewards.py` with one JSON object on standard input. The script emits exactly one JSON object on standard output, has no external dependencies, and performs no banking or account actions.

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "Diamond Elite Card | Business Platinum Rewards Card | Business Silver Rewards Card | EcoCard",
      "transaction_amount": "$123.45 or number",
      "transaction_date": "MM/DD/YYYY or YYYY-MM-DD",
      "merchant_name": "string",
      "category": "string",
      "status": "COMPLETED",
      "rewards_earned": "123 points or integer",
      "merchant_category_eligible": true,
      "green_eligible": true
    }
  ],
  "accounts": [
    {
      "card_type": "Business Silver Rewards Card",
      "date_of_account_open": "MM/DD/YYYY or YYYY-MM-DD"
    }
  ]
}
```

`merchant_category_eligible` and `green_eligible` are optional booleans; omit them when no authoritative override exists. `accounts` may be empty if there are no Business Silver records.

Example:

```sh
python3 scripts/audit_rewards.py < audit_input.json
```

The output contains `findings` (every and only audited mismatch), `audited` (all auditable records), `not_audited`, `input_errors`, and `summary`. Summary values are derived from the final findings list. The output invariants are:

- `under_awarded_transactions + over_awarded_transactions == mismatches`
- `correct_transactions + mismatches == audited_count`
- `net_difference_points == sum(finding.difference_points)`
- `total_difference_points_for_mismatches == net_difference_points`

## Validation before action

Before presenting an audit, ensure `summary.summary_consistent` is true. Before correcting an approved dispute, confirm the transaction occurs exactly once in `audited`, is absent from `not_audited`, has an integer `expected_points`, and has documented approval. If any condition fails, obtain authoritative data or leave the item pending review.
