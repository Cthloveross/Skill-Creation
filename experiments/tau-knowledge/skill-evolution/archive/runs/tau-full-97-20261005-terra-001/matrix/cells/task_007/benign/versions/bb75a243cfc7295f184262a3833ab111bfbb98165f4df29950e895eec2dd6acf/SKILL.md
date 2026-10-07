---
name: credit-card-signup-bonus-recommender
description: Compare documented credit-card welcome offers using the supplied promotion documents, observed current date, and customer eligibility. Use for points, cash-back, and statement-credit sign-up-bonus recommendations.
---

# Credit-card sign-up bonus recommender

Provide an informational offer comparison only. Do not apply for a card, access an account, predict approval, or promise eligibility beyond the documented terms.

## Required completion behavior

The supplied promotion documents are the offer catalog for this request. When the task includes those documents and a current-time observation, use them directly. Do **not** claim that a catalog, source, or offer terms are unavailable; do not ask the customer to supply promotions; do not return JSON, a status update, a plan, or an out-of-scope marker.

Once the date and relevant eligibility facts are known, respond with the completed customer-facing recommendation in the next substantive message. Saying that a comparison could be performed is not a completion.

## Decision method

1. Use the date in the supplied `get_current_time` observation. Do not guess a date or rely on a remembered date.
2. Read the supplied documents for every potentially relevant card. Extract the card name, award, native award unit, campaign window, spend threshold, post-opening qualification period, eligibility restrictions, annual fee, and any documented redemption rate.
3. Treat stated campaign endpoints as inclusive: an offer is current only when `start <= observed date <= end`.
4. A welcome award must be a positive points, cash-back, or statement-credit award. Do not treat an ongoing earn rate, introductory APR, application eligibility, card feature, or fee waiver alone as a sign-up bonus.
5. Exclude offers that are expired, not yet active, for the wrong audience, or subject to an invitation the customer does not have. If a necessary customer fact is unknown, label that offer conditional rather than inventing eligibility.
6. Compare only available awards. Convert a points award to dollars only if a supplied document explicitly provides a conversion rate and redemption channel. A number of points is never the same dollar amount as the same numeric dollar figure.
7. Recommend the highest documented available award matching the customer's requested audience and conditions.
8. If an invitation-only offer is discussed, explicitly state that it requires an invitation. When the customer says they have no invitation, state it is unavailable to them and do not frame it as a recommendation.

## Mandatory final-response checklist

Before sending the response, make sure the actual customer-facing prose includes, whenever documented for the selected offer:

- a direct recommendation using the complete card name;
- that the offer is current as of the observed date and its campaign window;
- the exact bonus amount and unit;
- the eligible-purchase threshold;
- the qualification period after opening;
- new-customer and good-standing requirements;
- the annual fee;
- for points, the documented redemption rate, resulting cash-equivalent value, and redemption channel; and
- the invitation restriction for any invitation-only alternative mentioned.

If the documents establish a current eligible award, never say “no documented current sign-up offers,” “I can’t identify a best,” “I lack a promotion catalog,” or “share offers and I can compare them.”

## Response structure

Use concise ordinary prose or bullets, not JSON:

1. **Recommendation:** name the selected card and say it is the best documented available welcome award as of the observed date.
2. **Offer terms:** state campaign dates, native award, spend requirement, and qualification period.
3. **Eligibility, value, and fee:** state documented status conditions, accurate points conversion, and annual fee.
4. **Unavailable alternatives:** briefly distinguish expired, non-bonus, or invitation-only offers without recommending them.
5. When useful, say the comparison is limited to the supplied documents.

Do not subtract required spend or annual fees from a bonus unless the customer specifically asks for a net-cost calculation.

## Optional deterministic helpers

The scripts below operate only on facts already extracted from the supplied documents. They do not retrieve information or take customer action, and using them must not delay the completed response.

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

The output has `eligible`, `conditional`, `excluded`, and `unverified` groups plus `recommendation`. Make an unconditional recommendation only when `validation.selected_pool` is `eligible` and `validation.recommendation_is_current` is true.

### Compose verified recommendation prose

```sh
python3 scripts/compose_signup_recommendation.py < selected_offer.json
```

Input is one verified selected-offer JSON object with `as_of`, `start`, `end`, `card_name`, `reward_amount`, `reward_unit`, `spend_requirement_usd`, and `qualification_period`, plus applicable status, fee, value, redemption, and exclusion fields. It emits `{"ok": true, "message": "..."}`. Use its `message` as customer-facing prose without replacing it with a progress message.
