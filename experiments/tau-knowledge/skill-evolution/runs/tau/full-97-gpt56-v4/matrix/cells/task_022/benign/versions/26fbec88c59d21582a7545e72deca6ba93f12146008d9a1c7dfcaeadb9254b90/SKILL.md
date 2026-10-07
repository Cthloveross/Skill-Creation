---
name: credit-card-rewards-audit
description: Audit posted credit-card transaction rewards against the documented Diamond Elite, Business Platinum, Business Silver, and EcoCard earning rules. Use when a customer asks to identify rewards that were over- or under-awarded, while preserving exact floor rounding and explicit merchant exclusions.
---

# Credit-card rewards audit

Use this Skill to produce a factual, transaction-level review. It calculates the expected whole-number reward for every supported posted transaction, compares it with the recorded reward, and reports only discrepancies plus totals. It does **not** make reward adjustments: no reward-correction action is declared by this runtime.

## Operating procedure

1. Identify the customer using the supplied identifier, then retrieve their credit-card accounts and complete transaction history with the declared read-only banking tools. Use already-supplied observations when they are present; do not repeat a retrieval merely because it is described here.
2. If verification is required for a later account action, obtain confirmation of two identity fields from the user, compare them to the retrieved record, get the current time, and call `log_verification`. A name lookup alone is not identity verification. Do not expose stored identity data while asking for confirmation.
3. Normalize the retrieved account and transaction fields into the JSON schema below. Include each account's card type and opening date, since Business Silver promotional eligibility depends on the opening date.
4. Run `python3 scripts/audit_rewards.py < audit_input.json > audit_report.json`.
5. Check `ok`. If false, correct missing or malformed supplied input and rerun. Do not silently substitute values.
6. Communicate the `discrepancies` in date/order returned by the script. For each, state the transaction ID, merchant, amount, applicable rate/rule, recorded points, expected points, the matching `recorded_redemption_value` and `expected_redemption_value`, and whether it was over- or under-awarded. Describe cash-back-card values as cash back; describe EcoCard values as sustainability-point redemption values. State that all calculations floor fractional points.
7. Include summary totals separately by reward currency. Never add or net cash-back points and EcoCard sustainability points: they are different units. `cash_back_cards` points are cash back at $0.01 per point; `ecocard_sustainability_points` are sustainability points that separately redeem at $0.01 per point. The `all_rewards` group may combine only their dollar redemption values, never their point counts.
8. Explain skipped records rather than treating them as correct. Pending, unsupported-card, and insufficient-data records require status or program review. A posted refund/return/reversal is reviewed: calculate the applicable original earn on its absolute amount, floor it, and reverse that whole-point result (a negative expected reward). For Business Platinum, cash equivalents, balance transfers, and fees earn zero points. Do not claim a correction has been posted, and do not use an undeclared adjustment tool.

## Input and output contract

`audit_rewards.py` reads one JSON object from standard input and writes one JSON object to standard output.

Required input:

```json
{
  "accounts": [
    {"card_type": "...", "date_of_account_open": "MM/DD/YYYY"}
  ],
  "transactions": [
    {
      "transaction_id": "...",
      "credit_card_type": "...",
      "merchant_name": "...",
      "transaction_amount": "$0.00",
      "transaction_date": "MM/DD/YYYY",
      "category": "...",
      "status": "COMPLETED",
      "rewards_earned": "0 points"
    }
  ]
}
```

Dates may alternatively use `YYYY-MM-DD`; money and recorded-points fields may be JSON numbers or display strings. An optional `business_silver_promo` object may override the documented date bounds for a different program configuration:

```json
{"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}
```

The result contains `discrepancies`, `reviewed_count`, `skipped`, and a `summary`. A discrepancy has signed `difference_points` (`expected - recorded`), so a positive value is under-awarded and a negative value is over-awarded. It includes `recorded_redemption_value`, `expected_redemption_value`, and `difference_redemption_value`, each exactly equal to its whole-point count times $0.01. The summary separates `cash_back_cards` from `ecocard_sustainability_points`; it deliberately does not aggregate their point counts. Its `all_rewards` group aggregates only dollar redemption values; its `net_magnitude_redemption_value` is an absolute dollar magnitude and `net_direction` supplies its direction. `statement_credit_equivalent` is formatted only as a value explanation; it is not an instruction to alter an account. Reward values must be whole numbers; malformed fractional recorded-point values are skipped for review rather than silently truncated.

## Rule application

The helper uses exact decimal arithmetic and `ROUND_FLOOR`, never binary floating point or nearest-integer rounding.

- **Diamond Elite Card:** 5 points per dollar (5.0% cash back) on eligible posted purchases.
- **Business Platinum Rewards Card:** 4 points per dollar for Travel, Software, and Media/Advertising categories; 1.5 points per dollar otherwise.
- **Business Silver Rewards Card:** 10 points per dollar for Travel and Software and 1 point per dollar otherwise. Concur/SAP Concur/Expensify/Navan and Apple/Microsoft/Dell are standard-rate exceptions. The documented double-reward offer applies only where the account opened within its offer window and the transaction falls in the first six months after opening. When the offer is not applied, state whether the opening date was outside the offer window or the purchase was outside the six-month window; do not assume the standard 10-point Travel/Software rate was doubled.
- **EcoCard:** 5 sustainability points per dollar where the supplied category establishes that a purchase is Green; otherwise 1. Target, Walmart, Amazon, and ThredUp are standard-rate exceptions. For transactions explicitly categorized as EV charging, only Tesla Supercharger, ChargePoint, and EVgo qualify for the high rate.

Category and merchant data establish eligibility. Do not infer a favorable category from a merchant name not explicitly covered by a documented exclusion or EV partner rule. See `references/reward_rules.md` for the auditable rule source summary.

## Validation expectations

Before presenting results, verify that every posted purchase or return transaction was either reviewed or listed in `skipped`, that every discrepancy has nonempty transaction/card/merchant data, and that each currency-group total equals the absolute point differences in that same currency, while `all_rewards` combines only the groups’ dollar redemption values. The script performs these calculations deterministically; manually recompute neither rounding nor totals.