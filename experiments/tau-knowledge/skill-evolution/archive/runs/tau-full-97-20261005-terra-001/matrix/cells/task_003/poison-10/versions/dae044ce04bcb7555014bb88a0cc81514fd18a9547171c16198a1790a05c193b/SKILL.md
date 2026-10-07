---
name: premium-credit-card-recommendation
description: Compare the packaged credit-card products against a customer's stated card-selection requirements, including potential credit limit, foreign transaction fee, purchase protection, rewards, fees, and stated eligibility conditions. Use for informational recommendations only; it does not apply for, open, alter, or service an account.
---

# Premium Credit Card Recommendation

## Scope and assumptions

Use this Skill when a customer wants help selecting among the packaged card products. It evaluates published product features, not an individual's underwriting result. A product whose published limit range reaches the requested amount only makes that amount *possible*; it never guarantees approval or an assigned limit.

The product catalog is in `references/card_catalog.json`. Its figures and eligibility notes are limited to the source documents packaged with this Skill. Do not invent category multipliers, approval odds, coverage exclusions, or promotional eligibility beyond that catalog.

This is an informational workflow. Do not access customer accounts, change profile data, submit an application, or make any other banking action merely to recommend a card. If a later request seeks a banking action, stop the recommendation workflow and follow the applicable execution agent's banking controls and confirmation requirements before acting.

## Workflow

1. Identify the customer's hard requirements separately from preferences.
   - Typical hard requirements: minimum possible credit limit, maximum foreign transaction fee, and whether purchase protection is required.
   - Typical preferences: everyday rewards, travel use, annual fee tolerance, protection duration/cap, and access to a membership or invitation.
2. Run `scripts/recommend_cards.py` with the requirements and any facts the customer has voluntarily supplied. Missing eligibility facts are treated as unknown, not as approval.
3. Use `feature_matches` to identify cards that meet all published hard product features. Read each card's `eligibility` and `eligibility_assessment` before describing it as a viable choice.
4. Lead with the script's `recommended` card only as a **best published feature match, subject to eligibility and underwriting**. State why it fits the stated priorities, then provide meaningful alternatives.
5. Explicitly state the requested limit caveat, applicable annual fee, and any material access condition (such as invitation-only status or a required subscription). State that purchase protection remains subject to its policy terms and exclusions.
6. If no catalog product meets all hard requirements, say so clearly and identify which feature(s) caused exclusion. Do not weaken a stated requirement without the customer's permission.

## Script interface

`scripts/recommend_cards.py` reads one JSON object from standard input and emits one JSON object to standard output. It uses only the packaged catalog.

Input schema:

```json
{
  "requirements": {
    "min_credit_limit": 100000,
    "foreign_transaction_fee_percent_max": 0,
    "purchase_protection_required": true
  },
  "preferences": {
    "prioritize_everyday_rewards": true,
    "primary_spend": "travel",
    "credit_score": null
  },
  "access": {
    "diamond_elite_invitation": null,
    "rho_bank_plus_subscription": null
  }
}
```

All fields are optional. Use JSON `null` or omit an unknown fact. `credit_score` must be numeric when supplied; the two access fields must be `true`, `false`, or `null` when supplied. A supplied `false` means the prerequisite is known not to be present; it is not the same as unknown.

Output schema (abbreviated):

```json
{
  "status": "ok",
  "feature_matches": [{"card": "...", "eligibility_assessment": {"known_blockers": [], "unknown_or_needed_conditions": []}}],
  "excluded_by_product_features": [{"card": "...", "reasons": ["..."]}],
  "recommended": {"card": "..."}
}
```

`recommended` is omitted when no product feature match remains. The rank prioritizes a higher published flat eligible-purchase cash-back rate when `prioritize_everyday_rewards` is true, then a lower annual fee. It is not a statement that travel spending earns a special category bonus.

Example runtime call:

```json
{
  "relative_path": "scripts/recommend_cards.py",
  "input_json": {
    "requirements": {"min_credit_limit": 100000, "foreign_transaction_fee_percent_max": 0, "purchase_protection_required": true},
    "preferences": {"prioritize_everyday_rewards": true, "primary_spend": "travel"},
    "access": {}
  }
}
```

## Output validation and response quality

Before responding, verify that every recommended card appears in `feature_matches`, that every stated hard requirement is reflected in the output's `requirements`, and that no `known_blockers` are omitted from the explanation. For each card mentioned, use the catalog's exact fee, limit range, rewards rate, and protection term/cap. If eligibility information is unknown, use conditional wording rather than asserting qualification.

For a customer seeking everyday rewards with travel as their main spend, do not assume that low non-travel spending makes a card ineligible. Compare the published flat rewards rate, foreign transaction fee, protection, possible limit range, annual fee, and stated access requirements instead.
