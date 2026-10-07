---
name: savings-card-apy-combination-advisor
description: Compare a customer's feasible savings-account and credit-card combinations to maximize one-year interest, applying balance tiers, eligibility conditions, non-stacking card bonuses, and linked-checking boost rules. Use for informational product comparisons; not for opening accounts or making account changes.
---

# Savings and credit-card APY combination advisor

Use this Skill to give a transparent, conditional recommendation when a customer wants to pair a savings account with a credit card for the best savings yield.

## Scope and safety

This is an informational comparison only. Do not open an account, submit a credit-card application, change an account, or imply approval. Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

Do not request identity verification merely to provide general product information. If the customer chooses to apply, explain that the normal application flow will collect and verify required information and that approval is not guaranteed.

## Decision method

1. Extract the available opening balance, existing checking-account type(s), desired holding period, and any known eligibility facts (such as credit score and subscription status).
2. Determine savings-account feasibility using both opening and ongoing balance requirements. A product that cannot be opened or maintained at the stated balance is not an unconditional recommendation.
3. Determine the base APY for the applicable balance tier.
4. For each feasible savings account, identify credit cards that can provide a documented bonus. Multiple card bonuses do **not** stack: use only the single highest applicable bonus among cards the customer will actually hold and is eligible to obtain.
5. Check linked-checking boosts separately. Only documented checking/savings pairings qualify. Multiple qualifying checking boosts do not stack; use the highest one. A non-listed checking account contributes 0%, not an inferred boost.
6. Add the base APY, highest eligible credit-card bonus, and highest eligible checking boost. These bonus categories can stack with one another.
7. Estimate one-year interest as `balance * effective_apy / 100`. APY is already an annualized yield; do not compound the APY a second time. Clearly label this as an estimate and note that actual credited interest may vary with balances, timing, rate changes, and product terms.
8. Separate results into:
   - **confirmed feasible**: requirements supplied by the customer are met;
   - **conditional**: a potentially superior option depends on an unknown condition; and
   - **not feasible**: show the blocking requirement briefly.
9. State the best confirmed combination, the conditional higher-yield combination if applicable, annual-interest estimates, the difference in dollars, and the next fact needed to resolve any conditional result.

For calculation consistency, run `scripts/rank_options.py` and use its structured output. Do not represent a conditionally eligible option as confirmed.

## Packaged calculator

### Input

Run `scripts/rank_options.py` with JSON on standard input:

```json
{
  "balance": 8000,
  "checking_boost_percent": 0,
  "credit_score": null,
  "premium_subscription": null,
  "card_availability": {
    "Diamond Elite Card": "unknown"
  }
}
```

Fields:

- `balance` is a nonnegative dollar amount.
- `checking_boost_percent` is the highest *verified* linked-checking boost for the selected savings account. Use `0` when the customer's checking account is not a documented qualifying pairing. Do not guess this value.
- `credit_score` is a number or `null` if unknown.
- `premium_subscription` is `true`, `false`, or `null`.
- `card_availability` is optional. Its values are `eligible`, `ineligible`, or `unknown` and are used for cards whose eligibility is otherwise not documented in the supplied product facts.

The calculator contains the documented account and card data needed for the comparison. It emits JSON with `confirmed`, `conditional`, `infeasible`, and `data_notes` arrays. Each ranked option includes base APY, card bonus, checking boost, effective APY, and estimated annual interest. Dollar results are rounded only for display; ranking uses unrounded values.

### Example invocation

```sh
python3 scripts/rank_options.py <<'JSON'
{"balance":8000,"checking_boost_percent":0,"credit_score":null,"premium_subscription":null}
JSON
```

### Output validation

Before using the result, confirm that:

- `balance` is the customer's stated amount;
- any nonzero checking boost is supported by a documented matching pair;
- the same option does not contain more than one card bonus;
- effective APY equals base APY plus the displayed card and checking components;
- a confirmed result has no unmet opening, ongoing-balance, or known card-eligibility condition; and
- the recommendation distinguishes conditions that are unknown from conditions that fail.

## Customer-facing response pattern

Use plain language. Lead with the recommendation and dollar estimate, then show the arithmetic. Explain why the existing checking account does or does not add a boost. For an option dependent on score, subscription, approval, or missing facts, say exactly what is needed and give a confirmed alternative. Mention relevant application requirements and balance requirements, but do not make promises about approval or rates remaining unchanged.
