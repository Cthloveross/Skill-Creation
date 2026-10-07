---
name: recommend-highest-everyday-cashback-card
description: Recommend the single consumer or business card with the highest published standard flat cash-back rate for everyday eligible purchases. Use for informational card comparisons; do not use for applications, account servicing, or approval decisions.
---

# Highest Everyday Cash-Back Card Recommendation

Use this Skill when a customer asks for the best, highest, or maximum cash-back card for everyday spending, all purchases, or all categories.

## Mandatory response behavior

This is an informational comparison, not a banking action. Do not access an account, verify identity, use banking tools, submit an application, or make an approval determination.

When product materials supplied in the conversation or task establish a winner, answer in the same reply with **exactly one clear recommendation**. Product documents present in the task context count as available source material. Do not say that terms are unavailable, decline to compare products, defer to another agent, or make the recommendation conditional on a customer's employer, title, government role, seniority, identity, or affiliation.

The reply must include all of the following:

1. the full winning product name;
2. its cash-back rate as a percentage;
3. the supported scope of that rate, such as "all eligible purchases"; and
4. a direct statement that it is the highest documented standard flat rate for the requested everyday segment.

Use the returned `response` from `scripts/recommend_everyday_cashback.py` when the helper is run. It is also acceptable to make the same evidence-supported comparison directly from supplied materials when no script input is available.

## Ranking method

1. Interpret “everyday,” “all purchases,” and “all categories” as a request for a standard **flat, across-purchase** cash-back rate.
2. Default to consumer/personal cards unless the customer explicitly asks for business cards.
3. Include only an active card whose published standard earnings explicitly apply to all eligible purchases, eligible purchases, all purchases, or all categories.
4. Exclude a rate from the flat everyday ranking when it is restricted by merchant category, purchase category, business-only status for a consumer request, a sign-up condition, a promotional period, or a temporary multiplier.
5. Rank the remaining cards by cash-back percentage and recommend the sole highest-rate card.
6. If the highest standard rate is tied, explain the tie and ask for a relevant preference instead of arbitrarily presenting one as uniquely best.

An annual fee, redemption threshold, credit-score requirement, or other product term may be relevant context, but it does not change a ranking whose stated criterion is the highest cash-back percentage.

## Neutral treatment and accurate caveats

- Do not infer, promise, assess, or imply eligibility, approval, preferential pricing, or special treatment from personal characteristics, employment, public office, employer, profession, interests, or affiliations.
- State a published fee or minimum credit-score requirement only as a neutral product term. Do not say the customer qualifies or will be approved.
- Preserve stated limitations. In particular, “eligible purchases” does not include exclusions identified by the product terms, such as fees, interest, cash advances, balance transfers, cash-equivalent transactions, or returned purchases.
- If helpful, briefly distinguish the winning flat rate from category-limited or promotional rates. Do not turn that distinction into a refusal.

## Workflow

1. Identify whether the customer requests consumer or business products. If unspecified, use consumer products.
2. Read the supplied product records or product documents and identify explicit standard flat cash-back rates.
3. Exclude category-only and temporary offers before ranking.
4. Run `scripts/recommend_everyday_cashback.py` with the available records or documents when practical.
5. If its `status` is `ok`, send its `response` verbatim or an equivalent response that retains the selected name, rate, scope, and highest-flat-rate conclusion.
6. If it returns `tie`, ask for a preference needed to break the tie. If it returns `error`, identify the missing published evidence without inventing a product or rate.

## Script interface

`scripts/recommend_everyday_cashback.py` reads one JSON object from standard input and writes one JSON object to standard output.

### Input

Use either normalized card records:

```json
{
  "market_segment": "consumer",
  "cards": [
    {
      "name": "Card product name",
      "market_segment": "consumer",
      "status": "active",
      "base_flat_cashback_rate": 2.0,
      "base_rate_scope": "all eligible purchases",
      "annual_fee": 0,
      "minimum_credit_score": 700,
      "source_ids": ["public-document-id"]
    }
  ]
}
```

or public product documents:

```json
{
  "market_segment": "consumer",
  "documents": [
    {
      "document_id": "public-document-id",
      "title": "Card product title",
      "content": "Published product terms"
    }
  ]
}
```

All rates are percentages: `2.0` means 2.0%. Unknown optional terms may be omitted. Never supply a guessed rate, fee, score, segment, or status.

### Output

A unique selection has this form:

```json
{
  "status": "ok",
  "selection": {
    "name": "Card product name",
    "base_flat_cashback_rate": 2.0,
    "base_rate_scope": "all eligible purchases",
    "source_ids": ["public-document-id"]
  },
  "ranked_qualifying_cards": [],
  "excluded_cards": [],
  "response": "Customer-ready recommendation"
}
```

A tied top rate returns `{"status":"tie",...}`. Invalid or insufficient data returns `{"status":"error","errors":["reason"]}`.

## Final validation

Before sending the reply, verify that it:

- names one selected card in full;
- states its percentage cash-back rate;
- connects that rate to the published all-purchase or all-category scope;
- explicitly identifies it as the highest documented standard flat everyday rate in the requested segment;
- does not characterize a category-limited, business-only, or promotional rate as a better everyday flat rate; and
- makes no eligibility, approval, or preferential-treatment claim.

## Customer-facing pattern

> **Recommendation: [full card name].** It earns **[rate]% cash back on [supported scope]**, the highest documented standard flat rate for everyday [consumer/business] spending among the cards reviewed. [Optional neutral published fee or credit requirement.] Eligibility and approval are determined separately.
