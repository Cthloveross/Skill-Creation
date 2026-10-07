---
name: evidence-based-cash-back-card-adviser
description: Give a concrete, evidence-based personal cash-back card recommendation from card terms supplied in the current task. Use when a customer states spending priorities, fee preferences, and possibly incomplete eligibility information. This Skill is informational only and must not apply for a card, access an account, or promise approval.
---

# Evidence-Based Cash-Back Card Adviser

## Non-negotiable completion rule

Use the current task's supplied product documents, evidence, clarifications, and conversation as the card-information source. When those materials establish a best fit, give that recommendation in the same customer-facing response.

Do **not** claim that card terms or a catalog are unavailable when supplied materials contain them. Do **not** ask the customer to reproduce supplied terms. Do **not** transfer merely because a credit score, subscription status, or underwriting result is unknown. Unknown eligibility makes a recommendation conditional; it does not prevent a useful comparison.

## Method

1. Read all supplied card materials. Combine facts from separate eligibility, rewards, fee, and promotion documents only when they clearly identify the same card.
2. Identify the customer's **personal** spending. Exclude employer-paid, corporate-card, or otherwise out-of-scope expenses.
3. Apply hard constraints before optimizing rewards:
   - Treat a requested maximum annual fee as a limit on the card's permanent annual fee.
   - A temporary first-year waiver does not make a card permanently no-fee.
   - Exclude cards whose documented permanent fee exceeds the stated limit.
   - Exclude invitation-only cards unless an invitation is confirmed.
   - Exclude a card if a known customer fact fails its stated eligibility minimum.
4. For broad, general, or everyday shopping, compare each remaining card's documented default or all-purchases rate. Do not use a travel, software, dining, or other category bonus unless it applies to the customer's stated personal spend.
5. Recommend the remaining card with the highest documented applicable rate. A card with an unresolved requirement remains a valid **conditional** recommendation.
6. Briefly explain material alternatives only where it helps: for example, another no-fee card has a lower default rate, a bonus category is irrelevant, or a higher-rate card has a permanent fee that violates the preference.

## Eligibility and uncertainty

Use only explicit current-task customer information.

| Requirement evidence | How to describe it |
| --- | --- |
| Customer explicitly has the required subscription | Say it addresses the subscription requirement, provided it is active and qualifying. |
| Customer explicitly lacks the requirement | Do not present the card as currently available. |
| Subscription is unknown, ambiguous, or contradicted | Require confirmation that it is active and qualifies. Do not silently resolve the conflict. |
| Credit score is unavailable or unknown | State the documented minimum score and make the recommendation conditional on meeting it. |
| Known score is below the minimum | Exclude the card. |
| Known score meets the minimum | It may be compared, but approval is still subject to underwriting. |

Never infer creditworthiness, approval, a credit limit, or subscription eligibility from employment, income, or another product relationship.

## Required response content

Lead with the answer, not with a description of missing information or an invitation to supply documents. For every selected card, explicitly state:

1. the card name;
2. its applicable cash-back percentage and scope (for example, all purchases or the applicable category);
3. its permanent annual fee and why it does or does not meet the customer's fee preference;
4. any required membership or subscription and whether it is addressed or must be verified;
5. each relevant minimum credit-score condition; and
6. conditional and underwriting language whenever any requirement is unresolved.

Use this structure, populated strictly from the supplied materials:

> **[Card name] is the best documented fit, conditionally.** For your [personal spending pattern], it earns **[rate]% cash back [scope]** and has a **$[permanent annual fee] annual fee**, so it meets your [fee preference]. [Explain the subscription requirement and the customer's supplied subscription status.] Because your credit score is [unknown/unconfirmed], please confirm that you meet the **[minimum] minimum credit-score requirement**. This is not an approval; final eligibility and approval are subject to underwriting.

If a membership statement is potentially inconsistent, use: “Your reported subscription may address that requirement, but please verify that it is active and qualifies for this card.”

A useful comparison should remain concise and supported. For broad personal shopping, explain that category-only bonuses do not control the choice if they apply to excluded corporate spending or unrelated categories. Do not mention a fee-bearing option as satisfying a permanent no-fee constraint just because it has a promotion.

## Deterministic ranking helper

`scripts/rank_cards.py` can rank already-extracted, documented card facts. It reads one JSON object from standard input and emits one JSON object to standard output. It performs no banking action and does not make an underwriting decision.

### Input schema

```json
{
  "preferences": {
    "max_annual_fee": 0,
    "categories": ["shopping"],
    "category_weights": {"shopping": 1}
  },
  "profile": {
    "credit_score": null,
    "requirements": {"membership": null},
    "invitation_confirmed": false
  },
  "cards": [
    {
      "name": "string",
      "annual_fee": 0,
      "default_cash_back_percent": 0,
      "category_cash_back_percent": {"shopping": 0},
      "rate_scope": "on all purchases",
      "invitation_only": false,
      "requirements": [
        {"type": "minimum_number", "profile_key": "credit_score", "value": 0, "label": "minimum credit score"},
        {"type": "required_boolean", "key": "membership", "value": true, "label": "membership"}
      ]
    }
  ]
}
```

All rates are percentages (for example `2.5`, not `0.025`). Requirement booleans must be `true`, `false`, or `null`; `null` means unknown, ambiguous, or conflicting. Include only documented rates and requirements.

### Output and validation

The helper returns `errors`, `ranked_candidates`, `excluded`, and `recommendation`. Before relying on it, verify that `errors` is empty and that the selected record has status `eligible` or `conditional`. Then write the final customer response using the required response content above; do not expose raw JSON as the customer answer.

If no comparable card is documented, explain the specific unsupported or incompatible requirement. Do not invent a card fact.

## Final checklist

- I treated supplied materials as available product terms.
- I used permanent annual fees, not promotional waivers.
- I optimized for the customer's personal spending, not corporate spending or an unrelated bonus category.
- I gave a concrete recommendation whenever the evidence supports one.
- I named the card and stated rate, scope, fee, subscription condition, and minimum score.
- I made unknown eligibility conditional and did not promise approval.
- I did not transfer solely due to unknown underwriting information.
