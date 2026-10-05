---
name: credit-card-signup-bonus-advisor
description: Compare documented credit-card sign-up promotions and recommend the highest-value offer that is current as of a supplied date, while clearly stating spend requirements, deadlines, eligibility constraints, and non-cash points conversions. Use for informational product comparisons, not for applying for or modifying an account.
---

# Credit Card Sign-Up Bonus Advisor

Use this skill when a customer asks which card has the best sign-up bonus, cash-back bonus, or points bonus. The result must distinguish the largest *documented current* incentive from alternatives that are easier to qualify for or require less spending.

## Scope and safety

This is an informational comparison only. Do not submit an application, enroll a customer, redeem rewards, disclose account information, or make another banking change. Do not infer that the customer is eligible for an invitation-only offer, underwriting approval, or a bonus unless the documented terms establish it.

If a later request changes from comparison to a banking action, first follow all applicable banking controls: verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

## Required inputs

Collect or use the following from the current task materials:

- `as_of_date`: current date in `YYYY-MM-DD` form. Obtain current time if it was not supplied; do not call an expired offer current.
- Documented promotion facts for each candidate: card name, source document ID, offer window (if documented), reward amount/type, any point-to-cash conversion, fee waiver value, required spend, qualification period, and eligibility/status restrictions.
- The customer's stated priority or constraints, if any (for example, lowest required spend, cash rather than points, new-customer status, or invitation status).

Only rely on the supplied current materials. Missing dates, conversion rates, requirements, or eligibility facts must be identified as unknown rather than guessed.

## Method

1. Establish the as-of date and compare it inclusively with every documented offer window. Exclude offers whose end date has passed. If an offer has no documented availability window, label its current availability as unconfirmed rather than ranking it as a current offer.
2. Normalize each qualifying bonus:
   - A statement credit or cash bonus has its stated dollar value.
   - For points, use a documented redemption conversion only. Report both the point amount and calculated dollar value.
   - Keep a waived annual fee separate from the bonus cash/points value, then show an optional total disclosed first-year incentive when the waived-fee value is documented.
3. Rank current, availability-confirmed offers by documented total disclosed monetary value. Do not treat ongoing earn rates, APR, credit limits, or purchase protections as sign-up incentives unless the source says they are a sign-up offer.
4. Check feasibility before recommending: invitation-only status, new-customer requirement, membership/subscription requirement, minimum credit score, account-opening deadline, required spend, qualifying period, eligible-purchase rules, good-standing requirements, and return/credit effects.
5. Give a direct answer followed by a practical alternative if the top promotion has unusually high spend or restrictive eligibility. Do not call a lower-spend alternative “best” without explaining the different criterion.
6. Cite each factual claim to its source document ID or title. State the offer’s posting timeline if documented. Describe eligibility as a requirement, not as a prediction of approval or an invitation.

## Recommended response structure

- **Best documented current bonus:** Card, bonus amount and type, plus separately stated fee waiver if applicable; required spend and deadline; offer-window status as of the supplied date.
- **Important eligibility/terms:** invitation or customer-status restrictions, known credit or subscription requirements, qualifying-purchase exclusions, good-standing requirements, and benefit-posting timing.
- **Lower-barrier alternative:** current alternative with lower spend or fewer constraints, including a points conversion when documented.
- **Bottom line:** a concise tradeoff statement based on the customer’s stated priority.

Use careful phrasing such as “largest documented current incentive in the supplied materials,” because materials may not represent the whole market.

## Optional deterministic ranking helper

Use `scripts/rank_signup_offers.py` after extracting source facts into structured JSON. It filters offers by inclusive dates, derives a documented points value when possible, and ranks confirmed-current offers. It does not determine whether a customer is personally eligible.

### Input schema

Pass one JSON object on standard input:

```json
{
  "as_of_date": "YYYY-MM-DD",
  "include_availability_unknown": false,
  "offers": [
    {
      "card": "string",
      "source_id": "string",
      "window_start": "YYYY-MM-DD or null",
      "window_end": "YYYY-MM-DD or null",
      "cash_bonus": 0,
      "points_bonus": 0,
      "point_value_usd": 0,
      "fee_waiver_value": 0,
      "required_spend": 0,
      "qualification_months": 0,
      "eligibility_notes": ["string"]
    }
  ]
}
```

Monetary inputs must be nonnegative numbers in USD. `point_value_usd` is the documented USD redemption value per point; use `null` when it is not documented. Dates must be ISO calendar dates.

### Output schema

The script emits JSON with `ranked_current_offers`, `excluded_offers`, and `availability_unknown_offers`. Each ranked item contains the separately reported `cash_bonus`, `points_value_usd`, `fee_waiver_value`, and `total_disclosed_incentive_usd`, plus the supplied requirements and source ID. Review the source text before turning those fields into customer-facing language.

Example executor call pattern (with facts extracted from the current task, not hardcoded values):

```text
run_skill_script(relative_path="scripts/rank_signup_offers.py", input_json={"as_of_date":"...","offers":[...]})
```

## Validation checklist

Before responding, verify that:

- the recommendation is current on the as-of date and expired offers were excluded;
- all dollar values, point conversions, spend thresholds, and dates match cited materials;
- fee waiver and bonus are not silently conflated;
- invitation-only and other restrictions are explicit;
- no unknown fact was calculated or assumed; and
- the response recommends only and does not perform a banking action.
