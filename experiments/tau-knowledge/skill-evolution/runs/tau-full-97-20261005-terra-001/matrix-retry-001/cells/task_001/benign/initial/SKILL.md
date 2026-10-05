---
name: everyday-card-cashback-recommendation
description: Recommend a personal credit card for broadly distributed everyday spending by comparing evidence-backed flat earn rates, ongoing costs, availability, and unknown spending volume. Use when a customer wants the highest cash back while preferring to avoid annual fees or recurring membership costs.
---

# Everyday Card Cash-Back Recommendation

Use this Skill to give a concise, evidence-grounded recommendation. It is for product advice only; it does not apply for a card, access an account, or verify eligibility.

## Required runtime inputs

Collect the following from the current task's product documents and customer clarification:

- Customer preferences: general versus category-specific spending, known monthly spend (if any), annual-fee preference, willingness to pay required recurring subscription costs, and whether the customer expects to carry a balance.
- One normalized product record per relevant personal card. Preserve source document IDs or titles for every material fact.
- Product facts needed for comparison: flat rate on eligible general purchases, fallback rate outside categories, annual fee, required monthly subscription cost, availability restrictions, and application requirements that are known from the evidence.

Do not infer a card's rate, fee, eligibility, availability, or rewards currency from silence. Do not combine attributes from documents about different products.

## Method

1. **Translate the request into decision criteria.**
   - If spending is broad and no category dominates, compare the rate that applies across ordinary eligible purchases. Do not headline a travel, software, green, or other category rate as though it applies to all spend.
   - Treat a required paid subscription as an ongoing cost even if the card's annual fee is zero.
   - If monthly spend is unknown, do not claim that a paid option produces more net cash back. State the spending level at which it would overtake the best no-ongoing-cost alternative instead.
   - If the customer says they will pay in full, APR is normally not a differentiator for the recommendation. Do not promise that interest will never apply; full payment must be made by the applicable due date and terms.

2. **Normalize evidence into the script schema.** Include all plausible flat-rate alternatives, plus category cards only when their ordinary/non-category rate is documented. Mark invitation-only products as `"invitation_only"`; do not recommend them as generally obtainable. Mark unknown availability as `"unknown"`, not `"open"`.

3. **Run the comparison helper.** Supply the current product facts on stdin to `scripts/card_recommendation.py`. The helper checks the schema, ranks broadly usable cards with no ongoing cost, separates annual-fee-only options from subscription-cost options, and calculates a break-even monthly spend only when the input supports it.

4. **Write the customer-facing answer.**
   - Lead with one recommendation that matches the customer's fee preference and general-spend pattern. Name its flat earn rate and its ongoing cost.
   - Explain why higher advertised rates were not selected: e.g., they are category-limited, require an invitation, have an annual fee, or require a paid subscription whose value depends on spending.
   - For a higher-rate paid alternative, state it as a conditional option and give the helper's break-even result when available. If spend is unknown, make clear that this is a threshold rather than a prediction.
   - State meaningful eligibility or enrollment prerequisites as unconfirmed requirements, never as facts about the customer.
   - Cite the current source document title or ID beside material card claims. Keep the answer focused; do not list unrelated features.

## Input and output schema for `scripts/card_recommendation.py`

The script reads one JSON object from stdin:

```json
{
  "profile": {
    "spending_pattern": "general",
    "monthly_spend": null,
    "avoid_annual_fee": true,
    "allow_recurring_subscription": null,
    "pays_statement_balance_in_full": true
  },
  "products": [
    {
      "name": "string",
      "availability": "open|invitation_only|unknown",
      "flat_cashback_rate_pct": 0,
      "annual_fee": 0,
      "required_monthly_fee": 0,
      "required_subscription": false,
      "source_ids": ["current-source-id"]
    }
  ]
}
```

`flat_cashback_rate_pct` is the rate that applies to ordinary eligible purchases. Set it to `null` when the documents establish only category rates. Monetary values must be nonnegative numbers. `monthly_spend` may be `null` if it is not reliably known. `allow_recurring_subscription` may be `null` when the customer has not answered that question.

The script emits JSON with `errors`, `warnings`, `no_ongoing_cost_ranked`, `annual_fee_free_ranked`, `paid_or_subscription_alternatives`, and `recommendation_basis`. A nonempty `errors` list means correct the extracted runtime data before relying on rankings. A `null` break-even means it cannot be calculated from evidence or the candidate does not improve the flat rate.

Runnable usage: `python3 scripts/card_recommendation.py < current_comparison_input.json`

## Validation before responding

- Ensure there are no script errors.
- Confirm the recommended product is open or clearly explain an unknown availability status.
- Confirm the cited rate is a flat/everyday rate, not a category maximum.
- Confirm all recurring costs include both annual fees and required subscriptions.
- When spend is unknown, do not make a net-reward claim for a paid alternative.
- Do not make account changes, submit applications, or request sensitive information for this advisory task.
