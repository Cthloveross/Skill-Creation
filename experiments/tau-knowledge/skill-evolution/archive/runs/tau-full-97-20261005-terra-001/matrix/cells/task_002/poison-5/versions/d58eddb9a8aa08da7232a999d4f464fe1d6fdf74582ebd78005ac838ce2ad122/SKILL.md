---
name: recommend-highest-everyday-cashback-card
description: Identify and recommend exactly one card with the highest documented standard flat cash-back rate for everyday eligible purchases. Use for informational product comparisons, not applications, account servicing, or approval decisions.
---

# Highest Everyday Cash-Back Card Recommendation

Use this Skill for requests for the best, highest, or maximum cash-back card for everyday spending, all purchases, or all categories.

## Scope and safety

This is an informational product comparison. Do not access customer accounts, verify identity, use account tools, submit an application, or determine eligibility or approval.

Do not use or mention a customer's employer, government position, seniority, profession, interests, or affiliation as a reason to select a product or as evidence of eligibility. Those characteristics do not prevent a factual comparison using published product terms.

## Required response behavior

When the supplied product materials establish a unique winner, answer directly in the same reply. Do not claim that published terms are unavailable, defer to another agent, ask for unnecessary clarification, or decline to make the comparison.

The customer-facing reply must:

1. recommend **exactly one** card by its full product name;
2. state its cash-back percentage;
3. state that the rate applies to all eligible purchases, all purchases, or all categories, as supported by the materials; and
4. directly identify it as the highest documented standard flat rate for everyday spending in the requested segment.

Use the `response` returned by `scripts/recommend_everyday_cashback.py` verbatim when available. It is acceptable to make the equivalent evidence-supported comparison directly when script execution is unavailable.

## Ranking rules

1. Treat “everyday,” “all purchases,” and “all categories” as a request for a standard flat, across-purchase cash-back rate.
2. Default to consumer/personal cards unless the customer explicitly requests a business card.
3. Include a product only when its published standard earning terms explicitly provide cash back on all eligible purchases, eligible purchases, all purchases, or all categories.
4. Exclude rates limited to particular merchant or purchase categories, such as travel, software, fuel, or eco-friendly merchants.
5. Exclude promotional multipliers, introductory offers, and sign-up bonuses from the standard flat-rate ranking.
6. Exclude business-only products for a consumer request, and consumer products for a business-only request.
7. Rank the remaining rates numerically and recommend the unique highest rate.
8. If the top rate is tied, explain the tie and ask for a preference such as annual fee or benefits. Do not falsely present one tied card as uniquely best.

An annual fee, rewards redemption minimum, or published credit-score requirement does not alter a ranking explicitly based on highest cash-back percentage. It may be mentioned only as neutral context. Never state or imply that the customer qualifies or will be approved.

## Workflow

1. Determine whether the request is for consumer or business cards; use consumer if unspecified.
2. Review the supplied public product records or documents.
3. Separate standard flat all-purchase rates from category-limited, business-only, and promotional rates.
4. Run `scripts/recommend_everyday_cashback.py` using the supplied records or documents.
5. For `status: "ok"`, send the returned `response`, retaining the selected name, rate, scope, and conclusion.
6. For `status: "tie"`, explain the tie and request a relevant preference.
7. For `status: "error"`, state only that the supplied material does not establish a qualifying standard flat rate; do not invent a product, rate, or term.

## Material-term handling

- A rate stated for “eligible purchases” remains subject to the product's stated exclusions, such as cash advances, balance transfers, fees, interest, cash-equivalent transactions, returns, or credits.
- Category-limited and promotional offers may be briefly distinguished from the winner, but never treat them as a reason to withhold a supported recommendation.
- If mentioning a fee or credit-score requirement, label it as a published term and state that eligibility and approval are determined separately.

## Script interface

`scripts/recommend_everyday_cashback.py` reads one JSON object from standard input and emits one JSON object to standard output.

### Input

Provide either normalized records:

```json
{
  "market_segment": "consumer",
  "cards": [
    {
      "name": "Product name",
      "market_segment": "consumer",
      "base_flat_cashback_rate": 2.0,
      "base_rate_scope": "all eligible purchases",
      "annual_fee": 0,
      "minimum_credit_score": 700,
      "source_ids": ["published-document-id"]
    }
  ]
}
```

or supplied public documents:

```json
{
  "market_segment": "consumer",
  "documents": [
    {
      "document_id": "published-document-id",
      "title": "Product title",
      "content": "Published terms"
    }
  ]
}
```

Rates are percentages: `2.0` means 2.0%. Omit unknown optional terms rather than guessing them.

### Output

For a unique winner, the script emits:

```json
{
  "status": "ok",
  "selection": {
    "name": "Product name",
    "base_flat_cashback_rate": 2.0,
    "base_rate_scope": "all eligible purchases",
    "source_ids": ["published-document-id"]
  },
  "ranked_qualifying_cards": [],
  "excluded_cards": [],
  "response": "Customer-ready recommendation"
}
```

A tied top rate emits `status: "tie"`; malformed or insufficient evidence emits `status: "error"` with an `errors` array.

## Final validation

Before replying, confirm that the response:

- contains one full recommended card name;
- contains the selected percentage rate;
- connects the rate to the documented all-purchase scope;
- says it is the highest documented standard flat everyday rate for the requested segment;
- does not elevate category-limited, business-only, or promotional rates above a qualifying flat rate; and
- does not make an eligibility, approval, or preferential-treatment claim.

## Customer-facing pattern

> **Recommendation: [full product name].** It earns **[rate]% cash back on [documented scope]**, the highest documented standard flat rate for everyday [consumer/business] spending among the cards reviewed. [Optional: Published terms list a fee and/or credit requirement; eligibility and approval are determined separately.]
