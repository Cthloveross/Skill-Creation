---
name: apy-card-fee-break-even
version: 1.0.0
description: Evaluate whether an eligible credit card's APY boost is worth its annual fee for a savings balance, while applying non-stacking APY-bonus rules. Use for rate/fee recommendations before any account or card action.
---

# APY Card Fee Break-Even

Use this Skill when a customer asks whether a card with an APY bonus is worthwhile, which eligible card is best for a savings balance, or how a checking and card APY combination affects approximate annual earnings.

This Skill is informational. It does **not** open, close, link, transfer, or apply for any product.

## Banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For an informational comparison, do not imply eligibility is confirmed. If the customer later authorizes a product or account action, separately perform all applicable verification, eligibility, balance, account-status, pending-transaction, consent, and tool-specific checks before acting.

## Method

1. Obtain the savings balance and the product documentation for the applicable savings account, linked checking accounts, and cards.
2. Confirm the relevant base APY, checking boost, card bonus, annual fee, and eligibility conditions from current product documentation. Do not infer undisclosed rates or fees.
3. Select only the highest applicable checking boost; checking boosts do not stack with each other.
4. Select only the highest applicable card APY bonus; card bonuses do not stack with each other. A qualifying checking boost and the selected card bonus may be additive if product policy says they stack across categories.
5. Run `scripts/apy_fee_analysis.py` with each card that is eligible or conditionally eligible. Include `existing_card_bonus_pct` if the customer already has an active card bonus.
6. Explain that the calculation uses the stated APY as an approximate one-year yield on a constant balance. Actual interest can vary with balance changes, tier rules, eligibility, linking status, daily compounding, interest crediting, taxes, and product terms.
7. Recommend a card for rate purposes only when its incremental annual interest is greater than its annual fee. When it is not, state the annual shortfall and break-even balance. Mention non-rate benefits separately without treating them as savings interest.

## Script input and output

The script reads one JSON object from stdin and writes one JSON object to stdout.

### Input schema

```json
{
  "balance": "non-negative USD amount",
  "base_apy_pct": "base savings APY percentage",
  "checking_boosts": [
    {"name": "checking product", "apy_bonus_pct": "percentage", "eligible": true}
  ],
  "existing_card_bonus_pct": "optional percentage; defaults to 0",
  "card_options": [
    {
      "name": "card product",
      "apy_bonus_pct": "percentage",
      "annual_fee": "non-negative USD amount",
      "eligible": true
    }
  ]
}
```

`checking_boosts` and `card_options` may be omitted or empty. Entries marked `eligible: false` are excluded rather than recommended. Use only product values supported by the case evidence.

### Output highlights

- `baseline`: APY and approximate annual interest using the highest checking boost and current card benefit.
- `scenarios`: one no-new-card comparison plus each eligible candidate, including incremental annual interest, annual fee, net annual change, and break-even balance.
- `recommended_scenario`: the scenario with the greatest net annual result, preferring no new card in a tie.
- `validation_errors`: populated instead of a calculation result when required values are absent or invalid.

## Example invocation

```sh
python3 scripts/apy_fee_analysis.py <<'JSON'
{"balance":"6000","base_apy_pct":"4.0","checking_boosts":[{"name":"checking option","apy_bonus_pct":"0.55","eligible":true}],"card_options":[{"name":"card option","apy_bonus_pct":"0.5","annual_fee":"50","eligible":true}]}
JSON
```

Do not reuse the example values as case facts.

## Validation and response checks

Before relying on the result, ensure that the balance and all rates/fees are non-negative numeric values, the selected savings tier actually applies at that balance, and card/checking eligibility and linking requirements have been checked. Confirm the response distinguishes:

- total APY from the card's **incremental** APY;
- gross annual interest from the increase caused by the card; and
- a rate recommendation from authorization to apply for, open, link, close, or fund a product.

If eligibility, an APY tier, or a fee is unknown, say that the comparison is conditional and request or retrieve the missing current product term rather than presenting a definitive recommendation.
