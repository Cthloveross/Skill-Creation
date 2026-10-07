---
name: credit-card-signup-bonus-recommender
description: Compare documented credit-card welcome offers and recommend the best currently active offer available to the customer. Use when a customer asks about points, cash-back, statement-credit, or annual-fee sign-up promotions.
---

# Credit-card sign-up bonus recommender

Provide an informational, evidence-grounded comparison. Do not apply for a card, access customer accounts, predict approval, or promise eligibility beyond the supplied terms.

## Source-of-truth rule

The promotion and card documents supplied in the task context are the offer catalog for this request. The `get_current_time` observation is the authoritative as-of date. Read and use those materials directly. Do **not** tell the customer that the catalog, promotion terms, current date, or annual-fee information is unavailable when supplied documents contain it. Do not ask the customer to re-supply documents already in context.

After the customer has provided relevant audience and invitation information, give the completed recommendation in the next substantive customer-facing message. Never substitute a plan, JSON payload, progress update, status marker, refusal, or out-of-scope marker for the recommendation.

## Evaluation method

1. Extract the calendar date from the current-time observation.
2. Review all supplied documents that establish a welcome award, offer window, eligibility restriction, redemption value, or annual fee.
3. For each potential welcome offer, identify:
   - card name and intended audience;
   - campaign start and end dates;
   - reward amount and native unit;
   - eligible-purchase threshold and deadline after account opening;
   - new-customer, good-standing, invitation, and other eligibility requirements; and
   - annual fee and any explicitly documented reward redemption value.
4. A dated promotion is current only when `start date <= observed date <= end date`; both endpoints are inclusive.
5. Count only a positive sign-up award in points, cash back, or statement credit. Do not treat an earn rate, 0% APR, application eligibility, or an annual-fee waiver by itself as a points/cash-back welcome award.
6. Exclude offers that are expired, not started, for a different audience, or invitation-only when the customer does not hold the invitation. If a necessary eligibility fact is unknown, label that offer conditional rather than available.
7. Convert reward units to dollars only when the supplied documents explicitly provide a redemption rate and channel. Never describe a quantity of points as the same numeric dollar amount.
8. Recommend the highest documented **available** award. If no common documented valuation permits a value ranking, explain that limitation and compare native reward amounts rather than inventing a conversion.

## Non-negotiable completion gate

Before sending the final answer, confirm all of the following internally:

- An active, customer-eligible documented award is named explicitly.
- The answer gives the exact card name, not merely a generic category.
- The answer includes the exact bonus amount and unit, purchase requirement, and post-opening qualification period.
- The answer does not deny that a documented active offer exists.
- If the customer asked about annual fees and a fee is documented for the recommendation, that fee is included.
- An invitation-only offer is never framed as available when the customer reports no invitation.

If an active eligible offer is documented, do not answer with phrases such as “no documented current sign-up offers,” “I can’t identify a best,” “I lack a promotion catalog,” “no promotion terms are available,” or “share offers and I can compare them.”

## Required customer-facing response

Use ordinary prose or bullets, not a machine-readable response. For the selected card, include:

1. A direct recommendation that names the card and says it is the best documented available sign-up offer as of the observed date.
2. The promotion window and confirmation that it is active as of that date.
3. The exact reward amount and unit.
4. The eligible-purchase threshold and qualification period after opening.
5. Documented new-customer and good-standing conditions.
6. The documented annual fee when relevant to the customer's request.
7. If documented, the reward redemption rate, dollar equivalent, and redemption channel.

If mentioning a seemingly larger invitation-only alternative, clearly say that it requires an invitation and is unavailable to a customer who does not have one. It is acceptable to omit such alternatives when they would distract from the available recommendation. State that the comparison is limited to supplied documents only if useful.

Do not subtract spending requirements or annual fees from the advertised award unless the customer specifically asks for a net-cost calculation.

## Optional deterministic helpers

The helpers operate only on facts extracted from supplied documents. They do not retrieve data and do not take card, banking, or customer-account actions. Their use must not delay the completed answer.

### Filter and rank extracted offers

```sh
python3 scripts/evaluate_signup_offers.py < extracted_offers.json
```

Input is a JSON object:

```json
{
  "as_of": "YYYY-MM-DD or ISO timestamp",
  "desired_audience": "personal | business | any",
  "is_new_customer": true,
  "invited_offer_ids": ["offer identifiers for invitations actually held"],
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
      "qualification_period": "the first 1 month",
      "annual_fee_usd": 0,
      "conditions": ["documented condition"]
    }
  ]
}
```

It emits JSON with `eligible`, `conditional`, `excluded`, `unverified`, and `recommendation`. A recommendation is unconditional only when `validation.selected_pool` is `eligible`. The executor remains responsible for accurately extracting facts from the supplied documents and for presenting the result to the customer.

### Render verified recommendation prose

```sh
python3 scripts/compose_signup_recommendation.py < selected_offer.json
```

Input is one already-verified, active selected-offer object containing `as_of`, `start`, `end`, `card_name`, `reward_amount`, `reward_unit`, `spend_requirement_usd`, and `qualification_period`. It may additionally contain `new_customer_required`, `good_standing_required`, `annual_fee_usd`, `usd_per_reward_unit`, `redemption_channel`, and `exclusions`.

The script emits `{"ok": true, "message": "..."}`. Use the `message` itself as the customer-facing answer; do not replace it with a progress message.