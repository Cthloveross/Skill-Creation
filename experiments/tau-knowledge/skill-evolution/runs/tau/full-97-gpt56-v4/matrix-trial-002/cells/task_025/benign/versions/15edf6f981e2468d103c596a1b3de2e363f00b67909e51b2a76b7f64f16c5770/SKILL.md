---
name: business-card-large-purchase-recommendation
description: Compare business credit-card options for a large planned purchase, including transaction capacity, merchant-category eligibility, time-bounded promotions, fees, underwriting, and cash-back calculations. Use for informational card-selection requests where approval or merchant coding may be uncertain.
---

# Business Card Recommendation for a Large Purchase

Provide an informational comparison. Do not apply for a card, promise approval or a credit limit, or state that a merchant will receive a bonus rate when its coding is not confirmed. A general product comparison does not require identity verification or account lookup.

## Gather the decision facts

Use the runtime's supplied customer request, date/time observation, and product rules. Identify:

1. Net purchase amount, whether it is a single transaction, and the merchant/service.
2. The merchant category code (MCC), if actually known; otherwise explicitly mark it unconfirmed.
3. Current date, offer start/end dates, account-opening conditions, new-customer requirements, and promotion duration.
4. Each candidate's limit range, ordinary and bonus rates, fee applicable in year one, exclusions, and published underwriting requirements.
5. Whether the comparison is gross rewards or first-year net value.

For a single charge, a card is only usable if the customer has both an approved credit line and available credit at least equal to the charge when it posts. A documented maximum that exceeds the charge establishes only *potential* capacity.

## Evaluate in this order

1. **Capacity screen.** Exclude a card if its documented maximum is below the purchase amount. Keep cards whose maximum can reach the amount as conditional candidates, and distinguish them from cards with confirmed available credit.
2. **Classify the charge conservatively.** Rewards depend on the merchant's payment category, not simply a product description, a recurring billing arrangement, or the customer's business use. Apply explicit merchant exclusions exactly, without extending one brand/product exclusion to unrelated services from that brand.
3. **Establish a guaranteed rate first.** Use the ordinary rate unless an eligible bonus category is confirmed. Present a possible bonus outcome separately and label it conditional. Do not rank an unconfirmed bonus outcome as the promised return.
4. **Check promotions independently.** A promotion changes the rate only when all documented criteria are met: opening date, new-customer status, duration, and the rule for whether it multiplies ordinary and/or bonus rates. Do not equate application submission with account opening. If the timing or eligibility is unknown, show both the non-promotional result and a clearly conditional promotional result.
5. **Calculate gross and net transparently.** Cash back is `net purchase amount × applicable rate ÷ 100`. For first-year net value, subtract only the annual fee applicable to that account in that year; a documented waiver means the applicable fee is zero. Returns or credits reduce rewards.
6. **Make a conditional recommendation.** Select the highest guaranteed first-year net outcome among candidates with documented potential capacity, while stating that approval/available credit remains required. Give the next-best option if the leader's promotion is missed or its line is insufficient. Mention material published underwriting thresholds without predicting qualification.

## Streaming or music-subscription guardrail

When the purchase is an ordinary streaming or music subscription, do not infer a software or advertising bonus merely because the charge is digital, recurring, or company-wide. The supplied rules describe streaming as entertainment and describe software and advertising more narrowly. A named hardware/electronics exception for a brand does not decide the reward category of that brand's subscription service. Use the ordinary rate unless the actual merchant category is confirmed to meet a card's published bonus rule.

For the card-specific facts and exclusions, consult `references/business_card_rules.md`. Determine results from those rules and the runtime's date rather than embedding a scenario's amount, date, or answer in the response.

## Customer-facing response

Give a direct recommendation, then a compact table or bullets for every material candidate with:

- ordinary/guaranteed rate and calculated dollars;
- separately labelled possible bonus or promotional rate, if relevant;
- applicable first-year fee and gross versus net value;
- limit-range and available-credit caveat; and
- significant underwriting or timing constraints.

Explain why the merchant's MCC prevents a bonus promise. End with practical next steps: verify merchant coding, verify promotion eligibility and account-opening timing, and obtain/confirm a line with enough available credit before attempting the single charge.

Never claim that a card will approve a limit, that a subscription will earn a bonus rate, or that an offer applies outside its documented date window.

## Offer-window helper

Run `scripts/evaluate_offer_window.py` to make the calendar-date portion of an offer check reproducible. It accepts JSON on stdin:

```json
{"current_date":"YYYY-MM-DD","start_date":"YYYY-MM-DD","end_date":"YYYY-MM-DD","account_open_date":"YYYY-MM-DD or omit if unknown"}
```

It emits whether the window is open on the current date and whether a supplied account-opening date is within the inclusive date range. It intentionally does not infer a cutoff time, completed opening, new-customer status, approval, or other offer conditions. If no actual opening date is known, retain a conditional recommendation even if the offer is open today.

## Calculation helper

Run `scripts/compare_rewards.py` with JSON on standard input after making the factual determinations above. Scripts receive JSON on stdin and emit JSON on stdout.

```json
{
  "amount": "positive decimal",
  "include_annual_fee": true,
  "options": [
    {
      "name": "card label",
      "documented_capacity": "can_cover | cannot_cover | unknown",
      "available_credit": "confirmed | unconfirmed | insufficient",
      "base_rate_percent": 1.5,
      "bonus_rate_percent": 4.0,
      "bonus_eligibility": "confirmed | unconfirmed | not_eligible",
      "promotion_multiplier": 2,
      "promotion_eligible": true,
      "annual_fee": 0
    }
  ]
}
```

`documented_capacity` concerns the published limit range, while `available_credit` concerns the customer's actual approved line and remaining credit. Omit optional bonus/promotion/fee fields to use their documented defaults of no bonus, no multiplier, and zero fee. The output contains guaranteed calculations, separately labelled bonus possibilities, capacity readiness, and a ranking only across cards not documented as unable to cover the charge. It does not infer MCC, date eligibility, approval, or fee waivers.

Validate that the returned amount matches the purchase, that displayed rates and fees match the product rules, and that only confirmed bonuses are described as guaranteed. A conditional-capacity ranking is an informational comparison, not evidence that a charge can be made.
