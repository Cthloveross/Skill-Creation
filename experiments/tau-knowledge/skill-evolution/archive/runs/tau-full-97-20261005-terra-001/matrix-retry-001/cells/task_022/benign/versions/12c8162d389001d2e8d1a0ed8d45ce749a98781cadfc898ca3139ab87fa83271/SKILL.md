---
name: credit-card-rewards-audit
version: 1.1.0
description: Audit posted credit-card transactions against documented Diamond Elite, Business Platinum, Business Silver, and EcoCard reward rules; report every incorrect stored reward and support corrections only after an approved dispute.
---

# Credit Card Rewards Audit

Use this Skill when a customer asks to review transaction-level credit-card rewards. It calculates whole-number stored points independently, identifies both under- and over-awards, and produces a structured audit suitable for review. It does not itself make banking-tool calls or change account data.

## Safe operating procedure

1. Before disclosing account-specific results or making a change, verify the customer by confirming two of date of birth, email, phone number, and address against the authoritative user lookup. Obtain the current time and record the successful verification with `log_verification` using every required field.
2. Retrieve the customer's transaction history and credit-card accounts with the normal banking tools. Transaction history supplies the individual entries; account opening dates are required for Business Silver promotion evaluation.
3. Convert the retrieved records to the input schema below and run `scripts/audit_rewards.py`.
4. Return the script's `findings` and `summary` as the structured audit result. Do not manually type or alter summary counts. In particular, `under_awarded_transactions`, `over_awarded_transactions`, `mismatches`, and `net_difference_points` must be taken directly from the final findings list.
5. `difference_points` means `expected_points - recorded_points`. A positive difference is an under-award and a negative difference is an over-award. `net_difference_points` has the opposite sign convention: it is `recorded_points - expected_points` summed across findings; negative means the recorded total exceeds the calculated total.
6. Do not update rewards or apply a statement credit merely because an audit found a mismatch. A transaction-reward correction is permitted only after the applicable cash-back dispute is resolved and approved.
7. If the customer wants to dispute a finding, provide `submit_cash_back_dispute_0589` for the customer to run with their own `user_id` and the selected `transaction_id`. If they can perform only one action at a time, offer only the first transaction they select.
8. For an approved dispute only: independently rerun this calculation; unlock `update_transaction_rewards_3847`; call it with the exact transaction ID and `new_rewards_earned` formatted as `"X points"`, where `X` is the calculated integer. Confirm the update in transaction history and retain calculation notes. Never rely on an `expected_rewards` value stored in a dispute record. Do not substitute a statement credit for the documented reward correction.

## Calculation rules

- All reward calculations truncate fractional points down per transaction; do not round to nearest.
- Stored points on cash-back cards correspond to one cent each. Thus a 5% rate is 5 points per dollar.
- Diamond Elite earns 5 points per dollar on eligible purchases.
- Business Platinum earns 4 points per dollar for Travel, Software, and Media/advertising merchant categories; all other purchases earn 1.5 points per dollar. An explicit `merchant_category_eligible: false` forces the standard rate.
- Business Silver earns 10 points per dollar for eligible Travel and Software purchases and 1 point per dollar otherwise. Concur, SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight always earn the standard rate.
- The Business Silver double-reward promotion applies only if the account opened from 2024-11-14 through 2025-11-14, inclusive, and the transaction occurred before the six-month anniversary of opening. It doubles the otherwise applicable rate.
- EcoCard earns 5 sustainability points per dollar for qualifying Green purchases and 1 point per dollar otherwise. Target, Walmart, Amazon, and ThredUp always earn the standard rate. An explicit `green_eligible` boolean is authoritative for ambiguous merchants; otherwise the supplied Green category is used. Tesla Supercharger is a known qualifying charging merchant.
- Cash equivalents, balance transfers, and fees earn zero. Returned/refunded transactions reverse the calculated original award. Pending, declined, cancelled, failed, reversed, voided, and unknown-status records are not audited.
- If merchant coding, Green eligibility, status, required dates, or an account opening date needed for Business Silver is unavailable, do not guess. The script reports that item in `not_audited`.

## Script interface

Run `scripts/audit_rewards.py` with one JSON object on standard input. The script writes exactly one JSON object to standard output and performs no network, banking, or account actions.

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

`merchant_category_eligible` and `green_eligible` are optional booleans. Omit them when no authoritative override exists. `accounts` may be empty when no Business Silver records are present.

Example:

```sh
python3 scripts/audit_rewards.py < audit_input.json
```

The output contains:

- `findings`: every and only audited transaction where expected and recorded points differ.
- `audited`: calculations for all auditable records, including correct entries.
- `not_audited` and `input_errors`: unsupported or incomplete records and malformed inputs.
- `summary`: counts and totals derived programmatically from `audited` and `findings`. Its invariant is `under_awarded_transactions + over_awarded_transactions == mismatches`; `correct_transactions + mismatches == audited_count`.

## Validation before action

Before presenting an audit, use the script output unchanged and ensure `summary.summary_consistent` is true. Before correcting an approved dispute, confirm the transaction appears exactly once in `audited`, does not appear in `not_audited`, has an integer `expected_points`, and is tied to documented approval. If any check fails, obtain authoritative data or leave the transaction pending review.
