---
name: credit-card-feature-fit-advisor
description: Recommend a credit-card option when a customer states mandatory features (such as no foreign transaction fee, purchase protection, and a potential credit limit) and optional spending preferences. Use for informational product comparison only; do not use for account changes, applications, or other banking actions.
---

# Credit Card Feature-Fit Advisor

Use this Skill to give a precise, evidence-based card recommendation from the packaged product facts or from explicitly supplied offer data.

## Scope and safety

This is a product-information workflow, not a banking transaction. Do not access customer accounts, make applications, alter cards, or represent that a customer will receive a particular credit line. A published maximum or typical range establishes only the *possibility* of a limit, subject to approval.

Do not treat a conditional benefit as unconditional. For example, a 0% foreign-transaction fee that requires a subscription does not meet a request for no foreign-transaction fees unless the customer explicitly says they have or will obtain that subscription and its terms are known.

## Workflow

1. Extract the customer's hard requirements and preferences. Keep these distinct:
   - Hard requirements: stated must-haves, such as a 0% foreign-transaction fee, purchase protection, or a minimum possible credit limit.
   - Preferences: spending pattern or rewards preference, such as travel-heavy spending.
2. Review `references/card_catalog.json`. Cite the source document IDs recorded there; do not invent benefits not shown in the catalog.
3. For a repeatable comparison, run `scripts/evaluate_offers.py` with the request and candidate offers. The script accepts only explicitly represented facts and flags conditional benefits.
4. Recommend the strongest candidate that satisfies every hard requirement. Explain the specific facts that establish the fit and how the rewards structure relates to the stated spending pattern.
5. If no candidate fully qualifies, say so plainly and identify the closest alternatives and the unmet condition. Ask a focused follow-up only when a stated condition is ambiguous or a conditional benefit may be acceptable.
6. State material caveats relevant to the recommendation (for example, annual fee, approval-dependent limits, or eligibility and policy terms for purchase protection). Do not claim that a rebate, protection claim, or credit line is guaranteed.

## Current packaged product comparison

For the catalog supplied with this Skill, the Platinum Rewards Card is the direct fit when a customer requires all of: an unconditional 0% foreign-transaction fee, purchase protection, and a possible limit of at least $100,000. Its flat rewards rate applies to travel as well as other purchase categories. Include the documented annual fee and explain that its annual-fee rebate has a separate $7,500 monthly-spend condition; do not assume the condition is met.

The Silver Rewards Card's 0% foreign-transaction fee is conditional on a premium subscription. Its published maximum possible initial limit is $100,000 and its purchase protection is lower than the Platinum card's. It may be discussed as a conditional alternative, not as the unconditional match.

## Response template

Use a short customer-facing answer structured like this:

- **Recommendation:** card name and a direct fit/no-fit statement.
- **Why it fits:** each hard requirement with its published value, then the spending-pattern reason.
- **Important consideration:** approval uncertainty plus any material fee or threshold.
- **Comparison if useful:** why a near match is conditional or falls short.

Cite supporting catalog document IDs in parentheses, e.g. `(Source: doc_...)`. Do not mention internal scripts or this Skill to the customer.

## Optional comparison script

`scripts/evaluate_offers.py` reads one JSON object from stdin and writes one JSON object to stdout.

Input schema:

```json
{
  "requirements": {
    "require_zero_foreign_transaction_fee": true,
    "require_purchase_protection": true,
    "minimum_possible_credit_limit": 100000,
    "spending_focus": "travel"
  },
  "offers": [
    {
      "name": "Card name",
      "max_possible_credit_limit": 100000,
      "foreign_transaction_fee_percent": 0,
      "foreign_transaction_fee_conditions": null,
      "purchase_protection_days": 90,
      "purchase_protection_max_per_claim": 3000,
      "rewards": {"type": "flat", "rate_percent": 1.0, "applies_to": ["all purchases"]},
      "annual_fee": 0,
      "sources": ["document_id"]
    }
  ]
}
```

`foreign_transaction_fee_conditions` must be `null` only when the stated fee applies without an extra prerequisite. A nonempty string makes the benefit conditional. The output contains `fully_qualifying_offers`, `conditional_or_partial_offers`, and per-offer reasons. Validate that the selected recommendation appears in `fully_qualifying_offers` before describing it as a full match. If required fields are absent, the script returns an `errors` array; obtain the missing product facts rather than guessing.
