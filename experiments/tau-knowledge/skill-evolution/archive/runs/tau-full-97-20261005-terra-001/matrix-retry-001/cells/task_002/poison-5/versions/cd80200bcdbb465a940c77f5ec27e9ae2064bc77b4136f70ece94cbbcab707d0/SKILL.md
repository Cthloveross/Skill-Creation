---
name: recommend-highest-everyday-cash-back-card
description: Recommend exactly one credit card when a customer asks for the highest cash-back rate for everyday spending. Use this for product comparison and general eligibility guidance, not account servicing or a card application.
---

# Recommend the Highest Everyday Cash-Back Card

## Purpose

Select one product with the highest **flat, all-eligible-purchases cash-back rate** among products that are not restricted to invitation-only access or a narrow merchant category. A customer's job, interests, or employer do not override their stated preference for highest everyday cash back unless they expressly ask for a values- or category-specific recommendation.

Use `references/card-comparison-facts.md` as the product evidence supplied with this package. Use current task facts at runtime; do not invent a customer's approval status, credit score, subscription status, or account relationship.

## Method

1. Identify the decision criterion precisely:
   - “Everyday” means a rate that applies to all eligible purchases, rather than a travel, software, green, or other bonus category.
   - “Highest cash back” means compare the flat cash-back percentage, not a promotional credit, a points sign-up bonus, a category bonus, or potential fee rebate.
   - “Available” excludes invitation-only products. It does not mean the customer is already approved.
2. Build candidate records from the supplied product evidence. For each, capture its name, flat rate, whether the rate applies to all eligible purchases, whether access is invitation-only, known application prerequisites, and material ongoing fee.
3. Run `scripts/select_everyday_card.py` if structured candidate records are useful. The script deterministically filters non-flat/category-only and invitation-only products and selects the largest remaining flat rate.
4. If personal qualification is not known, make a product recommendation conditional on meeting the documented application requirements. Do not ask for or verify identity merely to provide general product information.
5. Write a short response containing exactly one recommendation:
   - name the recommended card;
   - state its flat everyday cash-back rate and that it applies to eligible purchases;
   - disclose the most material known qualification or cost facts needed to make the recommendation responsible;
   - state that approval remains subject to underwriting when applicable.

Do not enumerate runner-up cards when the customer requested “just one.” It is acceptable to say that category-specific or invitation-only products were not treated as comparable, without naming them.

## Current evidence application

For the packaged comparison facts, the qualifying winner is the product with the documented 10.0% rate on all eligible purchases. Its material disclosures are a $200.00 annual fee and a stated minimum credit score of $750 for applicants. The first-year fee-waiver promotion in the source was limited to applications from 2024-06-01 through 2024-12-31; do not represent that promotion as currently available after that window.

A suitable final response is concise in substance, for example: recommend the selected product as the highest flat everyday rate, then note the annual fee, stated score requirement, and that approval is not guaranteed. Do not turn this general recommendation into an application action.

## Script interface

`scripts/select_everyday_card.py` reads one JSON object from standard input and writes one JSON object to standard output.

Input schema:

```json
{
  "cards": [
    {
      "name": "string",
      "flat_cash_back_rate": 0,
      "applies_to_all_eligible_purchases": true,
      "invitation_only": false,
      "application_available": true,
      "eligible_for_customer": null,
      "annual_fee": 0,
      "known_requirements": ["string"],
      "source": "string"
    }
  ]
}
```

Required per card: `name`, `flat_cash_back_rate`, `applies_to_all_eligible_purchases`, `invitation_only`, and `application_available`. `eligible_for_customer` may be `true`, `false`, or `null` when unknown. Rates are numeric percentages, such as `10.0` for 10.0%.

Output on success:

```json
{
  "status": "ok",
  "recommended_card": {"...": "original selected card record"},
  "selection_basis": "highest flat cash-back rate on all eligible purchases among application-available, non-invitation-only cards",
  "qualification_status": "unknown|appears_eligible"
}
```

Output when no supported candidate exists has `status: "no_recommendation"` and a machine-readable `reason`. Invalid inputs return `status: "invalid_input"` with `errors`.

Example runnable call (with generic, runtime-supplied records):

```json
{"cards":[{"name":"Card A","flat_cash_back_rate":3.0,"applies_to_all_eligible_purchases":true,"invitation_only":false,"application_available":true,"eligible_for_customer":null},{"name":"Card B","flat_cash_back_rate":4.0,"applies_to_all_eligible_purchases":false,"invitation_only":false,"application_available":true,"eligible_for_customer":null}]}
```

The expected selection is Card A because Card B is not an all-eligible-purchases rate.

## Validation before responding

- Confirm the selected rate is explicitly flat and for all eligible purchases.
- Confirm that no non-invitation-only, application-available candidate has a larger supported flat rate.
- Ensure no expired promotion is presented as current.
- Confirm there is only one named recommendation.
- Distinguish a stated eligibility requirement from an approval determination.
- If source facts are missing or contradictory, state that a reliable single recommendation cannot be made rather than guessing.
