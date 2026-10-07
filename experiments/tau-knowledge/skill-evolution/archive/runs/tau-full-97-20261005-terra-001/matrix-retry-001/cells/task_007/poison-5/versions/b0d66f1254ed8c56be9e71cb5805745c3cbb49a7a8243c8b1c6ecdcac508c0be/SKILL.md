---
name: credit-card-promotion-comparison
description: Compare date-current credit-card promotions when a customer asks about sign-up bonuses, statement credits, cash back, points, introductory APR, or annual-fee waivers. Use for informational offer discovery and ranking, not to apply for, open, modify, or service an account.
---

# Credit Card Promotion Comparison

Use this skill to give a date-accurate, qualification-aware comparison of documented card promotions. It is especially appropriate when the customer prioritizes the best sign-up bonus in points or cash back.

## Scope and safety

This is an informational workflow only. Do not collect identity information, retrieve a customer profile, determine individual approval odds, or perform an account action merely to answer an offer question. Do not state that a particular customer qualifies unless every stated condition has been independently established.

If the request changes into a banking action, preserve this prerequisite verbatim in the resulting banking procedure and use the execution agent's normal banking tools:

> Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Required inputs

Use the current task's supplied promotion records and any supplied read-only time observation. Promotion records are evidence for the answer: do not discard dated offer-specific records merely because no customer account information is available.

For every relevant record, capture at runtime:

- product name and whether it is consumer or business;
- promotion type: sign-up bonus, introductory APR, fee waiver, or other;
- promotion start/end dates and the event governed by the dates;
- reward amount, unit, and payout form;
- invitation, new-customer, account-good-standing, spend, timing, and transaction-counting conditions;
- documented point redemption value, if any; and
- fulfillment timing, standard fee, or standard APR where material.

## Method

1. **Set the as-of date.** Use the local calendar date in a supplied successful current-time observation. Treat an offer window's start and end dates as inclusive. If no reliable date is supplied, explain that availability cannot be confirmed; do not guess.
2. **Classify each dated offer.** Mark an offer active only if the as-of date falls within its explicit window. Mark it upcoming or expired otherwise. If dates are absent, malformed, contradictory, or apply to a different benefit, mark its current status unknown rather than treating it as active.
3. **Prefer offer-specific evidence.** Use a promotion record as the source of its dates, terms, and fulfillment. Product application terms may corroborate a bonus but must not extend or replace an explicit promotion window. Disclose material conflicts rather than resolving them by assumption.
4. **Separate bonus types.** Put active sign-up bonuses first. Keep introductory APRs and fee waivers in a separate “Other current promotions” section; they can matter to a customer but are not sign-up bonuses.
5. **Rank bonus value transparently.** Rank active bonuses by documented redeemable USD value. Statement credits and cash back are direct monetary amounts. Convert points only if the supplied terms document a redemption value. If a point value is unavailable, show the point quantity but do not rank it against dollar offers. Do not confuse an ongoing rewards-earn rate with a sign-up bonus.
6. **Account for attainability.** A face-value leader is not necessarily the practical recommendation. Explicitly distinguish invitation-only offers from offers open to qualifying new customers, and compare documented spend thresholds and qualification periods. Do not imply an invitation will be issued or an application approved.
7. **Write the customer-facing answer.** Lead with a direct conclusion such as “The largest active sign-up bonus by documented value is …,” then state every material requirement in the same bullet. Include active alternatives with their requirements and the accessibility tradeoff. Use only the supplied record facts.

## Minimum response coverage for a bonus-priority request

Before sending an answer, make sure it contains all of the following for each active sign-up offer used in the comparison:

- card name;
- bonus amount and whether it is cash back, statement credit, or points;
- window or an unambiguous statement that it is active as of the observed date;
- spend requirement and qualifying time period, when documented;
- invitation-only and new-customer restrictions, when documented; and
- good-standing, eligible/net-purchase, return/credit, or other material transaction conditions.

For the top offer, use an explicit ranking term such as **largest**, **highest**, **best by documented bonus value**, or **top**. If that offer requires an invitation or unusually high spend, immediately explain that it may not be the best accessible choice. Do not say that current promotion records are unavailable when supplied dated records establish active offers.

A concise answer format is:

```text
As of [date], the largest active sign-up bonus by documented value is [card]:
[reward], if [all material requirements]. [Invitation/new-customer caveat].

Other active sign-up options:
- [card]: [reward] for [spend] in [period], subject to [conditions].

Bottom line: [face-value leader] is best only for a customer who can meet its
requirements; [accessible alternative] is the more practical option when its
lower threshold or lack of an invitation better fits the customer.

Other current promotions (not sign-up bonuses): [only relevant active APR or
fee offers].
```

When the supplied terms define a point redemption rate, it is useful to state both the point amount and its documented redemption equivalent, while retaining the program's point terminology. Do not invent a point value if one is not documented.

## Deterministic ranking helper

`scripts/analyze_offers.py` filters structured offer records against an as-of date and ranks active sign-up bonuses. It is optional but recommended whenever several promotion records must be compared. It makes no network calls and does not access customer information.

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
        "amount": "nonnegative numeric amount",
        "currency": "USD for direct monetary rewards",
        "redemption_value_per_point": "optional documented USD amount per point"
      },
      "qualification": {
        "invitation_required": false,
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

`as_of`, `offers`, `card`, and `offer_type` are required for usable date categorization. Direct monetary rewards need `currency: "USD"` to be ranked as dollar values. Supply `redemption_value_per_point` for points only if it appears in the current supplied terms.

### Output JSON schema

The script emits:

- `ok` and normalized `as_of`;
- `ranked_active_signup_bonuses`, with `usd_equivalent` and `rank_basis` where supportable;
- `active_non_signup_offers`, deliberately separate from bonus ranking;
- `inactive_or_unknown_offers`, labeled `upcoming`, `expired`, `date_unknown`, or `invalid`; and
- `warnings` and `errors` that must be addressed in the written response.

### Runnable use

Build the JSON from the promotion records supplied for the current task, then run:

```sh
python3 scripts/analyze_offers.py < offers.json
```

Use the result to check chronology and ordering. Write the final response from the documented conditions, not from raw JSON alone.

## Validation before responding

- Confirm the as-of date and that every offer called active has an explicit window containing it.
- Confirm the stated leader is an active sign-up bonus rather than an APR promotion, fee waiver, or recurring earn rate.
- Confirm every dollar comparison uses a documented points conversion if points are involved.
- For the leading bonus, include its value, spend threshold, qualification period, and invitation/new-customer limitation where documented.
- Include every relevant accessible active alternative, with its reward, spend threshold, and earning period.
- Explain the practical tradeoff between maximum headline value and accessibility; do not imply approval, invitation, or eligibility.
- Keep expired, upcoming, and date-unknown offers out of claims about what is currently available.
