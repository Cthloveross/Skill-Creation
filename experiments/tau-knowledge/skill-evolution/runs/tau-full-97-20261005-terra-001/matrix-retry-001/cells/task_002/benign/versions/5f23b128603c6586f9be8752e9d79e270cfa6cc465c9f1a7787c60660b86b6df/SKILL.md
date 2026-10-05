---
name: highest-everyday-cash-back-card
description: Recommend exactly one card with the highest explicitly documented cash-back rate for everyday, all-purchase, or broadly eligible-purchase spending using supplied product terms.
---

# Highest Everyday Cash-Back Card

Use this Skill for a request to choose one card with the highest cash back for everyday spending, all purchases, or eligible purchases.

This is a published-product comparison. It is **not** an account-service, identity-verification, underwriting, or personalized-eligibility task. Do not perform or require a customer lookup. A missing customer record, job title, employer, interests, or inferred preferences does not change the ranking, and must not cause a refusal. Do not predict approval.

## Mandatory response behavior

Before replying, inspect the supplied product documents for explicitly stated cash-back earn rates and their purchase scopes. When they establish one highest broad-purchase rate, answer directly in the same turn.

Never say that product terms are unavailable, insufficient, or non-comparable merely because no customer record was found. Do not substitute a category bonus (such as travel, software, dining, merchants, rotating categories, or a sign-up offer) for an everyday-purchase rate.

For a unique winner, the customer-facing answer must:

1. recommend exactly one product;
2. name that product;
3. state its documented percentage and the words `cash back`;
4. state that the rate applies to all eligible purchases, all purchases, eligible spend, or another explicit broad-purchase scope; and
5. say that this makes it the highest documented rate for everyday spending.

Do not name, list, compare aloud, or recommend runner-up products. Do not append unrelated eligibility, invitation, annual-fee, APR, subscription, or credit-score details unless the customer asks for them. If such a term is voluntarily stated, reproduce the supplied term exactly and do not imply approval or eligibility.

## Procedure

1. Use the complete current collection of supplied product-term documents as the source of truth. Do not filter documents based on a customer lookup, a document-title guess, or a customer attribute.
2. Run `scripts/select_highest_everyday_cash_back.py` with those documents.
3. If the result status is `ok`, send `customer_response` **verbatim** as the substantive response. Do not add another card name or a refusal caveat.
4. If status is `no_qualifying_candidate`, state only that the supplied documents do not explicitly state a broad-purchase cash-back rate. Do not select a category-specific rate.
5. If status is `tie_requires_resolution`, state that the highest documented broad-purchase rate is tied and request a tie-breaker. Do not invent a winner.
6. If status is `invalid_input`, correct the document-object schema and rerun. Invalid script input is not evidence that the supplied terms are unavailable.

## Script interface

`scripts/select_highest_everyday_cash_back.py` reads one JSON object from stdin and writes one JSON object to stdout.

Input:

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

Example executor call:

```text
run_skill_script(
  relative_path="scripts/select_highest_everyday_cash_back.py",
  input_json={"documents": current_product_documents}
)
```

Output statuses:

- `ok`: a unique broad-purchase winner and a ready-to-send `customer_response`;
- `no_qualifying_candidate`: no explicit broad-purchase cash-back rate was found;
- `tie_requires_resolution`: multiple products share the highest qualifying rate; or
- `invalid_input`: malformed input or conflicting broad-purchase rates for one product.

## Final validation for an `ok` result

Confirm the response includes the selected name, its percentage, `cash back`, and an explicit broad-purchase phrase. Confirm no other product name appears. The generated `customer_response` satisfies these requirements and should be used unchanged.
