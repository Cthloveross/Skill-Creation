---
name: everyday-cash-back-card-recommendation
description: Recommend one credit card for a customer seeking the highest cash-back rate on ordinary everyday purchases, using documented card terms. Use when the request is informational and does not require account lookup, application processing, or a transaction review.
---

# Everyday Cash-Back Card Recommendation

## Purpose
Identify the single documented card with the highest **flat rate on all eligible purchases**. Do not treat a category-limited rate (such as travel/software) as an everyday-purchase rate.

## Procedure
1. Read `references/card_terms.md` and identify cards whose rate applies to all eligible purchases/all purchases.
2. Exclude category-specific rates from the flat-rate comparison unless the customer expressly asks about that category.
3. Select the highest documented flat cash-back percentage.
4. Give a direct, single-card recommendation. State the rate, that it applies to eligible purchases, and any material annual fee documented for the selected card.
5. Briefly distinguish the recommendation from lower flat-rate or category-limited alternatives only when useful. Do not claim eligibility, approval, or a personalized net benefit that is not documented.

For the supplied terms, use the recommendation generator:

```json
{"request_type":"highest_everyday_cash_back"}
```

with `scripts/recommend_card.py`. It emits a JSON decision object. Convert it into a concise customer-facing answer; it does not send a message or take banking actions.

## Boundaries
- “Everyday” means purchases that are eligible and posted normally; ordinary exclusions such as fees, interest, cash advances, balance transfers, and cash-equivalent transactions do not earn the selected card's stated cash back.
- Do not infer that an environmental-conservation role changes the recommended rate or card eligibility.
- Do not access customer data or request identity verification for this purely informational comparison.
- If the customer instead wants an application decision, personalized approval odds, an exact rewards balance, redemption help, or a comparison based on spending categories, explain the distinction and use only applicable documented terms.

## Validation
Before answering, verify that exactly one selected card has the maximum `all_eligible_purchase_rate_percent` among cards included in the decision output, and that the stated fee matches the generated result. If the reference data is absent or malformed, do not fabricate a recommendation; say that the terms cannot be compared from the available information.

## Script I/O
`scripts/recommend_card.py` reads one JSON object from standard input and writes one JSON object to standard output.

Input:
- `request_type` (optional string): must be omitted or `"highest_everyday_cash_back"`.

Output on success:
- `status`: `"ok"`
- `recommendation`: object containing `card`, `cash_back_rate_percent`, `annual_fee_usd`, `applies_to`, and `reason`
- `comparison_scope`: explanation of included/excluded rate types

Output on invalid input or unavailable source data has `status: "error"` and a machine-readable `error` field.
