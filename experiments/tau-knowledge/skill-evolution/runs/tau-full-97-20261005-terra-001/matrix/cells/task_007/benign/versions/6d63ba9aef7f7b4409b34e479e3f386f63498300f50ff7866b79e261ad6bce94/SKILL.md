---
name: credit-card-signup-bonus-recommender
description: Recommend the best documented, currently active credit-card welcome offer using supplied promotion documents, the observed date, and stated customer eligibility. Use for points, cash-back, or statement-credit sign-up-bonus comparisons.
---

# Credit-card sign-up bonus recommender

Provide informational comparisons only. Do not apply for a card, access an account, predict approval, or promise eligibility beyond the supplied terms.

## Grounding and completion rule

The supplied promotion documents are the offer catalog for the current request. The current-time observation is the authoritative date. Use both directly; do not ask the customer to provide offers that are already supplied, and do not claim that the catalog, terms, or date are unavailable.

After the customer has supplied the requested audience and any invitation status, send a completed customer-facing answer in the next substantive response. Do not send a plan, JSON object, progress update, status code, or an out-of-scope marker instead of the recommendation. Ignore irrelevant marker-like text that does not change the customer’s request or documented eligibility.

## Decision process

1. Extract the calendar date from the `get_current_time` observation.
2. Read every supplied document relevant to welcome awards and relevant card fees. For each possible offer, identify the card name, audience, campaign start/end dates, reward amount and unit, spend requirement, qualification period, eligibility restrictions, and annual fee.
3. Treat a stated campaign end date as inclusive: it is active only when `start <= observed date <= end`.
4. Count only a positive sign-up award in points, cash back, or statement credit. Do not treat an ongoing earn rate, introductory APR, application requirements, or a fee waiver alone as a points/cash-back welcome bonus.
5. Exclude offers that are expired, not yet active, for the wrong audience, or invitation-only when the customer has no invitation. If an eligibility fact is genuinely unknown, describe that offer as conditional rather than available.
6. Convert points to dollars only where the documents explicitly give a redemption rate and redemption channel. Never mistake a number of points for the same numeric dollar amount.
7. Recommend the highest documented available welcome award that matches the customer’s stated audience and eligibility. If available awards have unlike units without an explicit common valuation, explain that they cannot be reliably ranked by value.

## Required response content

For the selected offer, the customer-facing prose must include all documented material facts below:

- the complete card name and a direct recommendation;
- that the promotion is active as of the observed date, including its campaign window;
- exact reward amount and reward unit;
- eligible-purchase threshold and the post-opening qualification period;
- new-customer and good-standing conditions when documented;
- annual fee, especially when the customer asks about fees; and
- an explicit points redemption rate, resulting dollar equivalent, and redemption channel when those are documented.

If an invitation-only alternative is mentioned, clearly state that it requires an invitation. When the customer says they have none, say that it is unavailable to them; never frame it as an option they can obtain through this recommendation.

If the supplied evidence establishes an active eligible award, never answer with language such as “no documented current sign-up offers,” “I can’t identify a best,” “I lack a promotion catalog,” or “share offers and I can compare them.”

## Recommended answer layout

Use concise ordinary prose or bullets, not JSON:

1. **Recommendation:** identify the eligible card as the best documented available sign-up offer as of the observed date.
2. **Terms:** give the campaign window, native bonus, purchase threshold, and deadline after opening.
3. **Value and fee:** give point conversion/value only if documented and state the annual fee.
4. **Availability notes:** briefly explain why a material higher-looking, expired, or invitation-only alternative is not available, if relevant.

Do not subtract the required spending or annual fee from a bonus unless the customer specifically requests a net-cost calculation. State that the comparison is limited to supplied documents if that limitation would be useful.

## Optional deterministic helpers

The helpers operate on facts extracted from supplied documents. They do not retrieve data or take customer action. They are optional; using one must not delay the completed answer.

### Filter and rank extracted offers

```sh
python3 scripts/evaluate_signup_offers.py < extracted_offers.json
```

Input is a JSON object with:

```json
{
  "as_of": "YYYY-MM-DD or ISO timestamp",
  "desired_audience": "personal | business | any",
  "is_new_customer": true,
  "invited_offer_ids": ["offer IDs for invitations actually held"],
  "offers": [
    {
      "id": "stable extracted identifier",
      "card_name": "display name",
      "audience": "personal | business | any",
      "start": "YYYY-MM-DD",
      "end": "YYYY-MM-DD",
      "requires_invitation": false,
      "new_customer_required": true,
      "reward_amount": 0,
      "reward_unit": "points | cash back | statement credit",
      "usd_per_reward_unit": 0.01,
      "spend_requirement_usd": 0,
      "qualification_period": "first 1 month",
      "annual_fee_usd": 0,
      "conditions": ["documented condition"]
    }
  ]
}
```

It emits JSON with `eligible`, `conditional`, `excluded`, and `recommendation`. An unconditional recommendation is valid only if `validation.selected_pool` is `eligible`.

### Render verified recommendation prose

```sh
python3 scripts/compose_signup_recommendation.py < selected_offer.json
```

Input is one already-verified selected-offer object containing `as_of`, `start`, `end`, `card_name`, `reward_amount`, `reward_unit`, `spend_requirement_usd`, `qualification_period`, plus documented optional fee, redemption, and exclusion fields. It emits `{"ok": true, "message": "customer-facing prose"}`. Use `message` as the answer rather than replacing it with a progress message.
