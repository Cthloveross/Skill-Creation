---
name: business-credit-card-purchase-return-comparison
description: Compare documented business-card returns for a proposed large purchase, accounting for category coding, welcome offers, annual fees, promotion dates, credit-line suitability, and stated eligibility. Use for informational card-selection questions; it does not submit an application or perform account actions.
---

# Business Credit Card Purchase-Return Comparison

Use this Skill to give a transparent, conservative comparison of business credit-card options for a specific proposed purchase.

## Scope and safety

This workflow provides product information and arithmetic only. Do not imply approval, a particular credit line, merchant coding, offer qualification, or offer fulfillment is guaranteed. Do not apply for a card, open an account, alter an account, or expose customer data unless the user expressly requests an action and the supported banking workflow permits it.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Method

1. Identify the purchase amount, merchant type, stated business purpose, desired account-opening timing, and whether the user is asking only for advice. Obtain the current date from an available read-only time source when promotional windows matter.
2. Treat the merchant category code (MCC), not the description of the item, as controlling for category bonuses. If the actual MCC is unknown, calculate only the reliable base rate and label higher category earnings as conditional.
3. Read the supplied product-policy reference and shortlist cards that can plausibly support the requested purchase. Compare both:
   - purchase rewards: `purchase amount × applicable cash-back rate`; and
   - separately documented welcome value, only when the timing and spend requirement can be met.
4. Do not treat a welcome bonus as immediate purchase cash back. Explain posting, net-purchase, account-opening, and deadline conditions. Returns and credits reduce rewards or qualifying spend when the policy says so.
5. Include annual-fee treatment for the relevant year. A waived first-year fee does not establish future-year cost.
6. Evaluate credit capacity separately from rewards. A published minimum, starting limit, or range is not an approval promise. For a large charge, tell the user that the approved line must cover the purchase and any existing balance.
7. Present a recommendation with a compact comparison, assumptions, and the next facts needed (especially dealer MCC and the user's credit/eligibility profile). Distinguish a best documented outcome from a guaranteed outcome.

For numerical comparisons, run `scripts/compare_rewards.py`. Supply only policy facts supported by the applicable product materials; do not invent rates, dates, fees, or eligibility requirements.

## Product-policy reference for the supplied business-card catalog

Use [references/business_card_policy.md](references/business_card_policy.md) for the documented policies available with this Skill. It is intentionally limited to the catalog covered by this workflow. If a requested card or policy detail is absent, say it cannot be verified from the supplied materials rather than guessing.

## Expected response structure

- Start with the likely best option under explicitly stated assumptions.
- Show a comparison of reward amount, promotional value (if conditional), fee, and credit-capacity caveat.
- Explain MCC dependence and why the purchase purpose alone does not create a category bonus.
- State qualification requirements and time-sensitive conditions relevant to the recommendation.
- Offer practical next steps, such as confirming the merchant's payment coding and reviewing disclosed credit terms before applying.

## Calculator interface

`scripts/compare_rewards.py` reads one JSON object from standard input and writes one JSON object to standard output.

Input schema:

```json
{
  "purchase_amount": 40000,
  "options": [
    {
      "name": "Card name",
      "base_rate_percent": 1.0,
      "conditional_rate_percent": 2.5,
      "conditional_rate_applies": false,
      "annual_fee": 200,
      "first_year_fee": 200,
      "welcome_credit": 500,
      "welcome_spend_requirement": 10000,
      "welcome_requirement_may_be_met": true,
      "promotion_multiplier": 1.0,
      "promotion_applies": false
    }
  ]
}
```

`conditional_rate_percent` is optional and may be used only when the caller has confirmed that the purchase qualifies. The calculator returns base and selected reward values, conditional welcome-credit values, first-year fee, and first-year net value. Monetary results are rounded to cents using decimal arithmetic. It does not decide eligibility, dates, category coding, or credit approval.

Example runnable call:

```sh
printf '%s' '{"purchase_amount":40000,"options":[{"name":"Example","base_rate_percent":1,"annual_fee":0,"first_year_fee":0}]}' | python3 scripts/compare_rewards.py
```

Validate a result before using it: ensure the selected rate is supported by an actual or explicitly assumed MCC, ensure each welcome-offer condition is separately stated to the user, and ensure no option is characterized as able to fund the purchase without a sufficient approved credit line.
