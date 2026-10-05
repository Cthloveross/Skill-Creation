---
name: highest-everyday-cash-back-card
description: Recommend exactly one card for a request for the highest cash-back rate on everyday spending, using supplied product terms. Selects the highest documented flat rate on all eligible purchases and produces a concise, evidence-based response.
---

# Highest Everyday Cash-Back Card

## Use this Skill
Use this Skill for an informational request to identify the one card with the highest cash back for ordinary or everyday purchases. It is a product-terms comparison only: do not make an application decision, predict approval, or take account action.

## Required evidence
Use the product documents supplied with the current task. Treat a documented rate as qualifying only when it applies broadly to **all eligible purchases** or all everyday purchases. Do not substitute:

- a category-specific rate (for example, travel or software),
- a sign-up bonus, statement credit, fee waiver, or redemption conversion,
- a rate whose scope is not established by the supplied terms.

Extract one candidate record per documented product using this schema:

```json
{
  "product_name": "string",
  "earn_rate_percent": 0,
  "earn_scope": "all_eligible_purchases | category_limited | conditional | unknown",
  "eligibility_or_access": "optional documented condition",
  "supporting_facts": ["optional source facts"]
}
```

Use `all_eligible_purchases` only for an explicit flat all-purchase/all-eligible-purchase rate. A card may still have that scope when it has separately documented application requirements; retain those requirements in `eligibility_or_access` rather than changing the earning scope. Use `conditional` when the *earning rate itself* depends on a condition such as a threshold, promotion, subscription, or merchant condition.

## Procedure
1. Read the current supplied product terms and build `candidates`. Do not claim that terms are unavailable when supplied documents state rates.
2. Run `scripts/select_everyday_cash_back.py` with the candidate array.
3. On `status: "ok"`, send **exactly** the returned `customer_response` as the substantive recommendation. It names one product, states its documented percentage, and says the rate applies to all eligible purchases.
4. Do not name or compare other card products in the customer-facing response. The customer requested one best card.
5. Do not add fees, APRs, credit-score requirements, or availability claims unless the customer asks. If voluntarily stating a documented condition, state it accurately and do not imply that the customer meets it or will be approved.
6. On `no_qualifying_candidate`, explain that the supplied terms do not establish a flat all-eligible-purchase rate for any card and do not select a category-limited alternative.
7. On `tie_requires_resolution`, explain that the highest documented flat rate is tied and ask whether the customer wants a tie-breaker such as annual fee or access requirements. Do not invent a winner.

No identity verification, account lookup, or banking action is needed for this comparison. A failed account lookup does not affect the product recommendation.

## Script interface and validation
`scripts/select_everyday_cash_back.py` reads one JSON object from stdin and emits one JSON object to stdout.

Input:

```json
{
  "candidates": [
    {
      "product_name": "Card name from current terms",
      "earn_rate_percent": 1.5,
      "earn_scope": "all_eligible_purchases"
    }
  ]
}
```

For a unique winner, output includes:

```json
{
  "status": "ok",
  "recommendation": {"product_name": "...", "earn_rate_percent": 1.5},
  "customer_response": "I recommend ..."
}
```

The helper rejects malformed records and non-finite or negative rates. Validate that `recommendation.earn_rate_percent` equals the largest numeric rate among only `all_eligible_purchases` candidates, then use `customer_response` without adding alternate products.

Example executor call (with candidates extracted from the current supplied documents):

```text
run_skill_script(
  relative_path="scripts/select_everyday_cash_back.py",
  input_json={"candidates": extracted_candidates}
)
```
