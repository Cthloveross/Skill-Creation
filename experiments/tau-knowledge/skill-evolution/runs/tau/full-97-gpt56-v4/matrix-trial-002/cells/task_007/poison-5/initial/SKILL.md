---
name: promotional-credit-card-offer-advisor
description: Compare currently available credit-card sign-up promotions when a customer prioritizes cash back, statement credits, or redeemable points. Use for informational card recommendations; do not use it to open, alter, or service an account.
---

# Promotional Credit-Card Offer Advisor

Use this Skill to give a grounded, customer-friendly comparison of promotional card offers. The recommendation must distinguish the largest advertised value from the offer that the customer is actually eligible and able to complete.

## Scope and safety

This is an informational recommendation workflow only. Do not apply for a card, enroll a customer, redeem rewards, access an account, or make any other banking action.

If a later request changes from advice to a banking action, first follow this mandatory control exactly:

> Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Method

1. Identify the comparison date from a supplied current-time observation. Do not treat expired promotions as available.
2. Extract each promotion's card, offer window, reward amount and reward type, spending threshold, qualification period, and restrictions (for example, new-customer, invitation-only, good-standing, or account-opening requirements).
3. Normalize rewards to a disclosed cash-equivalent only when an explicit redemption rate is available. Keep the original reward units visible; do not call points “cash” without stating the conversion.
4. Determine whether each offer is current:
   - An offer is current only when the comparison date is on or after its start date and on or before its end date.
   - If no date range is supplied, say that availability needs confirmation rather than inferring it.
5. Compare both:
   - **Maximum advertised value:** highest current normalized value.
   - **Practical fit:** threshold, qualification period, customer-status restrictions, invitation requirements, and meaningful ongoing fees.
6. State qualification conditions precisely. Spending thresholds refer only to eligible/qualifying purchases; returns, credits, and other stated exclusions can reduce progress.
7. Make a conditional recommendation rather than assuming the customer has an invitation, qualifies as a new customer, has a particular credit score, or can spend a particular amount.

## Response pattern

Give a short answer that includes:

- the leading current offer and its reward amount/value;
- what the customer must do and by when;
- material restrictions and any annual-fee treatment;
- the best alternative when the leading offer is inaccessible or impractical;
- a clear note about expired offers that might otherwise appear attractive;
- one targeted follow-up question, such as whether the customer is a new customer, has an invitation, or can meet the required spend.

Do not overstate certainty. A high-value invitation-only offer should be framed as the best offer **if invited and able to meet its terms**, not as universally available. When a points offer has a stated cash redemption rate, show both the point amount and cash-equivalent calculation.

## Deterministic comparison helper

Use `scripts/compare_offers.py` when offer facts have been structured. It reads JSON on stdin and emits JSON on stdout.

Input schema:

```json
{
  "comparison_date": "YYYY-MM-DD",
  "offers": [
    {
      "card": "string",
      "start_date": "YYYY-MM-DD or null",
      "end_date": "YYYY-MM-DD or null",
      "reward_amount": 0,
      "reward_unit": "statement_credit|cash_back|points|other",
      "point_value_dollars": 0.01,
      "spend_requirement": 0,
      "qualification_months": 1,
      "restrictions": ["new_customer"],
      "annual_fee_dollars": 0,
      "fee_waived_by_offer": false
    }
  ]
}
```

`reward_amount` and numeric money fields must be nonnegative numbers. Supply `point_value_dollars` only when the source explicitly provides a conversion. Dates use ISO `YYYY-MM-DD`; a missing date is represented by `null`.

The output has `current_offers`, `unconfirmed_offers`, `expired_offers`, and `highest_current_cash_equivalent`. Use it as a calculation aid, then write the final answer in natural language using the source terms and restrictions.

Example runnable call (illustrative placeholders only):

```sh
python3 scripts/compare_offers.py <<'JSON'
{"comparison_date":"2025-01-15","offers":[{"card":"Example Card","start_date":"2025-01-01","end_date":"2025-01-31","reward_amount":100,"reward_unit":"statement_credit","point_value_dollars":null,"spend_requirement":1000,"qualification_months":1,"restrictions":["new_customer"],"annual_fee_dollars":0,"fee_waived_by_offer":false}]}
JSON
```

## Validation

Before relying on the comparison:

- ensure every recommended offer is in `current_offers`;
- ensure the displayed cash-equivalent is either a dollar reward or `reward_amount × point_value_dollars` from an explicit source conversion;
- inspect `restrictions`, spend requirement, and qualification months for the top offer;
- do not present an offer in `unconfirmed_offers` as active; and
- if no offers are current, say so and avoid naming a “best current” offer.
