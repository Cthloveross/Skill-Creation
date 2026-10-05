---
name: highest-everyday-cash-back-card
description: Recommend exactly one card for a request for the highest cash-back rate on everyday spending, using supplied product terms. It identifies the highest documented flat rate on all eligible purchases and produces a concise, evidence-based response.
---

# Highest Everyday Cash-Back Card

## Use this Skill
Use this Skill for an informational request to identify the one card with the highest cash back for ordinary or everyday purchases. This is a product-terms comparison only: do not make an application decision, predict approval, access customer data, or take account action.

A customer identity lookup, including an unsuccessful lookup, is irrelevant to this comparison. The customer's employer, job title, or personal interests do not change a request whose stated criterion is highest everyday cash-back rate.

## Required evidence and selection rule
Use the product documents supplied with the current task. A qualifying everyday rate must be explicitly documented as applying broadly to **all eligible purchases**, all purchases, or everyday purchases. Do not substitute:

- a category-specific rate (such as travel or software),
- a sign-up bonus, statement credit, fee waiver, or redemption conversion,
- a rate with an unestablished scope,
- an earn rate conditional on a promotion, threshold, subscription, or merchant category.

Application requirements do not change an otherwise flat earning scope. Retain them separately if relevant, but do not claim the customer meets them or will be approved.

## Mandatory workflow
1. Gather all currently supplied credit-card product documents. Do **not** say product terms are unavailable when the supplied documents state product cash-back rates.
2. Run `scripts/extract_and_select_everyday_cash_back.py`, passing the documents in its `documents` input. This helper extracts documented broad-purchase rates and selects the unique highest rate.
3. If the result has `status: "ok"`, send **exactly** its `customer_response` as the substantive customer-facing answer. This ensures the response names exactly one card, explicitly states the percentage, and explicitly states the all-eligible-purchases scope.
4. Do not mention, name, or compare other products in the customer-facing answer. The customer asked for one best card.
5. Do not add annual fees, APRs, credit-score requirements, or access conditions unless the customer asks. If voluntarily stated, quote the supplied term accurately and do not imply approval or eligibility.
6. If the result has `status: "no_qualifying_candidate"`, explain that the supplied terms do not establish a flat broad-purchase rate for any card. Do not select a category-limited alternative.
7. If the result has `status: "tie_requires_resolution"`, explain that the highest documented broad-purchase rate is tied and ask whether the customer wants a tie-breaker such as annual fee or access requirements. Do not invent a winner.
8. If the input is unavailable or malformed, use the error message to correct the document input if possible. Never turn an input-format issue into a false claim that the published terms do not contain rates.

## Script interface and validation
`scripts/extract_and_select_everyday_cash_back.py` reads one JSON object from stdin and emits one JSON object to stdout.

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

For a unique winner, the output is:

```json
{
  "status": "ok",
  "recommendation": {
    "product_name": "Card name",
    "earn_rate_percent": 1.5,
    "earn_scope": "all_eligible_purchases"
  },
  "customer_response": "I recommend the Card name. It earns 1.5% cash back on all eligible purchases, the highest documented rate for everyday spending."
}
```

The output also includes `extracted_candidates` for auditability. The helper accepts only nonnegative finite numeric rates, excludes category-limited and conditional rates from the ranking, and reports ties rather than choosing arbitrarily. Before responding, confirm `status` is `ok` and use its `customer_response` verbatim.

Example executor call, where `current_product_documents` contains every relevant current supplied document:

```text
run_skill_script(
  relative_path="scripts/extract_and_select_everyday_cash_back.py",
  input_json={"documents": current_product_documents}
)
```

`scripts/select_everyday_cash_back.py` is also available when an executor has already extracted candidates. It reads `{"candidates": [...]}` and returns the same selection and response fields.
