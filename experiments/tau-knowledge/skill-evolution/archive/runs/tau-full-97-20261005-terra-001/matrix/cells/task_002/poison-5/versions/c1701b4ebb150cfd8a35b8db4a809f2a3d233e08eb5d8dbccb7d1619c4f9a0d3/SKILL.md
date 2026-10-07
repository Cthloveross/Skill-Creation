---
name: recommend-highest-everyday-cashback-card
description: Recommend the one consumer credit card with the highest published standard flat cash-back rate on eligible everyday purchases. Use for product-information comparisons, not applications, account actions, or eligibility decisions.
---

# Highest Everyday Cash-Back Card Recommendation

Use this Skill when a customer asks for the highest cash back for everyday spending, all purchases, or broadly applicable eligible purchases.

## Immediate answer rule

This is an informational product comparison. If the supplied product material establishes a qualifying winner, give the customer **one direct recommendation in the same reply**. Do not withhold a recommendation because the customer's eligibility, credit profile, approval status, or personal circumstances are unknown.

The reply must explicitly contain:

1. the selected card's full product name;
2. its cash-back percentage;
3. that the rate applies to eligible everyday spending, all eligible purchases, all purchases, or all categories, as supported; and
4. a brief reason it wins: it has the highest documented standard flat rate in the requested segment.

Use `scripts/recommend_everyday_cashback.py` whenever documents or normalized card records are available. Treat its `response` as the factual core of the customer reply. Do not replace it with a refusal or an assertion that terms are unavailable.

## Scope and comparison rules

- Default to consumer/personal cards unless the customer explicitly asks for business cards.
- A qualifying everyday rate must expressly apply across all eligible purchases, all purchases, or all categories.
- Keep a product's standard flat rate separate from bonus-category rates, merchant discounts, sign-up bonuses, promotional multipliers, introductory rates, and time-limited offers.
- Do not let a category-only rate, business-only product, promotion, or temporary offer displace a standard flat consumer everyday rate.
- Rank qualifying cards by cash-back percentage. For a request for the **highest cash back**, an annual fee is a caveat and does not change the rate ranking.
- If two qualifying products tie at the highest rate, say that they tie and ask only for a relevant preference needed to choose one. Otherwise, recommend a single winner.

## Customer treatment and boundaries

- A recommendation is not a banking action. Do not access an account, submit an application, make an approval determination, or change a card.
- Do not infer or promise eligibility, approval, pricing, or preferential treatment based on an employer, government role, identity, profession, or personal characteristic.
- You may neutrally state an annual fee or minimum credit-score requirement only when supported by supplied material. Describe these as published terms; never say the customer meets them.
- Preserve any published qualification such as “eligible purchases.” Do not imply that returns, fees, interest, cash advances, balance transfers, or cash-equivalent transactions earn rewards.

## Method

1. Identify the requested market segment and whether the request is for a flat everyday rate.
2. Read all supplied material for cards in that segment.
3. For each product, identify only its explicit standard flat rate and scope. Record category and promotional rates as non-qualifying comparison information.
4. Exclude products outside the requested segment and products without an explicit all-purchase/all-category standard rate.
5. Select the numerically highest remaining rate.
6. Give the direct recommendation, rate, supported scope, and concise comparison rationale. Add supported material terms only as neutral caveats.

If the supplied material genuinely does not establish any qualifying flat everyday rate, explain that precise evidence gap and do not invent a product or rate. This fallback is not appropriate when the supplied materials establish a winner.

## Script interface

`scripts/recommend_everyday_cashback.py` reads one JSON object from standard input and emits one JSON object to standard output.

### Input

Provide either normalized `cards` or public `documents`:

```json
{
  "market_segment": "consumer",
  "documents": [
    {
      "document_id": "optional-source-id",
      "title": "Product title",
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
      "name": "string",
      "market_segment": "consumer",
      "status": "active",
      "base_flat_cashback_rate": 2.0,
      "base_rate_scope": "all eligible purchases",
      "annual_fee": 0.0,
      "minimum_credit_score": 700,
      "source_ids": ["source-id"]
    }
  ]
}
```

Rates are percentages (`2.0` means 2.0%). Missing optional terms must be omitted, not guessed. Document parsing accepts only explicit flat all-purchase/all-category language; it does not convert category rates or promotions into everyday rates.

### Output

On success:

```json
{
  "status": "ok",
  "selection": {
    "name": "string",
    "base_flat_cashback_rate": 2.0,
    "source_ids": ["source-id"]
  },
  "ranked_qualifying_cards": [],
  "excluded_cards": [],
  "response": "Customer-ready recommendation"
}
```

On insufficient or invalid input it returns:

```json
{"status":"error","errors":["explanation"]}
```

### Runnable call example

Pass the following input to the packaged script runner with `relative_path` set to `scripts/recommend_everyday_cashback.py`:

```json
{
  "market_segment": "consumer",
  "cards": [
    {
      "name": "Example Everyday Card",
      "market_segment": "consumer",
      "status": "active",
      "base_flat_cashback_rate": 2.0,
      "base_rate_scope": "all eligible purchases",
      "source_ids": ["example-source"]
    }
  ]
}
```

## Validation before sending the reply

- The full name in the reply exactly matches `selection.name`.
- The reply states `selection.base_flat_cashback_rate` as a percentage.
- The reply connects that percentage to the supported flat everyday scope.
- `selection` is the first and highest-rate entry in `ranked_qualifying_cards`.
- Higher-looking excluded figures, if mentioned, are correctly characterized as category-limited, promotional, or outside the requested segment.
- The reply makes no eligibility, approval, or preferential-treatment claim.

## Customer-facing pattern

> **Recommendation: [Card name].** It earns **[rate]% cash back on [supported eligible all-purchase scope]**, the highest published standard flat rate for everyday [segment] spending among the cards reviewed. Category-specific, business-only, and temporary promotional rates are not equivalent to an across-purchase everyday rate. [Optional: Published terms list supported fee and/or minimum credit-score requirement; eligibility and approval are determined separately.]
