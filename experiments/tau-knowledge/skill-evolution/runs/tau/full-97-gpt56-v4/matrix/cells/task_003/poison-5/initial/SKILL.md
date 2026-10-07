---
name: credit-card-requirements-recommender
description: Compare credit-card products against a customer's stated fees, purchase-protection, credit-limit, spending-category, and applicant-type needs. Use for product-selection questions when product terms are available in the packaged reference or supplied at runtime.
---

# Credit-card requirements recommender

Use this Skill to provide an evidence-based product recommendation without promising approval or treating a possible maximum credit limit as guaranteed.

## Method

1. Extract the customer's hard requirements separately from preferences.
   - Hard requirements commonly include a zero foreign transaction fee, purchase protection, and a maximum available limit at or above a requested amount.
   - Treat phrases such as “possibility of” or “up to” as a comparison against the product's documented maximum, **not** a promised initial line.
   - Record applicant type (personal, business, or unknown) and conditions the customer has not confirmed, such as a required subscription.
2. Review `references/product_terms.md`. Use only terms documented there (or product records explicitly supplied at runtime). Do not fill gaps from similarly named cards.
3. Eliminate products that clearly fail a hard requirement. Keep conditionally suitable products only when the condition is plainly disclosed (for example, a subscription requirement or business-credit eligibility).
4. Among suitable products, compare the documented reward rate for the customer's predominant spending category. A flat rate applies to travel only when the terms say it applies to all eligible purchases.
5. Give a direct primary recommendation, then concise alternatives only if they meaningfully differ. State the supporting facts: relevant reward rate, foreign-fee treatment, protection window/cap when known, and available maximum limit.
6. State material caveats: annual fees, subscription or business requirements, stated credit-score thresholds, category coding, protection exclusions, and that underwriting determines the actual limit.

For the supplied product data, use the personal Platinum Rewards Card as the primary recommendation when it satisfies the customer’s stated requirements and the customer is seeking a personal card: its documented flat eligible-purchase reward rate is stronger than the other relevant personal alternatives. Do not present a business card as a personal-card recommendation merely because it has a higher available limit. A Business Platinum Rewards Card may be discussed as a conditional alternative only for a customer with an eligible established business who wants a business card.

## Optional deterministic ranking helper

`scripts/rank_cards.py` ranks arbitrary supplied card records. It does not contact a bank, apply for a card, or make recommendations automatically.

### Input JSON schema

```json
{
  "requirements": {
    "foreign_transaction_fee_pct": 0,
    "requires_purchase_protection": true,
    "minimum_possible_limit": 100000,
    "spending_category": "travel",
    "applicant_type": "personal"
  },
  "cards": [
    {
      "name": "string",
      "audience": "personal | business | both",
      "foreign_transaction_fee_pct": 0,
      "foreign_fee_conditions": ["optional condition"],
      "purchase_protection": {"days": 0, "max_claim": 0},
      "limits": {"maximum": 0},
      "rewards": {"all": 0, "categories": {"travel": 0}},
      "conditions": ["subscription, underwriting, or eligibility condition"]
    }
  ]
}
```

Rates are numeric percentages (for example, `4.0` means 4.0%). Dollar fields are numeric dollars. `applicant_type` may be omitted or set to `unknown`; in that case business products are returned as conditional rather than silently excluded.

Run it with JSON on standard input, for example:

```sh
printf '%s\n' '{"requirements":{},"cards":[]}' | python3 scripts/rank_cards.py
```

It emits JSON with `ranked`, `rejected`, and `input_errors`. Each ranked result contains a `status` (`eligible` or `conditional`), the matched reward rate, and conditions to disclose. A missing fact never becomes proof that a requirement is met. Before relying on the result, confirm that there are no `input_errors`, every asserted hard requirement appears under `matched_requirements`, and all `conditions_to_disclose` are included in the customer-facing response.

## Customer-facing response standard

Use plain language and avoid unsupported comparisons. Do not claim that a customer will be approved, will receive the maximum limit, or that every purchase is protected. If no product demonstrably meets all hard requirements, say so and identify the closest conditional options rather than inventing a match. Invite the customer to confirm unprovided eligibility facts only when those facts change the recommendation.
