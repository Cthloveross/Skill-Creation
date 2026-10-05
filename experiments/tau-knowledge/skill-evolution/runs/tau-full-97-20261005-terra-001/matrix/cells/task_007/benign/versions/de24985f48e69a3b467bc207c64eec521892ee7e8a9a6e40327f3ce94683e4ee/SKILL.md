---
name: credit-card-signup-bonus-recommender
description: Compare documented credit-card sign-up bonuses for a customer seeking points, cash back, or statement-credit value. Use when current offer dates, card audience, invitation status, new-customer conditions, and spending requirements must be evaluated without recommending unavailable promotions.
---

# Credit-card sign-up bonus recommender

Use this Skill to answer informational card-shopping requests. It does not apply for a card, determine credit approval, access an account, or require identity verification.

## Gather the decision facts

Before making a recommendation, obtain from the current task materials:

1. The current/as-of date (use the provided current-time observation when available).
2. Whether the request is for a personal card, business card, or either.
3. Whether the customer has an invitation for every relevant invitation-only offer.
4. Whether new-customer status is confirmed, denied, or unknown.
5. Every documented sign-up **award** candidate: card name, dates, reward amount/unit, spend threshold, qualification period, eligibility restrictions, and source.
6. A documented point-to-USD rate before comparing points with cash or statement credits.

A sign-up award is a positive award of points, cash back, or statement credit. Do not treat an annual-fee waiver, an APR promotion, standard earn rate, or ordinary application terms as a sign-up award unless the user explicitly asks to compare that different benefit.

## Required availability workflow

Build a candidate list before writing the response. Do not infer that an offer is unavailable merely because other offers are expired or invitation-only.

For each documented candidate:

- Treat a stated offer window as inclusive: it is active when `start date <= as-of date <= end date`.
- Exclude an offer when its window has ended or not started, its audience conflicts with the request, the customer affirmatively lacks its required invitation, or the customer is known not to meet a required new-customer condition.
- Treat a currently active offer as **conditional**, not unavailable, when a required status (such as being a new customer) is unknown.
- Keep invitation-required offers conditional only if invitation status is unknown. If the customer said they do not have the invitation, exclude them.
- Mark an offer unverified rather than current if its complete date window is not documented.
- Never invent an offer, a conversion rate, eligibility, or a reward amount from unrelated card information.

Run `scripts/rank_signup_offers.py` after extraction. It classifies and ranks the candidates. Its input contains facts extracted from the current task, not facts embedded in this Skill.

**Hard pre-response check:** Do not say that no documented current sign-up award exists until every extracted positive-award candidate has been checked against the as-of date and placed in `excluded`, `unverified`, or `unrankable`. If `eligible` is nonempty, recommend its first item. Otherwise, if `conditional` is nonempty, name its first item and explicitly disclose its unresolved conditions.

## Compare and respond

Use documented cash-equivalent value to rank active candidates:

- A USD statement credit has a conversion of `$1 per $1`.
- Convert points only with a documented redemption rate; otherwise retain the native amount and classify the award as unrankable for value ranking.
- Do not call a native point count a dollar amount. If a conversion is documented, provide both the native reward and the resulting dollar equivalent.

The answer must:

1. Directly name the best documented currently available (or, if necessary, conditional) offer for the requested audience.
2. State the exact native sign-up award.
3. State the qualifying eligible-purchase threshold and qualification period.
4. State the offer end date and material requirements, including new-customer/account-good-standing requirements where documented.
5. State unresolved requirements conditionally rather than claiming they are met.
6. If a seemingly larger award is relevant, explain why it is not available to this customer (for example, required invitation not received), rather than presenting it as an option.
7. Describe the conclusion as limited to the documented offers supplied for this task, not the entire market.
8. Identify the supporting source document(s).

A compact response structure is:

```text
Recommendation: [card] is the highest-value documented [available/conditional] sign-up award for your requested card type as of [date].
Bonus and qualification: Earn [native reward] after [eligible-spend threshold] in [period] after opening. [State new-customer/good-standing terms and end date.]
Value: [documented USD equivalent, only if supported].
Availability note: [why relevant larger, expired, or invitation-only alternatives are excluded].
Source: [document title or ID].
```

If no candidate survives the hard pre-response check, say no documented current eligible sign-up award was found and briefly distinguish expired, unsupported, or unavailable offers. Do not substitute an expired or invitation-only promotion.

## Ranking script

`scripts/rank_signup_offers.py` reads one JSON object from standard input and writes one JSON object to standard output. It performs no retrieval; the executor supplies all extracted evidence.

### Input schema

```json
{
  "as_of": "ISO-8601 timestamp or YYYY-MM-DD",
  "desired_audience": "personal | business | any",
  "invited_offer_ids": ["offer IDs for invitations the customer has"],
  "is_new_customer": true,
  "offers": [
    {
      "id": "stable offer ID",
      "card_name": "display name",
      "audience": "personal | business | any",
      "offer_start": "YYYY-MM-DD",
      "offer_end": "YYYY-MM-DD",
      "requires_invitation": false,
      "new_customer_required": true,
      "spend_requirement_usd": "optional decimal",
      "qualification_months": "optional number",
      "reward": {
        "amount": "positive decimal",
        "unit": "native reward unit",
        "conversion_usd_per_unit": "optional documented decimal"
      },
      "terms": ["documented material condition"],
      "source": {"document_id": "source ID", "title": "source title"}
    }
  ]
}
```

`invited_offer_ids` may be omitted only when invitation status is unknown. Use an empty list when the customer has said they have no invitation. `is_new_customer` may be `true`, `false`, omitted, or `null`; omitted/null means unknown.

### Output and validation

The output has `eligible`, `conditional`, `excluded`, `unverified`, and `unrankable` lists plus `recommendation`. The recommendation is the first entry of `eligible`, or the first entry of `conditional` when no eligible entry exists. Check:

- `ok` is true;
- `validation.recommendation_is_current` is true before making a positive recommendation;
- `validation.selection_is_maximum_in_selected_pool` is true;
- every disclosed unresolved condition appears in the response;
- every USD conversion used in prose is documented in the supplied evidence.

Malformed input produces `{"ok": false, "error": "..."}`. Correct the extraction rather than guessing missing facts.

Runnable interface check:

```sh
printf '%s\n' '{"as_of":"2025-01-01","desired_audience":"personal","invited_offer_ids":[],"offers":[]}' | python3 scripts/rank_signup_offers.py
```
