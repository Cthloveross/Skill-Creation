---
name: highest-everyday-cash-back-card
version: 1.0.0
description: Advise a prospective Rho-Bank customer who asks which available personal card has the highest cash-back rate for ordinary, everyday eligible purchases. Use this for informational card comparisons; it does not apply to account-specific servicing, applications, or card-opening actions.
---

# Highest Everyday Cash-Back Card Advisor

## Scope and assumptions
Use this Skill when a customer wants the highest cash-back card for general/everyday spend. Treat **everyday** as requiring a flat rate across eligible purchases, rather than a rate restricted to one or more merchant categories. Do not represent a category-specific rate, a sign-up bonus, a fee rebate, or a points program as a higher general-purpose cash-back rate.

This is informational advice only. Do not access customer records, attempt to submit an application, make account changes, or request identity verification merely to compare publicly described products.

## Method
1. Load `references/personal_card_catalog.json` or pass its `cards` array to `scripts/recommend_card.py`.
2. Filter to products that are personal cards, earn cash back, and have `everyday_eligible_purchase_rate_pct` populated.
3. Rank by that rate, descending. Confirm that a higher advertised rate is actually general-purpose rather than category-limited.
4. State the top card and rate plainly. Give the meaningful tradeoffs from the selected card's terms: annual fee, eligibility/application requirement when known, reward posting/return treatment, and redemption minimum.
5. If the customer asks for a comparison, include the leading alternatives and explain why they are not the highest everyday rate. Do not treat EcoCard sustainability points as a flat cash-back rate; it is a points-based product with category-dependent earning.
6. If a customer asks to apply, explain that applications are completed in the Rho-Bank dashboard and that approval is subject to the published requirements. Do not claim approval, quote a personalized limit, or perform the application.

## Standard answer for a highest-rate everyday-spend question
After determining the ranking, provide a concise recommendation like:

> For general eligible purchases, the [card name] has the highest flat cash-back rate in the available personal-card lineup: [rate] cash back. Rewards accrue when eligible purchases post, and returns or credits reverse the related rewards. Its annual fee is [annual fee]; [include known minimum-score or subscription prerequisite]. Rewards can be redeemed once the available balance reaches [threshold].
>
> [Optional comparison: The next flat-rate alternative is ...; category-focused cards may be better only when most spending falls in their bonus category.]

For the current catalog, also disclose that Platinum's described annual-fee rebate requires at least $7,500 in net qualifying posted purchases in **each** of 12 monthly anniversary windows; one missed window disqualifies the annual rebate. Do not imply a historical promotion is active without checking its stated dates against the current date.

## Validation and deterministic helper
`scripts/recommend_card.py` accepts JSON on stdin:

```json
{
  "cards": [{"name":"...","personal":true,"program_type":"cash_back","everyday_eligible_purchase_rate_pct":2.5}],
  "require_flat_everyday_rate": true,
  "limit": 3
}
```

It emits JSON with `status`, `recommendation`, and a descending `ranked_cards` list. A successful result has `status: "ok"`, a non-null recommendation, and rates ordered from greatest to least. It returns `status: "no_qualifying_card"` rather than fabricating a recommendation if the supplied catalog has no qualifying flat-rate cash-back card.

Example executor call:

```text
python3 scripts/recommend_card.py < references/personal_card_catalog.json
```

The reference file is intentionally a product catalog, not customer data. If product facts supplied at execution differ from this catalog, use the current authoritative facts and preserve the same filtering and disclosure logic.

## Boundaries and follow-up
- “Eligible purchases” excludes the exclusions specified for the recommended product; never say literally every transaction earns rewards.
- Explain that posted—not merely authorized—transactions determine reward accrual when the product terms say so.
- If “everyday” actually means a particular category (such as travel, software, or green merchants), ask for the expected spending mix before changing the recommendation. A category card can be preferable for that narrower need but does not supersede the flat-rate result.
- If facts needed to rank products are missing or contradictory, say that the comparison cannot be completed from the available product terms; do not guess.
- Transfer only if the customer specifically needs human assistance or their request falls under an applicable operational escalation policy. A normal product comparison needs no transfer.
