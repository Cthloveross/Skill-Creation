---
name: recommend-highest-everyday-cashback-card
description: Directly recommend the one consumer credit card with the highest published standard flat cash-back rate for eligible everyday purchases. Use for product-information comparisons, not applications, account-specific advice, or card actions.
---

# Highest Everyday Cash-Back Card Recommendation

Use this Skill when a customer asks which card has the highest cash back for everyday spending, all purchases, or broadly applicable eligible purchases.

## Scope

- Treat the request as a comparison of **standard consumer-card earn rates** unless the customer explicitly requests business cards.
- An everyday rate must expressly apply across all eligible purchases, all purchases, or all categories. It is not enough that a card has a high rate in one merchant category.
- Do not let a category-only rate, merchant discount, business-only product, sign-up bonus, introductory offer, or time-limited promotion displace a standard flat everyday rate.
- A product recommendation is informational and is not a banking action. Do not access an account, apply for a product, determine approval, or take card action.
- Do not infer eligibility, approval, pricing, or preferential treatment from a customer’s employer, public position, identity, or personal characteristics.

## Required response behavior

When the supplied product material establishes a highest qualifying rate, answer the customer directly with one recommendation. Do **not** decline or ask for terms merely because individual eligibility is unknown. Eligibility is separate from comparing published products.

State all of the following:

1. the selected card’s full name;
2. its percentage cash-back rate;
3. that the rate applies to eligible everyday/all-purchase spending; and
4. a short explanation that category-specific, business-only, or temporary offers are not comparable to a standard flat everyday rate.

If supported by the same supplied material, neutrally mention material terms such as an annual fee and a minimum credit-score requirement. Say that they are published requirements or terms, not that the customer meets them. Do not introduce unsupported fees, dates, qualifications, or product features.

## Decision method

1. Read all supplied product documents relevant to the requested segment.
2. Create one candidate per product, keeping its standard flat rate separate from category rates and promotions.
3. Exclude candidates that are outside the requested segment, inactive, promotional-only, or do not expressly offer a standard rate across eligible purchases.
4. Rank the remaining candidates by standard flat percentage rate. A higher rate wins even if it has a fee; a fee is a caveat, not a substitute ranking criterion for a request for the *highest cash back*.
5. Provide the direct recommendation and supported caveats.

Use `scripts/recommend_everyday_cashback.py` for deterministic extraction, ranking, and response composition when product documents are available as structured runtime input. The script’s response must be used as the factual core of the customer reply; it may be lightly reformatted but must retain the selected name and rate.

## Script interface

The script reads one JSON object from standard input and emits one JSON object on standard output.

### Input schema

Supply either `documents` or pre-extracted `cards`.

```json
{
  "market_segment": "consumer",
  "documents": [
    {
      "document_id": "optional-string",
      "title": "Product title",
      "content": "Published product terms"
    }
  ]
}
```

or:

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

Rates are percentages: `2.0` means 2.0%. For document input, document titles identify the product and the parser only accepts explicit flat-rate language. A document identifier or title indicating a business product is classified as business. Missing fields are omitted rather than invented.

### Output schema

Successful output:

```json
{
  "status": "ok",
  "selection": {
    "name": "string",
    "base_flat_cashback_rate": 2.0,
    "annual_fee": 0.0,
    "minimum_credit_score": 700,
    "source_ids": ["source-id"]
  },
  "ranked_qualifying_cards": [],
  "excluded_cards": [],
  "response": "Customer-ready direct recommendation"
}
```

If the documents do not establish a qualifying standard flat rate, output has `status: "error"` and an `errors` list. In that case, explain precisely that the supplied materials do not establish an everyday flat-rate winner; do not guess.

### Runnable call example

Pass this object to the packaged-script runner with `relative_path` set to `scripts/recommend_everyday_cashback.py`:

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
      "annual_fee": 0,
      "source_ids": ["example-source"]
    }
  ]
}
```

## Validation before responding

- Confirm the card named in the reply equals `selection.name`.
- Confirm the percentage in the reply equals `selection.base_flat_cashback_rate`.
- Confirm the selected rate is the first and numerically highest rate in `ranked_qualifying_cards`.
- Confirm apparently higher figures in excluded material are category-limited, temporary, or outside the requested segment.
- Preserve the qualification “eligible purchases”; do not imply that cash advances, fees, balance transfers, returns, or other excluded transactions earn rewards.
- Do not claim the customer qualifies, is approved, or receives special treatment.

## Customer-facing pattern

> **Recommendation: [Card name].** It earns **[rate]% cash back on all eligible purchases**, the highest published standard flat rate for everyday consumer spending among the cards reviewed. Category-specific, business-card, and temporary promotional rates are not equivalent to an across-purchase everyday rate. Published terms also list [supported fee and/or credit requirement]. Eligibility and approval are determined separately.
