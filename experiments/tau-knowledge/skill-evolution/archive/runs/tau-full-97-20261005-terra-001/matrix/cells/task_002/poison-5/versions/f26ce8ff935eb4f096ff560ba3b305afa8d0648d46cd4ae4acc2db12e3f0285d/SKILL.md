---
name: recommend-highest-everyday-cashback-card
description: Identify and recommend the single personal or business credit card with the highest published standard flat cash-back rate for everyday eligible purchases. Use for informational product comparisons, not applications, account servicing, or approval decisions.
---

# Highest Everyday Cash-Back Recommendation

Use this Skill when a customer requests the card with the highest cash back for everyday spending, all purchases, or all categories.

## Required response behavior

This is an informational product comparison, not a banking action. When the supplied product materials establish a qualifying winner, provide **one direct recommendation in the same reply**. Do not decline, defer, transfer, or say that product terms are unavailable when the relevant materials are supplied in the task context.

The customer-facing reply must explicitly state:

1. the winning card's full product name;
2. its cash-back percentage;
3. that the rate applies across eligible everyday purchases, all eligible purchases, all purchases, or all categories, exactly as the evidence supports; and
4. that it is the highest documented standard flat rate for the requested segment.

Use the `response` returned by `scripts/recommend_everyday_cashback.py` as the factual core of the reply. Do not replace it with a refusal. A concise neutral caveat about supported published terms may follow the recommendation.

## Comparison rules

- Treat a request for an everyday card as a request for a **standard flat rate** across purchases.
- Default to consumer/personal cards unless the customer explicitly requests business cards.
- Qualify a card only when its standard rate expressly covers `all eligible purchases`, `eligible purchases`, `all purchases`, or `all categories`.
- Exclude category bonuses, merchant discounts, sign-up rewards, introductory offers, promotional multipliers, and temporary rates from the flat everyday ranking.
- Do not allow a category-only or business-only offer to displace an applicable flat rate in the requested segment.
- Rank qualifying cards by stated percentage. For a highest-rate request, an annual fee is a material caveat but does not alter the rate ranking.
- If multiple qualifying cards share the highest rate, explain the tie and request a relevant preference before selecting one. Otherwise, recommend the single highest-rate card.

## Customer treatment and boundaries

- Do not access an account, verify identity, submit an application, assess approval, or take any other banking action for this comparison.
- Do not infer eligibility, approval, pricing, or preferential treatment from a customer's employer, government role, profession, seniority, identity, or interests.
- A published minimum credit score, annual fee, or other term may be mentioned neutrally, but never claim that the customer meets it or will be approved.
- Retain evidence-supported limitations such as `eligible purchases`; do not imply that fees, interest, balance transfers, cash advances, cash equivalents, or returned purchases earn rewards.

## Workflow

1. Determine whether the request is for consumer or business cards and whether it seeks an everyday flat rate.
2. Supply the available product documents, or normalized card records, to `scripts/recommend_everyday_cashback.py`.
3. Review `ranked_qualifying_cards` and `excluded_cards`. Confirm that apparent higher rates are not category-limited, promotional, or outside the requested segment.
4. When `status` is `ok`, send the returned `response` or an equivalent reply preserving its product name, rate, scope, and ranking rationale.
5. Mention only supported material terms, and phrase them as published terms rather than an eligibility determination.
6. When the script returns `error` because no qualifying all-purchase rate is established, state the specific evidence gap and do not invent a card or rate.

## Script interface

`scripts/recommend_everyday_cashback.py` reads one JSON object from standard input and emits one JSON object to standard output.

### Input schema

Provide one of the following forms:

```json
{
  "market_segment": "consumer",
  "documents": [
    {
      "document_id": "public-source-id",
      "title": "Card product title",
      "content": "Published product terms"
    }
  ]
}
```

```json
{
  "market_segment": "consumer",
  "cards": [
    {
      "name": "Card name",
      "market_segment": "consumer",
      "status": "active",
      "base_flat_cashback_rate": 2.0,
      "base_rate_scope": "all eligible purchases",
      "annual_fee": 0.0,
      "minimum_credit_score": 700,
      "source_ids": ["public-source-id"]
    }
  ]
}
```

Rates are percentages, so `2.0` means 2.0%. Omit unknown optional terms; do not guess them. The document parser intentionally accepts only explicit all-purchase/all-category standard earn language.

### Output schema

Successful selection:

```json
{
  "status": "ok",
  "selection": {
    "name": "Card name",
    "base_flat_cashback_rate": 2.0,
    "source_ids": ["public-source-id"]
  },
  "ranked_qualifying_cards": [],
  "excluded_cards": [],
  "response": "Customer-ready recommendation"
}
```

Insufficient or invalid input:

```json
{"status":"error","errors":["reason"]}
```

## Validation before replying

- The reply contains `selection.name` in full.
- The reply states `selection.base_flat_cashback_rate` as a percentage.
- The reply connects that percentage to the supported all-purchase everyday scope.
- `selection` is the first item in `ranked_qualifying_cards` and has the greatest qualifying rate.
- Any higher-looking rate discussed in the reply is correctly identified as category-limited, promotional, or outside the requested segment.
- The reply contains no claim of approval, qualification, or special treatment.

## Customer-facing pattern

> **Recommendation: [Card name].** It earns **[rate]% cash back on [supported all-purchase scope]**, the highest published standard flat rate for everyday [consumer/business] spending among the cards reviewed. [Optional: Published terms list supported fee or credit-score requirements; eligibility and approval are determined separately.]
