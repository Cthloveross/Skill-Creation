---
name: personal-credit-card-signup-bonus-comparison
description: Provide a grounded comparison of documented personal credit-card sign-up bonuses, annual fees, qualification requirements, and bonus value. Use when a customer asks which personal card has the best promotional offer and the available product evidence may be incomplete.
---

# Personal credit-card sign-up bonus comparison

## Scope and grounding

Use only card offers and terms documented in the supplied task evidence. Do not imply that undocumented cards, bonuses, fees, eligibility rules, or application outcomes exist. If the customer asks for *all* available offers but the evidence documents only a subset, clearly identify the documented subset and say that a full market comparison is not possible from the available information.

Honor stated scope filters. In particular, exclude business cards when the customer asks for personal cards only.

## Method

1. Extract, for each documented in-scope card:
   - card name;
   - bonus quantity and reward currency;
   - redemption value, if documented;
   - minimum eligible spend and qualification period;
   - customer/account eligibility conditions;
   - annual fee; and
   - offer dates and whether the offer is active, if a current date is supplied.
2. Convert rewards to a dollar-equivalent only where a documented conversion rate exists. Preserve the original reward quantity as well. For example, `2,000` points at `$0.01` per point have a stated redemption value of `$20.00`; do not mistake a label such as "$2,000 points" for a $2,000 cash bonus.
3. Compare offers only when sufficient in-scope offers are documented. If there is only one documented offer, describe it rather than claiming it is the overall best available card.
4. Distinguish the bonus from ongoing reward earnings and from the annual fee. Do not subtract an annual fee from a bonus unless explicitly presenting an optional first-year net-value calculation, and label that calculation and its assumptions.
5. If the customer has not said whether they can meet the spend requirement, state that the offer is practical only if they can do so through normal eligible spending. Never encourage cash equivalents, fees, balance transfers, artificial spend, or any transaction that the terms exclude.
6. End with a concise next step: ask whether the customer expects to meet the stated threshold or whether they want help comparing additional documented personal offers. Do not apply for a card or make account changes.

## Current-task application

The supplied evidence documents one in-scope personal product, EcoCard. A complete response should say:

- EcoCard offers 2,000 sustainability points after $5,000 in eligible purchases during the first month for a new customer, provided the account is open and in good standing when awarded.
- The documented redemption rate is $0.01 per sustainability point, so 2,000 points are worth $20.00 when redeemed as the documented statement-credit or checking-credit options.
- EcoCard's annual fee is $50.00.
- The promotion runs from 2025-08-01 through 2025-12-15. With the supplied current date of 2025-11-14, it is within the documented offer window.
- Returns, chargebacks, disputes, balance transfers, cash equivalents, and fees do not count (or can reduce qualifying spend) as specified by the terms.
- No other personal-card promotional offers are documented in the available evidence, so no supported ranking of "best" across cards can be made.

Use neutral, customer-facing language. State uncertainty about the customer's ability to spend $5,000 because they have not confirmed it.

## Optional deterministic helper

`scripts/compare_offers.py` accepts a JSON object on stdin and emits a normalized comparison. It is useful when multiple documented offers are supplied at runtime; it does not discover offers.

Input schema:

```json
{
  "offers": [{"name": "string", "category": "personal|business", "bonus_points": 2000, "point_value_dollars": 0.01, "annual_fee_dollars": 50, "spend_requirement_dollars": 5000, "period": "first month", "offer_start": "YYYY-MM-DD", "offer_end": "YYYY-MM-DD", "conditions": ["..."]}],
  "as_of_date": "YYYY-MM-DD",
  "personal_only": true
}
```

Fields other than `name` and `category` may be omitted or null when not documented. The output retains unknown values as `null`, filters business offers when requested, and reports active status only when both a date and an offer window are known.

Example runnable call (from the package root):

```sh
printf '%s' '{"offers":[{"name":"Example","category":"personal","bonus_points":2000,"point_value_dollars":0.01,"annual_fee_dollars":50,"spend_requirement_dollars":5000,"period":"first month","offer_start":"2025-08-01","offer_end":"2025-12-15"}],"as_of_date":"2025-11-14","personal_only":true}' | python3 scripts/compare_offers.py
```

Validate the helper result before using it: confirm that excluded categories are absent, `bonus_value_dollars` equals `bonus_points * point_value_dollars` when both are known, and do not fill missing source facts from the computed output.
