---
name: credit-card-promotion-comparison
description: Compare currently available credit-card promotions when a customer asks about sign-up bonuses, statement credits, cash back, points, introductory APR, or annual-fee waivers. Use it for informational offer discovery and ranking; do not use it to apply for, open, modify, or service an account.
---

# Credit Card Promotion Comparison

Use this skill to give a date-accurate, qualification-aware comparison of promotions. It is especially suited to requests for the best sign-up bonus in points or cash back.

## Scope and safety

This workflow is informational only. Do not collect identity data, retrieve a customer profile, determine individualized approval odds, or perform an account action merely to answer an offer question. Do not represent that a customer is eligible unless all stated conditions have actually been established.

If the request changes into a banking action, the resulting banking procedure must preserve this prerequisite verbatim and the execution agent must use its normal banking tools:

> Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Method

1. **Establish the as-of date.** Use a supplied read-only current-time observation when available. Use the local calendar date represented by that observation. If no reliable date is available, say that current availability cannot be confirmed rather than guessing.
2. **Find offer-specific records.** Gather promotions for relevant cards and extract, for each offer:
   - card/product name;
   - promotion type (sign-up bonus, introductory APR, fee waiver, etc.);
   - offer start and end dates, including whether the dates govern application, account opening, invitation acceptance, or another event;
   - amount, unit, and payout form;
   - all qualification conditions: invitation-only status, new-customer requirement, spending threshold, qualifying period, good-standing requirement, and transaction exclusions;
   - fulfillment timing and any stated standard rate or fee after the promotion.
3. **Check availability.** Treat date endpoints as inclusive. Separate active, upcoming, expired, and date-unknown offers. Never use an expired promotion as an available recommendation.
4. **Resolve document overlap carefully.** Prefer an offer-specific promotion record for dates, conditions, and fulfillment. A product application or general terms record can corroborate a benefit but should not extend or replace an explicit offer window. If records materially conflict, disclose the conflict and avoid a definitive availability claim.
5. **Rank sign-up bonuses transparently.** For a request prioritizing bonus value, rank active sign-up bonuses by documented redeemable monetary value. A statement credit and cash back are direct monetary values. Convert points only when the supplied product terms explicitly provide a redemption value; otherwise show the point quantity separately and do not numerically compare it with dollars. Break ties by the lower documented spend requirement only if the qualification periods are comparable; otherwise leave the tie unresolved and explain why.
6. **Keep non-bonus promotions separate.** Report active introductory APR and annual-fee offers in a distinct section. They may be useful, but they are not sign-up bonuses and should not displace a larger bonus in the ranking.
7. **Give a concise customer-facing answer.** Lead with the best active sign-up bonus, then summarize other active bonuses and other relevant promotions. State material caveats directly, especially invitation-only restrictions, new-customer restrictions, spend windows, net/eligible-purchase rules, and posting delays. End with an offer to compare the leading options against the customer's expected spending; do not infer approval or eligibility.

## Deterministic ranking helper

`scripts/analyze_offers.py` filters structured offer records against an as-of date and ranks active sign-up bonuses without comparing unvalued points to currency.

### Input JSON schema

```json
{
  "as_of": "YYYY-MM-DD or timestamp beginning with YYYY-MM-DD",
  "offers": [
    {
      "card": "string",
      "offer_type": "signup_bonus | intro_apr | annual_fee_waiver | other",
      "window_start": "YYYY-MM-DD",
      "window_end": "YYYY-MM-DD",
      "qualifying_event": "account opening, application, invitation acceptance, or other event",
      "reward": {
        "kind": "statement_credit | cash_back | cash | points | other",
        "amount": "numeric amount",
        "currency": "USD for direct monetary rewards",
        "redemption_value_per_point": "optional USD amount per point"
      },
      "qualification": {
        "invitation_required": true,
        "new_customer_required": false,
        "spend_requirement": "optional amount or text",
        "spend_window": "optional text",
        "good_standing_required": false,
        "exclusions": ["optional strings"]
      },
      "fulfillment": "optional text",
      "details": "optional text"
    }
  ]
}
```

Only `as_of`, `offers`, `card`, and `offer_type` are required for date categorization. `reward.amount` must be a nonnegative numeric value when a reward is supplied. Direct monetary rewards need `currency: "USD"` to be ranked as dollar values. For points, provide `redemption_value_per_point` only when it is documented by the supplied terms.

### Output JSON schema

The helper emits an object with:

- `ok`: whether the top-level input was usable;
- `as_of`: normalized calendar date;
- `ranked_active_signup_bonuses`: active bonus records ordered by documented USD equivalent, followed by active bonuses whose value cannot be compared to USD;
- `active_non_signup_offers`: active APR, fee, and other promotions, kept separate from the bonus ranking;
- `inactive_or_unknown_offers`: records labeled `upcoming`, `expired`, `date_unknown`, or `invalid`;
- `warnings` and `errors`: missing, malformed, or non-comparable data that must be reflected in the response.

Each ranked item includes `rank_basis`, `usd_equivalent` when documented or calculable, and the source qualifications passed through from input.

### Runnable use

Create a task-time JSON file matching the input schema from the current promotion records, then run:

```sh
python3 scripts/analyze_offers.py < offers.json
```

Use the resulting ordering as a check, then write the customer response from the documented conditions rather than exposing raw JSON.

## Validation before responding

- Confirm the as-of date is present and that every claimed active offer has both a start and end date covering that date.
- Confirm that the winning bonus is actually a sign-up bonus, not an APR promotion or a recurring card reward rate.
- Confirm each dollar comparison uses a documented point conversion where points are involved.
- Include conditions that could change usefulness or availability: invitation, new-customer status, spend threshold, qualification window, eligible/net-purchase rules, good standing, and benefit posting timing.
- Do not state an offer is available if its window is missing, contradictory, or expired. Explain the limitation instead.
