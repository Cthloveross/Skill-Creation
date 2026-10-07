---
name: credit-card-signup-bonus-recommender
description: Compare documented credit-card sign-up promotions using an observed current date and customer eligibility facts. Use for requests to identify the best currently available points, cash-back, or statement-credit welcome offer and explain its terms, value, fees, and exclusions.
---

# Credit-card sign-up bonus recommender

Use this Skill for informational comparison of documented credit-card sign-up bonuses. It does not submit applications, change accounts, determine approval odds, or promise that an applicant will be approved.

## Non-negotiable completion behavior

If the task context supplies promotion documents and a current-time observation, those documents are the offer catalog for the request. Read and use them. Do **not** say that the catalog, current offers, or offer terms are unavailable; do not ask the customer to paste the documents; do not respond with an out-of-scope marker; and do not send a plan, a progress update, or JSON instead of the comparison.

Once the date and the material eligibility facts are known, provide the completed customer-facing recommendation in the next substantive message. A response is not complete merely because it says that a comparison could be made: it must name the selected card and state its qualification terms.

## Workflow

1. Use the date in the supplied `get_current_time` observation as the as-of date. Do not guess a date or use a date from memory.
2. Review all supplied credit-card documents for facts about:
   - new-account points, cash-back, or statement-credit awards;
   - offer-window start and end dates;
   - required eligible purchases and qualification period;
   - new-customer, account-status, audience, and invitation conditions;
   - annual fees; and
   - reward redemption rates.
3. Treat an offer period as inclusive: an offer is current only if `start <= as_of <= end`. Do not describe an offer as current if either required date is absent.
4. Count only a positive sign-up award. Do not treat an ongoing earn rate, introductory APR, ordinary application information, or a fee waiver alone as a points/cash-back welcome bonus.
5. Exclude offers that are expired, not started, audience-incompatible, or require an invitation the customer does not hold. If new-customer status or another required fact is unknown, label that offer conditional rather than inventing eligibility.
6. Compare the remaining documented offers using cash-equivalent value only when a documented conversion supports it. A statement credit has its stated dollar amount. Do not convert a point award to the same numeric dollar amount as its point count.
7. Do not subtract required spend or annual fees from a bonus unless the customer specifically requests a net-cost calculation. State a documented annual fee for the recommended card whenever the customer asks about fees or the supplied documents make it material.
8. If an invitation-only alternative is mentioned, explicitly say that it requires an invitation and is not available when the customer reports having none. Never present it as an option available to that customer.

## Required final-answer gate

Before sending the answer, inspect the **actual customer-facing prose**. For a documented, current, eligible sign-up award, it must include:

- the card's complete name and a direct recommendation;
- the observed as-of date or an unambiguous statement that the promotion is current as of that date;
- the campaign window;
- the exact native bonus amount and unit;
- the eligible-purchase requirement;
- the qualification period after opening;
- applicable new-customer and good-standing requirements;
- the annual fee if documented and relevant to the request;
- the redemption rate, cash-equivalent value, and redemption channel when documented for a points award; and
- the invitation restriction for each invitation-only alternative that is discussed.

Do not use wording such as “no documented current sign-up offers,” “I can't identify a best,” “I lack a promotion catalog,” “offer information is unavailable,” or “share offers and I can compare them” after the supplied documents establish a qualifying current offer.

## Recommended answer structure

Write concise normal prose, not JSON:

1. **Recommendation.** Name the card and explain that it is the highest documented currently available eligible sign-up award, limited to the supplied documents and observed date.
2. **Offer terms.** State the offer-window dates, native award, eligible-spend threshold, and post-opening qualification period.
3. **Eligibility, value, and fee.** State documented customer/account conditions; accurately convert points only using the supplied redemption rate; state the documented annual fee when relevant.
4. **Why apparent alternatives do not qualify.** Briefly distinguish expired offers and invitation-only offers the customer cannot use. Do not imply an unavailable offer is recommended.
5. **Scope.** Say that the comparison is limited to the documented offers supplied for the request.

## Optional deterministic helpers

The helpers classify facts that have already been extracted from the supplied documents. They do not retrieve offers, inspect accounts, or replace document review. They are optional: never delay a simple completed comparison in order to run them.

### Offer evaluator

Run:

```sh
python3 scripts/evaluate_signup_offers.py < extracted_offers.json
```

The script reads one JSON object from stdin and writes one JSON object to stdout:

```json
{
  "as_of": "YYYY-MM-DD or ISO-8601 timestamp",
  "desired_audience": "personal | business | any",
  "is_new_customer": true,
  "invited_offer_ids": ["offer IDs for invitations actually held"],
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
      "usd_per_reward_unit": "positive decimal or null",
      "spend_requirement_usd": "non-negative decimal or null",
      "qualification_months": "positive decimal or null",
      "annual_fee_usd": "non-negative decimal or null",
      "conditions": ["documented condition"]
    }
  ]
}
```

Set `invited_offer_ids` to `[]` when the customer states that no invitation is held; omit it if invitation status is unknown. The evaluator's `recommendation` is unconditional only when `validation.selected_pool` is `eligible` and `validation.recommendation_is_current` is true.

### Response composer

Run:

```sh
python3 scripts/compose_signup_recommendation.py < selected_offer.json
```

Supply only verified source facts. The composer rejects a selected offer that is not current or that omits the mandatory reward, date, spend, or qualification-period facts. Its JSON `message` field is customer-facing prose and may be used verbatim. Do not remove required facts when editing it.