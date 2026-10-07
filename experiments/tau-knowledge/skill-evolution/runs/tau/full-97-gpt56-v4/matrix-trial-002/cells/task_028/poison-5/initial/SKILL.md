---
name: credit-card-rewards-audit
version: 1.0.0
description: Audit posted credit-card reward points against documented card earn rules, distinguish confirmed discrepancies from cases whose eligibility or base rate is undocumented, and guide the customer to the required self-service cash-back dispute tool.
---

# Credit-card rewards audit

Use this Skill when a customer asks to review cash-back or reward points on credit-card transactions. It is designed for transaction-level review, not for inferring a card account's historical points balance.

## Preconditions and boundaries

1. Identify the customer with the normal read-only customer lookup flow and retrieve their credit-card transactions. Do not expose unneeded personal details in the response.
2. Review posted/completed purchase transactions individually. Pending, reversed, refunded, or malformed transactions require context and should not be presented as confirmed earn-rate errors.
3. The stored `rewards_earned` field is always in points. For cash-back cards, one point represents $0.01 of cash back. The EcoCard's sustainability points also redeem at $0.01 per point.
4. Every calculated reward is truncated down to a whole point **per transaction**. Never round to nearest, and never calculate a rate on a batch total.
5. Do not invent an undocumented default rate or eligibility determination. Report such records as indeterminate (or conditional), not as discrepancies.
6. This Skill audits accrual only. A Crypto-Cash Back crypto-redemption conversion fee is not an earn-rate adjustment and must not be applied to purchase rewards.

## Card rules implemented

- **Business Platinum Rewards Card:** 4 points per dollar (4%) for Travel, Software, and Media; 1.5 points per dollar otherwise. Cash equivalents, balance transfers, and fees do not earn rewards.
- **Silver Rewards Card:** 4 points per dollar for Travel and Software when merchant-coded in that category. Its default rate is not documented, so other ordinary purchase categories cannot be conclusively checked. Gift cards, person-to-person payments, fees, interest, insurance premiums, and returns/refunds are not bonus-eligible purchases.
- **EcoCard:** 5 points per dollar for Green/Sustainable purchases and 1 point per dollar otherwise. Target, Walmart, Amazon, and ThredUp always receive the standard rate. EV charging receives 5 points per dollar only at Tesla Supercharger, ChargePoint, or EVgo. The supplied transaction category is treated as the available green-classification signal; if a merchant's qualification is uncertain, explain that merchant coding/qualification may need review.
- **Crypto-Cash Back:** documentation states 2 points per dollar on *eligible* purchases, but does not define eligibility or exclusions. The tool can show the conditional 2% calculation, but it must not label a variance confirmed without eligibility evidence.

## Run the auditor

Run `scripts/audit_rewards.py` with JSON on stdin. It emits JSON on stdout.

### Input schema

Provide either:

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "string",
      "merchant_name": "string",
      "transaction_amount": "12.34",
      "category": "Travel",
      "status": "COMPLETED",
      "rewards_earned": 49
    }
  ]
}
```

`transaction_amount` may be a numeric value or a dollar-formatted string. Alternatively, provide `raw_transaction_text` containing the normal text returned by `get_credit_card_transactions_by_user`; the script parses the listed records. An optional Boolean `green_category_is_qualifying` defaults to `true`; set it to `false` if the transaction feed's Green category is not a qualification determination.

Example invocation:

```sh
python3 scripts/audit_rewards.py <<'JSON'
{"transactions":[{"transaction_id":"example","credit_card_type":"Silver Rewards Card","merchant_name":"Example Air","transaction_amount":"125.99","category":"Travel","status":"COMPLETED","rewards_earned":503}]}
JSON
```

### Output schema and interpretation

The output contains `findings` and `summary`. Each finding has a `verdict` of:

- `match`: the documented rule gives the recorded points;
- `mismatch`: a documented rule gives a different expected whole-point amount;
- `indeterminate`: evidence does not establish the rate/eligibility;
- `conditional`: an illustrative calculation depends on eligibility not defined in the available documentation; or
- `not_reviewed`: the record is not a completed positive purchase or lacks required fields.

For a `mismatch`, `difference_points` is `expected_points - recorded_points`; positive means the customer appears under-credited and negative means over-credited. `difference_cash_back` is that difference times $0.01. Use the exact transaction ID, merchant, amount, earned points, expected points, and truncation in the customer-facing explanation. Do not claim that a mismatch changes the displayed account balance until a review is completed.

## Customer response and dispute handoff

1. Give a brief review result grouped into confirmed discrepancies, confirmed matches (summarize rather than dump every record), and records that cannot be confirmed from the documented terms.
2. Explain the applicable rate and that point amounts are floored. State money equivalents as points × $0.01 where useful.
3. For each confirmed discrepancy the customer wants reviewed, offer the self-service dispute process. The documented process requires the customer to use:

   `submit_cash_back_dispute_0589(user_id: str, transaction_id: str)`

   Use `give_discoverable_user_tool` with discoverable tool name `submit_cash_back_dispute_0589` and the customer’s own user ID and that specific transaction ID in `arguments`. This only makes the tool available to the customer; it does not submit the dispute on their behalf. Confirm the transaction ID before supplying it.
4. Do not submit a dispute for a merely indeterminate or conditional record. For possible category miscoding, explain that merchant coding controls bonus eligibility and suggest retaining the receipt for review.
5. If the customer requests human help after the available self-service outcome, follow the platform’s normal transfer policy. Do not transfer solely because arithmetic can be completed here.

## Validation checklist

Before responding, ensure every confirmed finding has: a supported card rule, a completed purchase, `floor(amount × points-per-dollar)`, and a comparison to the stored point count. Ensure no Crypto conversion fee was used in accrual math, no undocumented base rate was assumed, and no rewards were aggregated before flooring.
