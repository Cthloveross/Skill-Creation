---
name: everyday-credit-card-recommendation
description: Provide a single, evidence-grounded recommendation for an everyday credit card when the customer prioritizes the highest broadly applicable cash-back rate, including cases where an otherwise higher-rate product is unavailable because of an eligibility requirement.
---

# Everyday credit-card recommendation

Use this Skill for an informational product recommendation, not for an application, account change, or reward redemption. It produces one decisive recommendation only when the documented product facts establish a clear winner for the customer's stated use.

## Principles

1. Use only documented product terms. Distinguish a rate on **all eligible purchases** from a category-limited, travel-only, green-only, or otherwise conditional rate.
2. Honor an explicit customer instruction to treat a product as unavailable. Do not infer that a customer qualifies merely because no disqualifying fact was supplied.
3. Do not use a customer's job, employer, public role, or other personal attribute as a proxy for creditworthiness or product eligibility. It may be acknowledged politely but does not alter a cash-back comparison unless the product terms expressly make it relevant.
4. Do not claim approval, invent fees, or state undocumented eligibility criteria. If a recommended card's approval requirements are not documented, say only that normal approval/eligibility requirements may still apply if needed.
5. Do not call account, identity, or verification tools for a general product comparison. No customer record is needed to explain published terms.

## Selection method

Build a small candidate list from the supplied product evidence. For each candidate include:

- `name`
- `available`: whether it remains an option under the customer's explicit instruction
- `cash_back_percent`: cash value earned per $100 on ordinary eligible everyday purchases
- `universal_everyday`: `true` only if that rate applies to all eligible purchases rather than a category or qualifying merchant
- `evidence`: a short, customer-safe citation of the documented rate and any relevant condition

For a points product, convert points only when the evidence supplies a redemption value. For example, 5 points per dollar at $0.01 per point has a 5% cash value, but it is not a universal everyday rate if it applies only to qualifying green purchases.

Run `scripts/select_recommendation.py` with the candidate list. It filters unavailable and non-universal products, ranks the remaining ordinary-purchase cash-back rates, and reports whether the result is decisive. Do not use it to invent candidates or eligibility facts.

### Runtime script interface

`python scripts/select_recommendation.py` reads one JSON object from stdin:

```json
{
  "candidates": [
    {
      "name": "string",
      "available": true,
      "cash_back_percent": "number or decimal string",
      "universal_everyday": true,
      "evidence": "string"
    }
  ]
}
```

It emits JSON with `status` (`ok`, `tie`, or `no_qualified_candidate`), the eligible candidates, and a `recommendation` object for an `ok` result. A candidate with missing required fields or an invalid rate causes an `invalid_input` result; correct the evidence extraction rather than guessing.

## Response construction

When the script returns `ok`, respond in this order:

1. State the single recommended card and its documented ordinary eligible-purchase rate.
2. Explain briefly why the higher-rate card is not being selected if the customer explicitly treated it as unavailable.
3. Give one concise reason the selected card beats conditional alternatives: its rate applies across eligible everyday purchases, rather than only in a particular category or at qualifying merchants.
4. Add a narrowly scoped caveat only if supported: rewards generally exclude such things as cash advances, balance transfers, fees, interest, and cash-equivalent transactions; returns/credits can reverse associated rewards. Do not add irrelevant product details.

Use clear dollar language where helpful (for example, “5% means $5 back per $100 in eligible purchases”). Do not confuse backend reward-point storage with the customer-facing cash-back value when evidence says points redeem at $0.01 each.

If the result is `tie`, explain that the supplied terms do not establish a unique best option and ask one preference question that would break the tie. If it is `no_qualified_candidate`, say that the available evidence does not identify a universal everyday cash-back alternative and ask permission to compare category-specific options. Do not fabricate a decisive answer.

## Validation before sending

Check that the final response:

- names exactly one card when a decisive result exists;
- treats each customer-excluded product as unavailable;
- compares cash-equivalent rates, not raw point counts;
- does not imply that a conditional earn rate applies to all purchases;
- does not make approval, account, or customer-data claims; and
- contains no application action, account modification, or unsupported term.

For the supplied conversation, the documented comparison should exclude the product the customer explicitly asked to treat as unavailable, and it should select the highest documented rate that applies to eligible everyday purchases generally. The response should remain an informational recommendation; it requires no banking-tool call.