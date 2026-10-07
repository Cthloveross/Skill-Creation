---
name: everyday-card-cashback-recommendation
description: Give evidence-grounded personal credit-card advice for broad everyday spending. Use when a customer wants the highest cash back while avoiding annual fees and/or required paid memberships, especially when monthly spend is unknown.
---

# Everyday Card Cash-Back Recommendation

Use the product documents supplied in the current task as the catalog. This Skill provides product advice only: it does not apply for a card, access an account, or establish that a customer will be approved.

## Required inputs

Before answering, identify from the current customer conversation:

- whether spending is broad/general or concentrated in documented categories;
- whether monthly spending is known;
- annual-fee preference;
- willingness to hold a required paid subscription; and
- whether the customer plans to pay the full statement balance.

From the current product documents, extract only documented facts for each plausible card:

- general/flat cash-back rate on eligible purchases;
- any category restriction and documented outside-category rate;
- annual fee;
- required subscription and its recurring cost;
- material availability restrictions, such as invitation-only status; and
- source document IDs or titles.

Do not infer a rate, fee, eligibility, availability, or subscription requirement from a document's silence. Do not combine facts from different products.

## Mandatory decision process

1. **Use the supplied catalog.** Once product documents are present, do not say that no catalog, product documents, or rate-and-fee evidence is available. Do not transfer the customer merely because comparison requires judgment.
2. **Match the rate to spending.** For broad everyday spending with no dominant category, compare documented flat/general-purchase rates. A travel, software, green, or other category maximum is not a general-spend rate.
3. **Count all ongoing costs.** Include both annual fees and required membership costs. A card with a $0 annual fee can still be a paid option if it requires a subscription.
4. **Honor expressed constraints.** If the customer declines annual fees or a required subscription, do not present a card with that cost as the unconditional winner. If a no-ongoing-cost flat-rate card is documented, clearly prioritize the best compatible one.
5. **Treat unknown spend carefully.** With no reliable monthly spend, do not claim that a paid higher-rate option has better net rewards. It may be mentioned only as a conditional alternative, with a documented break-even threshold when calculable.
6. **Handle payment intent accurately.** When the customer expects to pay the full statement balance by the due date, APR on carried balances is usually not a deciding factor. Do not promise that interest can never apply.
7. **State uncertainty correctly.** Approval, credit-score requirements, and availability not established by the evidence remain unconfirmed. Invitation-only products are not generally obtainable recommendations.

For a broad-spend, fee-averse customer who declines a required subscription, the final answer must explicitly name the documented no-ongoing-cost flat-rate recommendation, state its flat eligible-purchase rate and no-annual-fee status, and explain the relevant paid or category-limited alternatives. This is not optional after the required preferences and catalog facts have been gathered.

## Recommended helper workflow

Normalize the current product evidence and run:

```text
python3 scripts/card_recommendation.py < current_comparison_input.json
```

The helper is advisory and deterministic. Its recommendation is only as complete as the supplied, cited product records. Correct any reported `errors` before relying on its ranking.

### Input schema

The script reads one JSON object from stdin:

```json
{
  "profile": {
    "spending_pattern": "general",
    "monthly_spend": null,
    "avoid_annual_fee": true,
    "allow_recurring_subscription": false,
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
      "source_ids": ["document-id-or-title"]
    }
  ]
}
```

`flat_cashback_rate_pct` must be the documented rate for ordinary eligible purchases, not a category maximum; use `null` if no such rate is documented. `monthly_spend` can be `null`. Monetary inputs must be nonnegative. `allow_recurring_subscription` can be `null` only when the customer has not answered that question.

The script emits JSON with `errors`, `warnings`, `no_ongoing_cost_ranked`, `paid_or_subscription_alternatives`, `unranked_products`, and `recommendation_basis`. A `break_even_monthly_spend_vs_baseline` of `null` means the available evidence does not support a useful calculation.

## Customer-facing response format

Keep the final response concise and decisive:

1. Lead with: “I recommend **[card]** for your broad everyday spending.” State its documented flat rate and annual fee.
2. Tie it directly to the customer's broad spending, fee preference, subscription preference, and plan to pay the full statement balance.
3. Explain material alternatives only when useful:
   - higher flat-rate cards with a required subscription: state both the rate and subscription cost, and that the customer declined that requirement;
   - category cards: state that the advertised higher rate is limited to the documented category and state a documented ordinary rate if available;
   - annual-fee, invitation-only, or threshold-dependent cards: state the relevant restriction rather than calling them winners.
4. Add a brief approval/terms caveat only if applicable.
5. Cite the source title or ID beside each material product claim.

## Validation before responding

- The answer names a real documented card rather than merely describing a hypothetical option.
- A broad-spend recommendation uses a documented broad/flat rate.
- The recommendation discloses its annual fee and any required subscription cost.
- Paid or restricted alternatives are not presented as unqualified winners.
- Unknown monthly spend is not used to make an unsupported net-reward claim.
- The answer neither claims the current catalog is unavailable nor makes an unnecessary human transfer.
- No application, account change, or request for sensitive data is made.
