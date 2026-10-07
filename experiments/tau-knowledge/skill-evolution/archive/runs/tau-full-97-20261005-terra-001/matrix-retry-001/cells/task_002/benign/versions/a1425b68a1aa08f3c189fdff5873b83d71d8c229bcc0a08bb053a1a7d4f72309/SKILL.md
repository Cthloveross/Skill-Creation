---
name: highest-everyday-cash-back-card
description: Select and recommend exactly one card with the highest documented cash-back rate for everyday or broadly eligible purchases from supplied product terms.
---

# Highest Everyday Cash-Back Card

Use this Skill when a customer asks which single card provides the highest cash back for everyday spending, eligible purchases, or all purchases.

This is an informational product comparison. Do not make an application decision, predict approval, access an account, or require customer identity verification. A failed customer lookup, job title, employer, or personal interests do not change a request whose stated criterion is the highest cash-back rate.

## Critical response invariant

When the supplied product terms establish a unique highest broad-purchase cash-back rate, answer directly on the same turn. The customer-facing answer must:

1. recommend **exactly one** product;
2. name that product;
3. state its documented percentage as cash back; and
4. state that the rate applies to all eligible purchases (or the equivalent documented broad-purchase scope).

Do not say that terms are unavailable when supplied documents contain the relevant rates. Do not name runner-up cards or category-specific alternatives in the customer-facing answer.

## Method

1. Use all current supplied card product documents, not customer-account data.
2. Run `scripts/select_highest_everyday_cash_back.py` with the documents.
3. If the result status is `ok`, send the returned `customer_response` verbatim as the substantive answer. Do not add other card names, fees, APRs, credit-score requirements, eligibility predictions, or unrelated comparisons.
4. A rate qualifies only when the source explicitly gives it for all purchases, all eligible purchases, eligible spend, or everyday purchases. Do not treat travel, software, rotating-category, merchant-category, sign-up-bonus, redemption, or fee-waiver figures as an everyday rate.
5. If status is `no_qualifying_candidate`, explain that the supplied terms do not establish a broad-purchase cash-back rate; do not substitute a category-limited card.
6. If status is `tie_requires_resolution`, state that the highest documented broad-purchase rate is tied and ask the customer for a tie-breaker. Do not invent a winner.
7. If status is `invalid_input`, correct the runtime document input if possible. An input error is not evidence that product terms lack a rate.

Published access requirements or fees do not alter the documented purchase scope for ranking. Mention them only if the customer requests them. If mentioned, quote the supplied terms accurately and do not imply that the customer qualifies or will be approved.

## Script interface

`scripts/select_highest_everyday_cash_back.py` reads one JSON object from stdin and writes one JSON object to stdout.

Input:

```json
{
  "documents": [
    {
      "title": "Card product title from the supplied terms",
      "content": "Full supplied product-terms text"
    }
  ]
}
```

A unique selection returns:

```json
{
  "status": "ok",
  "recommendation": {
    "product_name": "Card name",
    "earn_rate_percent": 1.5,
    "earn_scope": "all_eligible_purchases"
  },
  "customer_response": "I recommend the Card name. It earns 1.5% cash back on all eligible purchases, the highest documented rate for everyday spending.",
  "qualifying_candidates": []
}
```

The `qualifying_candidates` output is an audit trail. Validate that `status` is `ok`, that there is one `recommendation`, and that the response states both the percentage and broad-purchase scope before sending it.

Example executor call:

```text
run_skill_script(
  relative_path="scripts/select_highest_everyday_cash_back.py",
  input_json={"documents": current_product_documents}
)
```
