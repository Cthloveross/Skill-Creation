---
name: credit-card-needs-recommendation
description: Recommend a credit-card product from supplied product facts when a customer states required fees, protections, credit-limit capacity, and spending priorities. Use for informational product comparisons only; do not apply, change an account, or make a credit decision.
---

# Credit-card needs recommendation

Use this Skill to give an evidence-based product recommendation without performing any banking action.

## Scope and safety

- Treat stated requirements such as a maximum foreign-transaction fee, minimum credit-limit capacity, and purchase-protection requirement as hard filters.
- Treat spend patterns as ranking criteria only after the hard filters are satisfied.
- Do not promise approval, a specific assigned limit, an invitation, a waiver, rewards posting, or coverage of a particular future claim.
- Do not submit an application or access customer records. If a later request requires an account, card, payment, transfer, profile, or other banking action, first verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.
- If product facts are missing or ambiguous, say so rather than infer them.

## Packaged product facts

For the supplied card catalogue, consult `references/diamond_elite_facts.md`. It supports a recommendation only for the documented features. The source describes the Diamond Elite Card as invitation-only, with consideration guidance of a credit score of at least 780; this is not a guarantee of an invitation or approval.

## Workflow

1. Extract the customer's hard requirements and preferences. Normalize currency and percentages, but preserve qualifiers such as “possibility” or “at least.”
2. Gather product facts from the runtime-supplied catalogue if one is provided. If the task uses the packaged catalogue, use the packaged reference.
3. For a structured comparison, run `scripts/rank_cards.py`. It accepts a JSON product list and requirement object on stdin and emits a ranked JSON assessment on stdout. The script is deterministic and does not make decisions or external calls.
4. Exclude every product that fails a known hard requirement. A product with an unknown value for a hard requirement is not a confirmed match.
5. Among confirmed matches, favor the card whose documented reward structure best matches the stated spending pattern. Do not manufacture a travel multiplier: a flat all-purchase reward rate can cover travel purchases only when the product facts explicitly say it applies to eligible purchases generally.
6. Give the customer a direct recommendation, followed by the facts establishing each required feature and any material eligibility or uncertainty note. Mention only terms documented in the available facts.

## Response structure

Use concise plain language:

- **Recommendation:** product name and why it fits the overall use case.
- **Requirement check:** no foreign transaction fee; documented purchase-protection window and cap/coverage qualification; documented limit range showing whether it can reach the requested threshold.
- **Rewards fit:** explain the documented earning rate and whether it applies to the customer’s travel spending.
- **Important eligibility note:** invitation, score, subscription, underwriting, or other condition if documented; distinguish potential limit range from an offered limit.

For the packaged catalogue, an appropriate conclusion is to recommend the Diamond Elite Card when the customer needs all three stated hard requirements and values travel spending, because the reference documents 0% foreign transaction fee, 150-day purchase protection with unlimited coverage subject to terms and exclusions, a $37,500–$375,000 standard limit range, and 5.0% cash back on eligible purchases. Include its invitation-only and 780-score consideration note.

## Script interface

Run:

```text
python scripts/rank_cards.py <<'JSON'
{"requirements":{"max_foreign_transaction_fee_pct":0,"min_credit_limit":100000,"purchase_protection_required":true,"spend_priority":"travel"},"products":[{"name":"Example","foreign_transaction_fee_pct":0,"credit_limit_min":10000,"credit_limit_max":150000,"purchase_protection_days":120,"purchase_protection_coverage":"subject to terms","rewards":{"type":"flat_cash_back","rate_pct":2.0,"eligible_spend":"all eligible purchases"}}]}
JSON
```

Input schema:

- `requirements` is an object. Supported keys: `max_foreign_transaction_fee_pct`, `min_credit_limit`, `purchase_protection_required`, `min_purchase_protection_days`, and `spend_priority`.
- `products` is an array of objects with `name` and the corresponding documented numeric fields. `rewards` is optional and may include `type`, `rate_pct`, and `eligible_spend`.

Output schema:

- `qualifying_products`: confirmed matches, sorted by a transparent reward-fit score.
- `excluded_products`: products with the failed or unknown hard-filter fields.
- `requirements`: normalized copy of the request.

Validate the output before using it: it must be JSON, every qualifying product must have an empty `hard_filter_failures` list, and any product whose required fact is absent must appear under `excluded_products` rather than being presented as a confirmed match.
