---
name: credit-card-signup-bonus-recommender
description: Compare documented credit-card sign-up awards as of an observed date, apply customer eligibility and invitation restrictions, and deliver a complete recommendation including qualifying terms, point value, and annual fee.
---

# Credit-card sign-up bonus recommender

Use this Skill for informational requests to identify the best currently available credit-card sign-up bonus in points, cash back, or statement credit. This Skill does not apply for cards, access customer accounts, assess approval likelihood, or promise approval.

## Required completion behavior

When the task context supplies offer documents, a current-date observation, and enough eligibility clarification, provide the **completed customer-facing comparison in the next substantive message**. The supplied documents are source material; do not ask the customer to provide them again and do not say that offer information is unavailable.

Do not send a plan, a progress update, JSON, or a statement that a comparison could be done later. The customer-facing message must itself name the recommended card and state the material terms. Do not claim that no current offers exist until every documented positive sign-up award has been classified against the observed date and eligibility facts.

## Evidence and eligibility method

1. Use the calendar date in the supplied current-time observation as the as-of date. Do not substitute a guessed date.
2. Read all supplied documents that establish any of the following:
   - sign-up award amount and reward unit;
   - promotion start and end dates;
   - spend threshold and qualification period;
   - new-customer, good-standing, audience, or invitation conditions;
   - annual fee; or
   - documented reward redemption value.
3. Classify a document as a positive sign-up award only if it awards points, cash back, or a statement credit for opening/qualifying on a new account. Do **not** treat an ordinary earn rate, introductory APR, application terms, or fee waiver alone as a sign-up bonus.
4. Treat offer endpoints as inclusive: an offer is active only if `start_date <= as_of_date <= end_date`. An offer with a missing start or end date is not established as currently available.
5. Exclude offers that are expired, not yet started, for a different requested audience, require an invitation the customer does not hold, or require new-customer status when the customer is known not to be new. If a relevant status is unknown, describe the offer as conditional rather than silently assuming eligibility.
6. Rank eligible awards by documented cash-equivalent value. Dollar statement credits have their stated dollar value. Convert points only when a document supplies a redemption rate. Never describe a point award as the same numerical amount in dollars.
7. Do not subtract annual fees or required spending from the bonus unless the customer asks for a net-cost calculation. Still disclose a documented annual fee when the customer asks about fees or when it is material to the comparison.
8. An invitation-only offer is not an available recommendation for a customer who reports no invitation. If it is useful to mention that offer, explicitly state both that it requires an invitation and that it is unavailable to that customer.

Use `scripts/evaluate_signup_offers.py` when practical after extracting the document facts. It only classifies facts supplied on stdin; it does not retrieve documents or replace the executor's review of the source documents.

## Mandatory answer contents

For a positive recommendation, write a direct answer in this order:

1. **Recommendation.** State the card name and that it is the best/highest documented currently available eligible sign-up award as of the observed date, limited to the supplied documents.
2. **Award and qualification.** State the exact native reward amount and unit, exact eligible-purchase threshold, and exact time to meet it after account opening. Include offer-window dates, new-customer status, and good-standing requirement when documented.
3. **Value and fee.** For points, state the documented per-point redemption rate, the resulting dollar value, and the documented redemption channel. State the annual fee when documented and requested/material.
4. **Material exclusions.** Briefly identify only material alternatives. For an invitation-only alternative, clearly say it is unavailable without an invitation when the customer does not have one. Expired bonus promotions may be identified as expired.
5. **Scope.** State that the conclusion is based on the documented offers supplied for this request, and identify supporting document titles or IDs when useful.

Before sending, confirm that the actual prose contains all applicable facts rather than merely referring to source documents:

- recommended card name;
- reward amount and reward unit;
- dollar spend requirement;
- qualification period after opening;
- campaign dates;
- new-customer and good-standing conditions;
- point conversion and resulting dollar amount, when documented;
- annual fee, when documented and requested/material; and
- invitation restriction for every discussed invitation-only alternative.

Never use wording such as “no documented current sign-up offers,” “I can’t identify a best,” “the chat does not include offer data,” or “share the offers and I can compare them” when relevant source documents are supplied in the task context.

## Evaluator interface

`scripts/evaluate_signup_offers.py` reads a JSON object from stdin and emits a JSON object to stdout. It performs no network, account, application, banking, or customer action.

Input schema:

```json
{
  "as_of": "YYYY-MM-DD or ISO-8601 timestamp",
  "desired_audience": "personal | business | any",
  "is_new_customer": true,
  "invited_offer_ids": ["offer IDs for which the customer holds an invitation"],
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
      "reward_unit": "native unit",
      "usd_per_reward_unit": "documented positive decimal or null",
      "spend_requirement_usd": "documented non-negative decimal or null",
      "qualification_months": "documented positive decimal or null",
      "annual_fee_usd": "documented non-negative decimal or null",
      "conditions": ["documented condition"]
    }
  ]
}
```

Set `invited_offer_ids` to an empty array when invitation status is explicitly known to be none. Omit it when unknown. Set `is_new_customer` to `true`, `false`, or `null`/omit when unknown. The output's selected recommendation is usable only if `validation.recommendation_is_current` is true. Check every extracted fact against the source documents before responding.

Runnable call:

```sh
python3 scripts/evaluate_signup_offers.py < extracted_offers.json
```

## Response composer interface

After determining a valid selected offer, `scripts/compose_signup_recommendation.py` can create prose that includes the required material terms. Supply only facts extracted from the supplied task documents. Its stdout field `message` is customer-facing prose: send it verbatim or adapt it without removing required terms.

```sh
python3 scripts/compose_signup_recommendation.py < selected_offer.json
```

Its input requires the selected offer's name, award, spend threshold, qualification period, campaign dates, and as-of date. It rejects missing mandatory facts rather than guessing them. Optional annual-fee, reward-value, good-standing, and exclusion fields are included only when supported by the documents.
