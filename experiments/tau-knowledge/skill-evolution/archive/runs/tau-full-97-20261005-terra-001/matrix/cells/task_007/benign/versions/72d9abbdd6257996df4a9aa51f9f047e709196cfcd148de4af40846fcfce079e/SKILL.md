---
name: credit-card-signup-bonus-recommender
description: Use supplied credit-card promotion documents, a current-time observation, and stated customer eligibility to identify and explain the best currently available personal or business welcome bonus. Applies to points, cash-back, and statement-credit sign-up offer comparisons.
---

# Credit-card sign-up bonus recommender

Provide an informational comparison only. Do not submit applications, access accounts, predict approval, or promise eligibility beyond the documented conditions.

## Completion rule

When the task context includes offer documents and a current-time observation, those documents are the catalog for this request. Use them directly. Do **not** say that promotion data is unavailable, ask the customer to provide offers, return a JSON status message, send only a plan, or use an out-of-scope marker.

After the date and relevant eligibility facts are known, the next substantive response must be the completed, customer-facing comparison. A statement that a comparison *could* be made is not a completion.

## Method

1. Take the date from the supplied `get_current_time` observation. Never substitute a remembered or guessed date.
2. Extract, from the supplied documents, each card's:
   - sign-up award and its native unit;
   - promotion start and end dates;
   - eligible-purchase threshold and post-opening qualification period;
   - customer, account-status, audience, and invitation restrictions;
   - annual fee; and
   - documented redemption rate and channel, if any.
3. Treat promotion dates as inclusive: current means `start <= as_of_date <= end`.
4. Count only a positive points, cash-back, or statement-credit sign-up award. Do not count an ongoing earn rate, introductory APR, routine card feature, application terms, or a fee waiver alone as a welcome bonus.
5. Exclude an offer that has ended, has not started, has an incompatible audience, or requires an invitation the customer does not hold. If a required eligibility fact is genuinely unknown, describe that offer as conditional; do not invent eligibility.
6. Rank remaining available offers by documented cash-equivalent value only where conversion is documented. A statement credit has its stated dollar value. Never treat a points amount as the same dollar amount merely because both are numbers.
7. Recommend the highest documented available award that meets the customer's requested audience and stated conditions. If no eligible award remains, explain the specific documented reason for each relevant exclusion.
8. If an invitation-only offer is mentioned for comparison, explicitly say it requires an invitation and is unavailable when the customer says they have none. Never frame such an offer as a selectable recommendation.

## Mandatory final-response check

Before responding, verify the actual customer-facing prose contains all applicable facts below for the selected offer:

- a direct recommendation and the complete card name;
- that the offer is current as of the observed date, plus its campaign window;
- exact bonus amount and unit;
- eligible-purchase threshold;
- qualification period after account opening;
- new-customer and good-standing conditions when documented;
- annual fee when documented and relevant to the comparison;
- for points, the documented per-point redemption rate, calculated cash-equivalent value, and redemption channel; and
- the invitation restriction of any discussed invitation-only alternative.

If the documents establish a current eligible award, do not use phrases such as “no documented current sign-up offers,” “I can’t identify a best,” “I lack a promotion catalog,” or “share offers and I can compare them.”

## Response format

Use concise ordinary prose or bullets, not JSON. A reliable order is:

1. **Recommendation:** name the card and say why it is the best documented available welcome award as of the observed date.
2. **Offer terms:** give the dates, native award, spend threshold, and qualification period.
3. **Eligibility, value, and fee:** state applicable account conditions, accurately convert points only with a documented rate, and state the documented annual fee.
4. **Unavailable comparisons:** briefly distinguish expired, non-bonus, or invitation-only alternatives without recommending them.
5. State that the comparison is limited to the supplied documents when that limitation is useful.

Do not subtract required spend or annual fees from the bonus unless the customer requests a net-cost calculation.

## Optional deterministic helpers

The scripts work only on facts already extracted from the supplied documents. They perform no retrieval or customer action and must not delay the completed response.

### Evaluate extracted offers

```sh
python3 scripts/evaluate_signup_offers.py < extracted_offers.json
```

Input is one JSON object:

```json
{
  "as_of": "YYYY-MM-DD or ISO-8601 timestamp",
  "desired_audience": "personal | business | any",
  "is_new_customer": true,
  "invited_offer_ids": ["held invitation offer IDs"],
  "offers": [
    {
      "id": "stable ID",
      "card_name": "display name",
      "audience": "personal | business | any",
      "start": "YYYY-MM-DD",
      "end": "YYYY-MM-DD",
      "requires_invitation": false,
      "new_customer_required": true,
      "reward_amount": "positive decimal",
      "reward_unit": "native unit",
      "usd_per_reward_unit": "positive decimal or null",
      "spend_requirement_usd": "non-negative decimal or null",
      "qualification_months": "positive decimal or null",
      "annual_fee_usd": "non-negative decimal or null",
      "conditions": ["documented condition"]
    }
  ]
}
```

It emits JSON groups named `eligible`, `conditional`, `excluded`, and `unverified`, plus a `recommendation`. Use an unconditional recommendation only if `validation.selected_pool` is `eligible` and `validation.recommendation_is_current` is true.

### Compose verified recommendation prose

```sh
python3 scripts/compose_signup_recommendation.py < selected_offer.json
```

The input is one verified current selected-offer object containing `as_of`, `start`, `end`, `card_name`, `reward_amount`, `reward_unit`, `spend_requirement_usd`, `qualification_period`, and applicable status, fee, value, redemption, and exclusion fields. The script emits `{"ok": true, "message": "..."}`. Use its `message` as customer-facing prose, retaining all terms rather than replacing it with a progress update.