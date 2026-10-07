---
name: review-silver-rewards-discrepancies
description: Review posted Silver Rewards Card transactions for apparent cash-back discrepancies using the documented 4% Travel/Software rate, 1% minimum non-category rate, per-purchase floor rounding, and cash-back point representation. Use when a customer asks to check Silver Rewards Card reward earnings or wants to dispute a specific reward calculation.
---

# Review Silver Rewards Card rewards

Use this Skill to calculate and clearly explain whether the rewards recorded for each **posted Silver Rewards Card** purchase meet the documented rate. It is not a general reward-rate table: do not infer rates for other card products from this Skill.

## Rules applied

- Reward values stored as `points` for this cash-back card represent cash back at **1 point = $0.01**.
- A completed Silver Rewards Card purchase categorized as `Travel` or `Software` earns **4.0%**, which is `floor(dollar_amount × 4)` points.
- Other Silver Rewards Card purchases earn at least **1.0%**, so the documented minimum is `floor(dollar_amount × 1)` points.
- Calculate each purchase separately and round down each purchase's fractional points. Do not calculate a rate on a transaction aggregate and do not round to nearest.
- The posted transaction category is controlling. Travel and software examples can help explain the result, but do not override the category recorded by the merchant or claim a different category without a review.
- Gift cards, person-to-person payments, bank fees, interest, insurance premiums, returns, and refunds may not qualify; rewards on returned/refunded purchases are reversed. Restrict this review to completed purchase transactions unless the customer specifically needs an explanation of another status.

A 4% category result below the calculated amount is an apparent shortfall. For a non-category purchase, only an amount below the 1% minimum is an apparent shortfall; an amount above that minimum is not evidence of an error because the documented rate is “at least” 1%.

## Procedure

1. Follow the runtime's required account-access and identity-verification flow before retrieving or disclosing live account data. A name alone is not a completed identity verification. If the runtime requires a verification audit, confirm two of the supported identity fields and log the verification only after confirmation.
2. Identify the relevant card and isolate transactions whose card type is exactly `Silver Rewards Card`. Do not assess transactions from another card as though they used Silver Rewards rates.
3. Keep only completed transactions for the automated comparison. Preserve transaction ID, merchant, date, category, amount, recorded points, and status.
4. Run `scripts/review_silver_rewards.py` with a JSON object containing the transaction records. If observations are supplied as formatted text rather than JSON, transcribe only the needed fields faithfully; do not alter merchant category or recorded rewards.
5. Check the script's `apparent_shortfalls` and `data_errors`. Explain the calculation in points and, where useful, dollars (points divided by 100). State that it is based on the posted category and the documented rates.
6. For transactions that meet the applicable rate, tell the customer the result is consistent with the rules, including the per-purchase floor. For an apparent shortfall, identify the specific transaction and expected versus recorded points without asserting that a correction has already occurred.
7. If the customer wants to contest an apparent discrepancy, confirm the exact transaction ID, then provide the customer-facing tool `submit_cash_back_dispute_0589(user_id: str, transaction_id: str)` using the runtime's `give_discoverable_user_tool`. The customer, not the agent, runs that tool with their own user ID and the selected transaction ID. Do not automatically submit disputes and do not collect card numbers or other sensitive card details.
8. Explain that category/merchant documentation may be requested during review. If the apparent issue depends on an allegedly incorrect merchant category, say that a category review may be needed rather than promising the bonus rate.

## Script interface

Run:

```sh
python3 scripts/review_silver_rewards.py < transactions.json
```

Input on stdin is a JSON object:

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "Silver Rewards Card",
      "merchant_name": "string",
      "transaction_amount": "$0.00 or number",
      "transaction_date": "optional string",
      "category": "Travel, Software, or another category",
      "status": "COMPLETED",
      "rewards_earned": "integer points"
    }
  ]
}
```

The script emits one JSON object. `reviews` contains eligible completed Silver transactions, with the applicable rate and integer expected minimum points. `apparent_shortfalls` contains only transactions recorded below the applicable documented amount. `skipped` explains why records were outside scope, and `data_errors` lists malformed records without silently guessing.

Validate the output before using it: `data_errors` should be empty for a definitive review; each reviewed record must show a nonnegative integer `expected_min_points`; and every listed apparent shortfall must have `recorded_points < expected_min_points`. The script uses decimal arithmetic, not binary floating point.

## Limits and escalation

This Skill supports only the documented Silver rates: 4% for posted Travel and Software, and a 1% minimum elsewhere. It cannot determine undocumented promotional rates, reconstruct rewards for another card type, or reclassify a merchant. If the transaction data are missing, malformed, non-completed, or the customer cannot identify a transaction, explain the limitation and request the relevant posted transaction details. Use the normal customer-support escalation path only when the issue requires work beyond the documented review or the available dispute process.
