---
name: highest-everyday-cash-back-card
description: Recommend exactly one card when a customer asks for the highest cash-back rate on everyday spending. Use this for informational card comparisons based on supplied product terms; it distinguishes a flat rate on all eligible purchases from category-limited or conditional rates.
---

# Highest Everyday Cash-Back Card

## Purpose
Select one product with the highest documented cash-back percentage that applies to **all eligible/everyday purchases**. This is an informational comparison, not an application decision, approval prediction, or account action.

## Required runtime input
Build a `candidates` array from the currently supplied product documents. Do not reuse a catalog from another request or infer missing terms. Each candidate supplied to the helper has this schema:

```json
{
  "product_name": "string",
  "earn_rate_percent": 0,
  "earn_scope": "all_eligible_purchases | category_limited | conditional | unknown",
  "eligibility_or_access": "optional string",
  "supporting_facts": ["optional factual source statements"]
}
```

Only include a numeric `earn_rate_percent` where the source explicitly states it. Use:

- `all_eligible_purchases` for a flat rate on all eligible purchases or all everyday purchases.
- `category_limited` for a rate limited to named categories (such as travel or software).
- `conditional` when a rate depends on a subscription, spend threshold, merchant condition, promo, or other condition rather than applying generally to all eligible purchases.
- `unknown` when the scope cannot be established.

If the source represents cash-back rewards as points, convert points to dollars only if the supplied terms explicitly provide a conversion. Never treat an unrelated points-per-dollar rate as a cash-back percentage without enough information to calculate it.

## Procedure
1. Identify that the request is for the highest rate on everyday spending. Do not substitute the highest category bonus, sign-up bonus, statement credit, or a fee waiver.
2. Extract each card's ongoing earning rate and its scope from the current supplied documents.
3. Run the selection helper:

   ```json
   {"candidates": [ ... ]}
   ```

   using `scripts/select_everyday_cash_back.py`.
4. If `status` is `ok`, make **one** recommendation: use `recommendation.product_name` and its `earn_rate_percent`. State that the rate applies to eligible purchases, using the returned scope. Mention a material access limitation only when the selected product has one explicitly documented (for example, invitation-only); do not speculate about approval.
5. Keep the customer-facing response concise and avoid presenting alternatives because the customer asked for one card. Annual fees, APR, redemption thresholds, and other terms should not change a rate-only ranking, but may be mentioned briefly only if needed to prevent a misleading claim and are explicitly sourced.
6. If `status` is `no_qualifying_candidate`, say that the provided terms do not establish a flat, all-eligible-purchase cash-back rate for any card, so a reliable one-card recommendation cannot be made. Do not choose a category-limited product as a substitute.
7. If `status` is `tie_requires_resolution`, ask one narrow follow-up only if the customer wants a tie broken by a criterion such as annual fee or eligibility. Do not invent a tie-breaker. If a single answer is mandatory, explain that the available terms show a tie rather than falsely claiming one has the higher rate.

## Customer and account handling
This comparison does not require account lookup or identity verification. Do not claim the recommended card is available to, suitable for, or approved for the customer. If a source says access is invitation-only or has a score/subscription requirement, present it as a documented condition, not as a determination about the customer.

## Helper input/output and validation
`scripts/select_everyday_cash_back.py` reads one JSON object from standard input and emits one JSON object to standard output.

Input:

```json
{"candidates": [{"product_name": "...", "earn_rate_percent": 1.5, "earn_scope": "all_eligible_purchases"}]}
```

Successful output contains `status: "ok"`, one `recommendation`, and the qualifying candidates considered. The selected rate must equal the maximum numeric rate among candidates whose scope is exactly `all_eligible_purchases`. The script rejects malformed candidate records and invalid negative/non-finite rates rather than silently ranking them.

Example invocation by an executor (with values drawn from its current source documents):

```text
run_skill_script(
  relative_path="scripts/select_everyday_cash_back.py",
  input_json={"candidates": extracted_candidates}
)
```
