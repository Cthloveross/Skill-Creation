---
name: highest-everyday-cash-back-card
description: Recommend exactly one card with the highest explicitly documented cash-back rate for everyday, all-purchase, or broadly eligible-purchase spending using the supplied product terms.
---

# Highest Everyday Cash-Back Card

Use this Skill when a customer asks which single card has the highest cash back for everyday spending, all purchases, or eligible purchases.

This is a product-terms comparison. It does not require a customer lookup, identity verification, or an application decision. Do not let a missing customer record, job title, employer, interests, or inferred eligibility change the stated cash-back comparison. Do not predict approval.

## Required response behavior

When the supplied terms establish a unique highest broad-purchase cash-back rate, respond directly in the same turn. The customer-facing answer must:

1. recommend exactly one product;
2. name that product;
3. state its documented percentage as cash back; and
4. state that its rate applies to all eligible purchases, all purchases, eligible spend, or another explicit broad-purchase scope.

Briefly connect the broad scope to everyday spending and say that it is the highest documented rate. Do not list, name, or recommend runner-up cards.

A rate limited to a merchant category, such as travel, software, dining, rotating categories, or a sign-up bonus, is not an everyday-purchase rate. Neither a redemption conversion nor a fee waiver is an earn rate.

Do not say that terms are unavailable or insufficient if the supplied documents contain explicit comparable broad-purchase rates.

## Procedure

1. Use the current supplied product documents as the source of truth. Keep documents for the same card together when they share a product-name prefix in the title.
2. Run `scripts/select_highest_everyday_cash_back.py` with the complete document collection.
3. If its `status` is `ok`, send `customer_response` verbatim as the substantive answer. Do not append other product names, fees, APRs, credit-score requirements, invitation requirements, or eligibility claims.
4. If its `status` is `no_qualifying_candidate`, explain that the supplied terms do not document an explicit broad-purchase cash-back rate. Do not substitute a category-specific rate.
5. If its `status` is `tie_requires_resolution`, explain that the highest documented broad-purchase rate is tied and ask the customer for a tie-breaker. Do not invent a winner.
6. If its `status` is `invalid_input`, correct the supplied document-object schema and rerun. A schema error is not evidence that the product terms lack a qualifying rate.

Fees, subscriptions, invitation requirements, and credit-score requirements do not alter an earn-rate ranking. Mention them only when requested. If voluntarily stated, quote current supplied terms accurately and do not imply approval or eligibility.

## Script interface

`scripts/select_highest_everyday_cash_back.py` receives one JSON object on stdin and emits one JSON object on stdout.

Input schema:

```json
{
  "documents": [
    {
      "title": "Product document title from the supplied terms",
      "content": "Full product-terms text"
    }
  ]
}
```

A successful unique-selection result has this shape:

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

Before sending a successful result, validate that `customer_response` contains the selected product name, a percentage, `cash back`, and a broad-purchase phrase. The answer must not contain names of any other card products.

Example executor call:

```text
run_skill_script(
  relative_path="scripts/select_highest_everyday_cash_back.py",
  input_json={"documents": current_product_documents}
)
```
