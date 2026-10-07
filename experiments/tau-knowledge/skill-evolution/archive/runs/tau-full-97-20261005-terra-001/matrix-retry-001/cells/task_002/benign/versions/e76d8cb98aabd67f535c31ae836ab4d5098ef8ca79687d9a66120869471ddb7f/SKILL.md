---
name: highest-everyday-cash-back-card
description: Recommend exactly one card with the highest explicitly documented cash-back rate for everyday, all-purchase, or broadly eligible purchase spending from supplied product terms.
---

# Highest Everyday Cash-Back Card

Use this Skill when a customer asks for one best card based on the highest cash back for everyday spending, eligible purchases, or all purchases.

This is a product-terms comparison, not an application or account-servicing request. Do not use customer lookup results, identity verification, job title, employer, personal interests, or inferred preferences to alter the stated cash-back comparison. Do not predict approval or eligibility.

## Required response behavior

When supplied product terms establish a unique highest broad-purchase cash-back rate, answer directly in the same turn. The substantive customer answer must:

1. recommend exactly one product;
2. name the product;
3. state its documented percentage as cash back; and
4. state that the rate applies to all eligible purchases, all purchases, eligible spend, or another explicitly documented broad-purchase scope.

Do not say that product terms are unavailable or insufficient when the supplied documents contain comparable broad-purchase rates. Do not present runner-up products, category-specific alternatives, or an unrelated product list. A category rate such as travel, software, merchant category, rotating category, sign-up bonus, redemption rate, or fee waiver is not an everyday-purchase rate.

## Procedure

1. Treat the current supplied product documents as the source of truth. No customer-account data is needed for this comparison.
2. Run `scripts/select_highest_everyday_cash_back.py` with the complete current document collection.
3. If the returned `status` is `ok`, send its `customer_response` verbatim as the substantive answer. This preserves the required single recommendation, rate, and scope. Do not append names of other cards or unsolicited fee, APR, score, or eligibility discussion.
4. If `status` is `no_qualifying_candidate`, explain that the supplied terms do not establish a broad-purchase cash-back rate. Do not replace the missing evidence with a category-specific recommendation.
5. If `status` is `tie_requires_resolution`, explain that the highest documented broad-purchase rate is tied and ask for a tie-breaker. Do not invent a winner.
6. If `status` is `invalid_input`, repair the document input schema if possible and rerun. An input failure is not evidence that product terms lack a qualifying rate.

Published fees, invitation requirements, subscriptions, and credit-score requirements do not change the purchase-rate ranking. Discuss them only when the customer requests them. If voluntarily stated, quote the current supplied terms accurately and do not imply that the customer qualifies or will be approved.

## Script interface

`scripts/select_highest_everyday_cash_back.py` reads one JSON object from stdin and writes one JSON object to stdout.

Input schema:

```json
{
  "documents": [
    {
      "title": "Card product title from supplied terms",
      "content": "Full supplied product-terms text"
    }
  ]
}
```

Successful unique-selection output schema:

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

Before sending a successful result, validate that `status` is `ok`, `recommendation` is present, and `customer_response` contains the product name, a percentage, and broad-purchase scope.

Example executor call:

```text
run_skill_script(
  relative_path="scripts/select_highest_everyday_cash_back.py",
  input_json={"documents": current_product_documents}
)
```
