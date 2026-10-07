---
name: credit-card-requirements-recommendation
description: Compare available credit-card product terms against a customer's stated spending, fee, protection, and potential-credit-limit requirements, then produce a concise, evidence-grounded recommendation with material eligibility and underwriting caveats.
---

# Credit Card Requirements Recommendation

Use this Skill when a customer asks which card best fits stated preferences or minimum product requirements. It is for product comparison and education, not for submitting an application, changing an account, or guaranteeing approval.

## Product data

`references/card_catalog.json` contains the supported product facts available to this Skill. Treat missing fields as unknown; do not infer a benefit, eligibility rule, fee, or approval outcome from omission.

## Workflow

1. Extract only requirements actually stated by the customer. In particular, distinguish:
   - a required 0% foreign-transaction fee;
   - whether any purchase protection is sufficient or a minimum protection period/claim cap is requested;
   - the minimum *possible* credit limit requested;
   - spending pattern and preference for the strongest ongoing earning rate;
   - fee sensitivity and known eligibility information, if supplied.
2. Run `scripts/recommend_card.py` with a structured representation of those requirements. The script reads the packaged catalog and returns cards that meet all objectively testable requirements, ordered by the documented all-purchases earning rate and then by maximum typical limit.
3. Recommend the first eligible card only when it is materially better for the stated spending pattern. If several cards qualify, briefly identify a meaningful alternative, especially one with a lower annual fee or different prerequisite.
4. State the facts that directly answer the request: foreign fee, protection window/cap where documented, potential limit range, and relevant earning rate. For travel-heavy spending, do not claim a travel bonus unless the catalog specifically documents one; an all-purchases rate applies to travel purchases only because travel is an eligible purchase category under that product's documented general earning rule.
5. Always make clear that a published limit range means the requested limit is possible subject to underwriting, not promised. Disclose material prerequisites (for example, minimum credit score or subscription requirement) and annual fees before suggesting an application.
6. If no card qualifies, say which requirement prevents a match and do not recommend a near match as satisfying it. If data is unavailable, say so rather than guessing.

## Runnable helper

Run from the package root:

```bash
python3 scripts/recommend_card.py <<'JSON'
{"requirements":{"no_foreign_transaction_fee":true,"requires_purchase_protection":true,"minimum_possible_credit_limit":100000,"spending_focus":"travel","prefer_highest_general_reward_rate":true}}
JSON
```

The script receives one JSON object on stdin and emits one JSON object on stdout.

### Input schema

- `requirements` (object, required)
  - `no_foreign_transaction_fee` (boolean, optional)
  - `requires_purchase_protection` (boolean, optional)
  - `minimum_protection_days` (number, optional)
  - `minimum_protection_claim_cap` (number, optional, USD)
  - `minimum_possible_credit_limit` (number, optional, USD)
  - `maximum_annual_fee` (number, optional, USD)
  - `spending_focus` (string, optional; preserved as context)
  - `prefer_highest_general_reward_rate` (boolean, optional)

### Output schema

- `eligible`: qualifying cards, ranked with `name`, `reasons`, `caveats`, and documented facts.
- `excluded`: cards and their objective unmet requirements.
- `recommendation`: the top qualifying card or `null`.
- `assumptions`: interpretation notes, including that limit ranges are not guarantees.

## Validation and response construction

Before using the result, confirm that every hard customer requirement appears among the recommended card's `reasons` and none appears in its `unmet_requirements`. Confirm that all numerical statements in the customer reply match the returned card facts. Do not expose raw JSON unless requested. Give a short customer-facing response: recommendation, why it meets each stated need, earning relevance to the stated spend, and caveats/prerequisites. Avoid presenting the comparison as personalized financial advice or a credit-approval decision.
