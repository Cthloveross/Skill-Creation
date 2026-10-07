---
name: credit-card-signup-bonus-recommender
description: Evaluate documented credit-card sign-up bonuses against an observed date, customer type, new-customer status, and invitation status, then provide a completed recommendation with material offer terms, reward value, and requested fees.
---

# Credit-card sign-up bonus recommender

Use this Skill to answer an informational request for the best currently available credit-card sign-up bonus. Do not apply for a card, access an account, determine approval odds, or promise approval.

## Non-negotiable response rule

When the task supplies promotion documents, an as-of date, and enough customer clarification to assess an offer, the **next substantive customer-facing message must be the completed comparison and recommendation**. Do not reply with a plan, an acknowledgement, JSON, a request for documents already supplied in the task context, or a claim that no offer list/source data is available.

The supplied task documents are the source data to evaluate. Read all documents that can establish a promotional award, campaign dates, card fee, reward conversion rate, customer eligibility, or invitation restriction.

A completed answer explicitly names a card and repeats the selected offer's reward amount, spend threshold, and qualifying time period in ordinary prose. Do not merely say that a recommendation is possible or describe a future comparison method.

## Method

1. Obtain or use the supplied current-time observation and use its calendar date as the as-of date.
2. Identify the requested audience (personal, business, or any), whether the customer is new if known, and whether they hold each required invitation.
3. Extract each **positive sign-up award** from the supplied documents. Record:
   - card name and applicable audience;
   - offer start and end date;
   - native reward amount and unit;
   - eligible-purchase threshold and time to qualify;
   - new-customer and good-standing conditions;
   - invitation requirement;
   - documented point redemption rate;
   - annual fee when the user asks about fees; and
   - source document ID/title.
4. Do not misclassify an ongoing earn rate, an APR promotion, ordinary application terms, or a fee waiver as a points/cash/statement-credit sign-up award.
5. Treat campaign endpoints as inclusive. An offer is currently active only when `start <= as_of_date <= end`. Do not assume an offer with a missing endpoint is active.
6. Exclude awards outside the requested audience, outside their campaign window, or requiring an invitation the customer does not have. Exclude a new-customer offer only when the customer is known not to be new; otherwise retain it as conditional and disclose that condition.
7. Rank remaining offers by documented cash-equivalent bonus value. A statement credit or dollar-denominated reward has its stated value. Convert a points award only with a documented conversion rate. Do not call a point total the same number of dollars.
8. Do not subtract annual fees or required spending from the bonus unless the customer specifically asks for a net-cost calculation.

Use `scripts/evaluate_signup_offers.py` after extracting facts when practical. It has no retrieval capability and only evaluates JSON facts provided by the executor. Its output checks the classification; it does not replace reading the task documents.

## Required customer-facing answer

For a positive recommendation, use this order, adapting only to documented facts:

1. **Recommendation:** name the recommended card and say it is the highest documented currently available sign-up award for the requested audience as of the observed date.
2. **Bonus and qualification:** state the exact native reward amount/unit, exact eligible-purchase threshold, and exact qualification period after opening. Include campaign dates and documented new-customer/good-standing conditions.
3. **Value and fee:** for points, state the documented redemption rate and resulting dollar redemption value, identifying the documented redemption channel. State the card's documented annual fee if the user asked about annual fees.
4. **Relevant exclusions:** briefly identify material alternatives that are expired or unavailable. If an invitation-only card is mentioned, explicitly say it requires an invitation and is not available when the customer said they have none. Never present it as the customer's option.
5. State that the conclusion is limited to the documented offers supplied for this task, and cite relevant document IDs or titles.

Before sending, verify the final prose itself contains all of the following, not merely an implied reference:

- recommended card name;
- reward number and reward unit;
- dollar spend number;
- qualifying period (for example, “first 1 month” or “first month”);
- promotion dates when documented;
- the new-customer and good-standing qualifications when documented;
- point conversion and dollar equivalent when documented;
- requested annual fee; and
- an explicit invitation restriction for any discussed invitation-only alternative.

Only say that no currently available sign-up award exists after classifying every documented positive award and explaining the relevant exclusions. Never use phrases such as “no documented current sign-up offers,” “I can’t identify a best,” or “the chat does not include offer data” if the supplied documents contain relevant offer facts.

## Evaluator script interface

`scripts/evaluate_signup_offers.py` reads one JSON object from stdin and emits one JSON object to stdout. It performs no network, account, application, or banking action.

Input schema:

```json
{
  "as_of": "YYYY-MM-DD or ISO-8601 timestamp",
  "desired_audience": "personal | business | any",
  "is_new_customer": true,
  "invited_offer_ids": ["offers for which the customer has an invitation"],
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
      "reward_unit": "points, statement credit, or other native unit",
      "usd_per_reward_unit": "documented positive decimal or null",
      "spend_requirement_usd": "documented decimal or null",
      "qualification_months": "documented positive decimal or null",
      "annual_fee_usd": "documented decimal or null",
      "conditions": ["documented material terms"]
    }
  ]
}
```

If invitation status is explicitly known to be none, pass an empty `invited_offer_ids` array. If it is unknown, omit that property. `is_new_customer` may be `true`, `false`, omitted, or `null`; omitted/null means unknown.

The successful output includes `recommendation`, `eligible`, `conditional`, `excluded`, `unverified`, and `validation`. A usable selected offer must have `validation.recommendation_is_current: true`. Check the extracted facts against source documents before writing the answer.

Runnable executor call:

```sh
python3 scripts/evaluate_signup_offers.py < extracted_offers.json
```

Malformed JSON or malformed fields produce `{"ok": false, "error": "..."}`. Correct the extraction from the supplied documents; do not guess missing facts.
