---
name: credit-card-cash-back-audit
description: Audit posted Business Silver Rewards Card and Silver Rewards Card transactions against the documented cash-back rates, promotion, exclusions, points conversion, and floor-rounding policy. Use when a customer reports missing or incorrect cash back and transaction/account data are available.
---

# Credit-card cash-back audit

Use this Skill to produce a transaction-level, explainable rewards review. It does not alter rewards, submit disputes, or reconcile a displayed account points balance to activity that may predate the supplied transaction history or include redemptions/adjustments.

## Required runtime data

Obtain the relevant customer's credit-card accounts and transaction history using the normal read-only banking tools. Supply those records to `scripts/audit_rewards.py` as JSON.

The script accepts:

```json
{
  "accounts": [
    {
      "card_type": "Business Silver Rewards Card",
      "date_of_account_open": "YYYY-MM-DD"
    }
  ],
  "transactions": [
    {
      "transaction_id": "...",
      "credit_card_type": "Business Silver Rewards Card",
      "merchant_name": "...",
      "transaction_amount": "12.34",
      "transaction_date": "YYYY-MM-DD",
      "category": "Travel",
      "status": "COMPLETED",
      "rewards_earned": 123
    }
  ]
}
```

`posted_date`, when supplied, is used instead of `transaction_date` for promotion timing. Amounts may be JSON numbers or decimal strings. `rewards_earned` may be a number or a string such as `"123 points"`.

Run it as:

```bash
python3 scripts/audit_rewards.py < audit_input.json
```

The script writes one JSON object to stdout with `audits`, `discrepancies`, `not_audited`, `summary`, and `input_errors`. It uses only completed/posted transactions. Pending, returned, refunded, invalid, and unsupported-card records are not assessed as reward discrepancies.

## Calculation rules implemented

* Database “points” for these cash-back cards are cash back at 1 point = $0.01.
* Expected points are always floored to a whole point, never rounded to nearest.
* **Business Silver Rewards Card:** eligible Travel and Software are 10%; other purchases are 1%. The documented excluded merchant families earn the normal 1% rather than 10%: Concur/SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight. Matching uses the named merchant or a clearly named variation beginning with that name (for example, a service plan bearing the merchant name).
* The Business Silver new-customer offer is modeled from the documented offer dates (2024-11-14 through 2025-11-14): an account opened during that period earns double its normally applicable rate for the first six calendar months after opening. Exclusions still receive the doubled ordinary rate (2%), not the travel/software bonus rate (20%). The six-month window is start-inclusive and ends before the same calendar day six months later. Override documented dates/months only by supplying the optional `business_promo` input object.
* **Silver Rewards Card:** Travel and Software are 4%; all other ordinary completed purchases are modeled at 1%. This standard rate is configurable with `silver_standard_rate` if runtime policy data differs.
* The supplied transaction category is treated as the posted merchant category. The Skill cannot prove that merchant coding was correct; a potentially misclassified charge should be described as needing category review rather than asserted to be definitively eligible.

Optional policy overrides are:

```json
{
  "business_promo": {
    "promo_start": "YYYY-MM-DD",
    "promo_end": "YYYY-MM-DD",
    "months": 6
  },
  "silver_standard_rate": "0.01"
}
```

## How to use the result

1. Confirm the customer and retrieve the requested accounts and transactions. Review both card types independently; do not apply Business Silver’s promotion to Silver Rewards.
2. Run the script with the retrieved records. Treat any `input_errors` or `not_audited` records as limitations to explain, not as proof that rewards are correct.
3. For each `discrepancies` record, tell the customer the transaction, recorded and expected points (and the corresponding dollars), applicable rate, and concise basis. A positive `point_difference` means the recorded points exceed the calculated points; a negative value means fewer points were recorded.
4. Explain that qualifying travel/software is dependent on the posted merchant category. Mention the Business Silver excluded merchants when relevant. Do not claim the current reward-points account balance should equal the transaction-only audit total.
5. If the customer wants a transaction investigated or corrected, verify the exact transaction ID and provide the documented self-service dispute tool with `give_discoverable_user_tool`: `submit_cash_back_dispute_0589`. The customer must submit it using their own `user_id` and that transaction ID. Do not submit it on their behalf.

A meaningful validation is that every item in `discrepancies` has `actual_points != expected_points`, every audited expected value is a nonnegative integer, and the summary discrepancy count equals the length of the discrepancies list. The included script performs these checks and reports malformed inputs instead of silently inventing results.
