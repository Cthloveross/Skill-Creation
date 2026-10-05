---
name: credit-card-signup-bonus-recommender
description: Use documented credit-card promotions and an observed current date to recommend the highest-value currently available sign-up award for an eligible customer, with complete qualification terms, reward value, fees, and invitation restrictions.
---

# Credit-card sign-up bonus recommender

Use this Skill for informational requests about the best current credit-card sign-up bonus in points, cash back, or statement credit. It does not apply for cards, inspect customer accounts, determine approval odds, or promise approval.

## Completion rule

When the task context includes promotion documents, a current-time observation, and sufficient customer eligibility facts, give the completed customer-facing comparison in the **next substantive message**. The supplied documents are evidence available to use. Do not ask the customer to provide those documents, claim that the chat lacks offer data, send JSON, send a progress update, or defer the comparison.

A response is incomplete unless it actually names a recommended card and states its offer terms in prose. Never conclude that no current offer is documented until each documented positive sign-up award has been checked for timing and eligibility.

## Required workflow

1. Take the date from the supplied current-time observation as the as-of date. Do not guess or substitute a date.
2. Review every supplied document that may establish:
   - a new-account points, cash-back, or statement-credit award;
   - campaign start/end dates;
   - spend requirement and qualification period;
   - new-customer, good-standing, audience, or invitation conditions;
   - annual fee; or
   - a reward redemption rate.
3. A positive sign-up award is a reward for opening and qualifying on a new account. Do not mistake an ordinary earn rate, an introductory APR, application details, or a fee waiver alone for such an award.
4. Treat campaign endpoints as inclusive. An award is current only when `start_date <= observed_date <= end_date`. If either endpoint is undocumented, do not represent the award as currently available.
5. Exclude an award that is expired, not started, for the wrong audience, requires an invitation the customer lacks, or requires new-customer status the customer does not have. If a relevant customer fact is unknown, label the offer conditional instead of assuming eligibility.
6. Compare eligible awards by documented cash-equivalent value. A statement credit has its stated dollar value. Convert points only when a documented redemption rate supports it. Never recast a point total as the same numeric dollar amount.
7. Do not subtract the annual fee or required spend from the award unless the customer requests a net-cost calculation. Disclose a documented annual fee when the customer asks about fees or it is material to the recommendation.
8. An invitation-only offer is not available to a customer who says they have no invitation. If it is discussed, explicitly state that it requires an invitation and is unavailable to that customer.

Use `scripts/evaluate_signup_offers.py` after extracting facts when useful. It classifies only the facts provided on stdin; it does not retrieve documents or replace review of their contents.

## Mandatory response gate

Before sending the final customer-facing answer, verify that the actual answer text—not merely a plan or a source reference—contains all applicable items:

- the recommended card's complete name;
- that it is currently available and eligible as of the observed date;
- the native reward amount and unit;
- the eligible-purchase threshold;
- the qualification period after opening;
- promotion window dates;
- documented new-customer and good-standing conditions;
- documented point conversion rate, resulting dollar value, and redemption channel, where applicable;
- documented annual fee when requested or material; and
- an invitation restriction for every invitation-only alternative mentioned.

If source documents establish an eligible current offer, do **not** use phrases such as “no documented current sign-up offers,” “I can’t identify a best,” “offer information is unavailable,” or “share the offers and I can compare them.”

## Answer structure

Write a concise, direct answer in this order:

1. **Recommendation:** Name the card and say it is the highest documented currently available eligible sign-up award, limited to the supplied documents and observed date.
2. **Terms:** Give the campaign dates, exact reward amount/unit, required eligible spend, qualification period, and eligibility conditions.
3. **Value and fee:** Explain a documented points conversion and dollar value without inflating the award. State the documented annual fee when applicable.
4. **Material exclusions:** Briefly explain why any larger-looking invitation-only or expired promotion is not an available alternative. Do not call an unavailable offer a recommendation.
5. **Scope:** State that the comparison is based on the documented offers supplied for the request.

## Evaluator interface

`scripts/evaluate_signup_offers.py` reads one JSON object from stdin and emits one JSON object to stdout. It performs no network, account, application, banking, or customer action.

Input schema:

```json
{
  "as_of": "YYYY-MM-DD or ISO-8601 timestamp",
  "desired_audience": "personal | business | any",
  "is_new_customer": true,
  "invited_offer_ids": ["IDs for invitations the customer holds"],
  "offers": [
    {
      "id": "stable extracted ID",
      "card_name": "display name",
      "audience": "personal | business | any",
      "start": "YYYY-MM-DD",
      "end": "YYYY-MM-DD",
      "requires_invitation": false,
      "new_customer_required": true,
      "reward_amount": "positive decimal",
      "reward_unit": "native reward unit",
      "usd_per_reward_unit": "positive decimal or null",
      "spend_requirement_usd": "non-negative decimal or null",
      "qualification_months": "positive decimal or null",
      "annual_fee_usd": "non-negative decimal or null",
      "conditions": ["documented condition"]
    }
  ]
}
```

Set `invited_offer_ids` to `[]` when the customer explicitly has no invitation; omit it when invitation status is unknown. Set `is_new_customer` to `true`, `false`, or `null` when unknown. Only treat the output recommendation as unconditional when `validation.recommendation_is_current` is true and `validation.selected_pool` is `eligible`.

Runnable call:

```sh
python3 scripts/evaluate_signup_offers.py < extracted_offers.json
```

## Response composer interface

`scripts/compose_signup_recommendation.py` turns an already verified, selected offer into customer-facing prose. Supply only facts supported by task documents. Its `message` result may be sent verbatim or edited only if no required fact is removed.

```sh
python3 scripts/compose_signup_recommendation.py < selected_offer.json
```

The composer rejects a non-current offer or missing mandatory award, window, spend, and period data rather than guessing.