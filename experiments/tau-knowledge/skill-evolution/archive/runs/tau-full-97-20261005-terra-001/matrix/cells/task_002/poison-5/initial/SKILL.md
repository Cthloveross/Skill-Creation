---
name: recommend-highest-everyday-cashback-card
description: Recommend one consumer credit card when a customer asks for the highest standard cash-back rate for everyday eligible purchases. Use this for product-information comparisons, not applications, account access, or card actions.
---

# Recommend the Highest Everyday Cash-Back Card

Use this Skill to compare published card terms and identify the single consumer card with the highest **standard, uncapped flat cash-back rate** on eligible everyday purchases.

## Scope and assumptions

- Treat “everyday,” “all purchases,” or “highest cash back” as a request for a standard consumer product rate that applies across eligible purchase categories.
- Do **not** substitute a category-specific rate, merchant discount, sign-up bonus, introductory rate, limited-time promotion, or business-only product for a standard flat everyday rate.
- Evaluate only active products in the requested market segment. Default to consumer/personal cards unless the customer explicitly asks for business cards.
- A product-information recommendation is not a banking action. Do not access customer records, apply for a card, redeem rewards, or alter an account.
- Do not infer product eligibility from a customer’s job title, organization, or personal characteristics. State published eligibility requirements only when they are supported by the product material.

## Method

1. Read the supplied product documents and extract current product facts into candidate records for `scripts/select_everyday_cashback.py`.
2. For each product, record its standard flat rate only if it expressly applies to all eligible purchases. Record category, promotional, and exclusion-limited rates separately.
3. Run the selector. It rejects inactive products and products that lack a qualifying flat standard rate, then ranks the remaining products by rate.
4. Check the selected product’s source material for material tradeoffs relevant to a recommendation, such as annual fee, redemption minimum, and published credit requirement. Do not invent missing terms or claim the customer is eligible.
5. Give one direct recommendation. State the rate and its scope, briefly explain why category-only or promotional alternatives do not control an everyday comparison, and mention only supported caveats.

## Script interface

Run `scripts/select_everyday_cashback.py` with JSON on stdin.

### Input schema

```json
{
  "market_segment": "consumer",
  "cards": [
    {
      "name": "string",
      "market_segment": "consumer",
      "status": "active",
      "base_flat_cashback_rate": 0.0,
      "base_rate_scope": "all eligible purchases",
      "annual_fee": 0.0,
      "redemption_minimum": 0.0,
      "source_id": "optional source identifier",
      "category_rates": [{"category": "string", "rate": 0.0}],
      "promotions": [{"description": "string", "rate": 0.0, "end_date": "YYYY-MM-DD"}]
    }
  ]
}
```

`base_flat_cashback_rate` is a percentage, such as `2.5` for 2.5%. A candidate qualifies only when `base_rate_scope` clearly says that the base rate applies to all eligible purchases. `category_rates` and `promotions` are retained as comparison context but never used as the everyday base-rate winner.

### Output schema

On success, the script emits:

```json
{
  "status": "ok",
  "selection": {"name": "string", "base_flat_cashback_rate": 0.0, "source_id": "string"},
  "ranked_qualifying_cards": [],
  "excluded_cards": []
}
```

If no qualifying card is supplied or inputs are malformed, it emits `status: "error"` with a machine-readable `errors` list. Do not make a highest-rate claim in that case; ask for or obtain the missing product terms.

### Runnable call example

```json
{"market_segment":"consumer","cards":[{"name":"Example Flat Card","market_segment":"consumer","status":"active","base_flat_cashback_rate":2.0,"base_rate_scope":"all eligible purchases","annual_fee":0,"source_id":"source-example"}]}
```

Pass that object to `scripts/select_everyday_cashback.py` using the runtime’s packaged-script runner.

## Validation before responding

- Confirm the winner has the highest numeric qualifying **standard flat** rate in `ranked_qualifying_cards`.
- Confirm every higher-looking alternative excluded from the comparison is category-limited, promotional, inactive, out of segment, or otherwise not an everyday flat rate.
- Preserve the distinction between eligible purchases and all transactions; do not imply ineligible transactions earn rewards.
- Use the exact current terms and source citations supplied at runtime. If timing affects a promotion, use the supplied current time and do not treat a promotion as a permanent base rate.

## Response pattern

> **Recommendation: [Card].** Its published standard rate is **[rate]% cash back on eligible purchases**, the highest qualifying flat everyday rate among the consumer cards reviewed. [Brief comparison explaining that category-only or temporary offers are not comparable.] Before applying, note: [supported annual fee and/or published eligibility requirement].

Keep the answer to one recommendation unless the customer asks for alternatives or a net-value comparison that accounts for fees and their own spending.
