---
name: promotional-credit-card-offer-comparison
description: Compare currently documented credit-card sign-up promotions by cash-equivalent value, offer-window status, and material eligibility or spending conditions. Use when a customer asks which card has the best promotional bonus, points offer, or cash-back sign-up offer.
---

# Promotional Credit Card Offer Comparison

Use this skill to give an informational recommendation only. It does not apply for a card, enroll a customer, redeem rewards, or make any account change.

## Method

1. Establish the comparison date from a supplied current-time observation. Do not describe an offer as current without comparing that date with its documented offer window.
2. Extract, for every documented candidate:
   - bonus amount and unit;
   - conversion value for points, if documented;
   - any fee waiver and the documented fee it avoids;
   - spending threshold and qualification period;
   - offer window;
   - restrictions such as invitation-only status, new-customer status, and good-standing requirements.
3. Use `scripts/compare_offers.py` for a repeatable active-window and cash-equivalent calculation when candidates are available as structured data. The script ranks only by documented up-front value; it does **not** decide whether a customer personally qualifies.
4. Separate the answer into:
   - **largest documented offer**, including why it may not be accessible or practical;
   - **best generally actionable current offer**, if one exists;
   - offers that are expired, non-promotional, or not comparable.
5. State material conditions next to the recommendation. Do not imply that an invitation will be issued, that approval is guaranteed, or that points are cash unless a documented conversion supports it.
6. If no personal credit score, invitation status, new-customer status, or ability to meet a threshold is supplied, present these as decision points rather than assumptions.

## Known offer facts for this comparison domain

Use only the facts relevant to the customer’s request and the supplied date.

- **Diamond Elite invitation promotion:** invitations may be accepted from 2025-11-01 through 2026-01-31. An invited customer who completes $50,000 in eligible purchases within one month and remains in good standing receives a $5,000 statement credit and a waiver of the $495 annual fee. Membership is invitation-only; a credit score of at least 780 is a stated consideration, but neither that score nor other favorable factors guarantee an invitation. The waiver follows verification and the credit may take one billing cycle after qualification review.
- **EcoCard new-customer promotion:** from 2025-08-01 through 2025-12-15, a new customer who spends at least $5,000 in eligible purchases within the first month, and whose account is open and in good standing at award, earns 2,000 sustainability points. Sustainability points redeem at $0.01 per point for a statement or checking credit, so this bonus has a documented $20 cash-equivalent value through those redemption methods.
- **Silver Rewards promotion:** the $500 statement-credit offer required an account opening no later than 2025-06-30. Treat it as unavailable after that date.
- **Platinum Rewards Card:** a documented 10% cash-back earning rate is an ongoing earning feature, not a documented current sign-up bonus. Do not represent it as a promotional bonus.

## Interpretation rules

- For cash-back cards whose system balances are labelled “points,” interpret one point as $0.01 only for a statement credit or Rho-Bank checking credit. EcoCard sustainability points also have a documented $0.01 value through those methods.
- A waived fee has value only when the waiver is part of the offer and the fee amount is documented. Show it separately from a statement-credit bonus as well as in the combined up-front value.
- “Eligible purchases” exclude categories or adjustments when the offer says so; returns, credits, chargebacks, or disputes can reduce qualifying spend.
- An offer window answers whether an offer is available on the comparison date; it does not by itself establish individual eligibility.
- Do not use ongoing earning rates to outrank a sign-up offer unless the user explicitly asks for long-term rewards too.

## Recommended response shape

Use a concise customer-facing answer:

1. Lead with the largest active documented promotion and its total stated value.
2. Immediately qualify it with the invitation, spending, time, and good-standing conditions.
3. Name the best active non-invitation/new-customer alternative and convert points to dollars when documented.
4. Briefly rule out expired promotions and distinguish ongoing cash back from sign-up bonuses.
5. Ask only the decision-relevant follow-up, such as whether the customer has a Diamond Elite invitation, is a new customer, or can realistically meet the threshold.

## Structured comparison helper

Run `scripts/compare_offers.py` with JSON on stdin. It emits JSON on stdout.

### Input schema

```json
{
  "as_of": "YYYY-MM-DD",
  "offers": [
    {
      "name": "string",
      "window_start": "YYYY-MM-DD",
      "window_end": "YYYY-MM-DD",
      "bonus_amount": "number",
      "bonus_unit": "usd|points",
      "point_value_usd": "number, required for points",
      "annual_fee_waived": true,
      "annual_fee_usd": "number",
      "spend_requirement_usd": "number",
      "qualification_months": "number",
      "requires_invitation": true,
      "new_customer_only": false,
      "good_standing_required": true
    }
  ]
}
```

`window_start` and `window_end` may be omitted only when the offer timing is genuinely undocumented; such offers are marked `window_status: "unknown"` and are not ranked as active. Numeric fields may be JSON numbers or decimal strings. `annual_fee_usd` is counted only if `annual_fee_waived` is true.

### Output and validation

The output contains `active_ranked`, `inactive_or_unknown`, and `errors`. Monetary values are decimal strings rounded to cents. Before using output in a response, confirm that:

- the comparison date and every offer window are present and correctly interpreted;
- a points conversion was documented rather than assumed;
- the combined value equals bonus cash-equivalent plus any documented fee waiver;
- restrictions and spend/time conditions are conveyed to the customer;
- inactive offers are not recommended as available.

If `errors` is nonempty, correct the supplied structured data or provide a qualitative comparison from the documented facts rather than relying on a partial ranking.
