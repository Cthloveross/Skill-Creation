---
name: savings-card-yield-comparison
version: 1.0.0
description: Compare eligible savings-account and credit-card combinations for a customer seeking the highest one-year savings yield. Use for product guidance before an application or account-opening action, especially when card bonuses, balance thresholds, annual fees, or non-stacking rules matter.
---

# Savings and card yield comparison

Use this Skill to give a transparent, suitability-neutral comparison of available combinations. It is designed for a customer who names a balance and wants to maximize savings earnings; it does not approve a card, open an account, or assume that undocumented eligibility requirements are met.

## Method

1. Extract the amount the customer expects to keep in savings for the year and whether it is expected to remain constant.
2. Identify each candidate combination from `references/product_rules.md` (or from product facts explicitly supplied at runtime).
3. Exclude or mark conditional any combination that fails an opening deposit, ongoing balance, account-rate threshold, card qualification, or required-subscription condition. Do not treat an account as eligible merely because its card APY bonus is attractive.
4. Apply the stacking rules:
   - Choose only the single highest applicable credit-card APY bonus; do not add card bonuses together.
   - A qualifying checking boost may stack with the selected card bonus, but only a documented qualifying checking/savings pairing receives one. Multiple checking boosts likewise use only the highest one.
   - Other independently documented relationship bonuses may stack only when their conditions are met.
5. For a constant balance, use APY as the annual yield: `projected_interest = balance × APY / 100`. Do **not** compound APY again; it already expresses an annual yield. Interest crediting frequency does not change this comparison.
6. Use `scripts/rank_options.py` for reproducible arithmetic when there are multiple candidates. Supply only candidates whose rate components and eligibility have been established. The script reports both gross savings interest and a separate figure after the candidate card's annual fee.
7. State the recommendation, its conditions, the APY arithmetic, projected one-year gross interest, and any material fee or application requirement. Distinguish “highest interest” from “best net result after disclosed card annual fees.” Do not invent the price of a subscription or an approval outcome.

## Customer-facing response rules

- Lead with the best eligible or clearly conditional combination, not a long product catalog.
- Explain why apparently higher-rate alternatives are unavailable at the stated balance or lack a documented benefit.
- Round projected dollar figures to cents. State that the projection assumes the balance remains constant for the full year and that the applicable APY remains in effect.
- Treat percentage bonuses as additive percentage points. Correct the arithmetic yourself if a product narrative contains an inconsistent illustrative total.
- If information required for the best option is unknown (for example, credit score, subscription status, or whether the card will be approved), phrase the recommendation conditionally and give the strongest documented alternative.
- Do not claim that the customer qualifies for, has applied for, or holds any product based only on a request for information.

## Product-opening and application handling

Advice does not itself authorize an action. After the customer selects a savings account and explicitly asks to open it:

1. Authenticate and verify identity according to the normal verification process. Log verification only after confirming two identity fields.
2. Check all documented savings-opening prerequisites: verified identity, an active checking account held for at least 14 days, fewer than five personal savings accounts, and no collections accounts or negative balances. Do not proceed if any checkpoint fails or cannot be confirmed.
3. Confirm the exact official savings account class and the customer’s authorization.
4. The documented internal savings-opening procedure uses `open_bank_account_4821` with `account_type: "savings"` and the full official account name ending in `Account`. Unlock and call that discoverable agent tool only after the prerequisites and selection are confirmed.
5. Ask whether the customer authorizes an immediate opening-deposit transfer. Only then use the documented transfer tool with the selected checking account, the newly created savings account, and the required opening-deposit amount. If the customer declines, disclose the documented 30-day funding deadline and closure consequence.
6. For a credit card, use only a normal card-application workflow or tool explicitly available in the current runtime. If none is available, explain the documented dashboard application route; do not fabricate a card-opening action.

## Calculator interface

Run `scripts/rank_options.py` with JSON on stdin.

Input schema:

```json
{
  "balance": "decimal dollar amount",
  "include_card_fees": true,
  "options": [
    {
      "label": "customer-facing combination name",
      "base_apy_percent": "decimal percentage",
      "card_bonus_percent": "decimal percentage",
      "checking_bonus_percent": "decimal percentage",
      "other_bonus_percent": "decimal percentage",
      "annual_card_fee": "decimal dollars",
      "eligible": true,
      "eligibility_notes": ["conditions checked or remaining"]
    }
  ]
}
```

All percentage fields are additive percentage points. Omitted bonus and fee fields default to zero. `eligible` means the account balance and known requirements support the candidate; unresolved card approval or subscription status should ordinarily be represented as `eligible: false` with a precise note, while the advisor can discuss it as a conditional option.

Output schema:

```json
{
  "balance": "0.00",
  "ranked_eligible": [
    {
      "label": "...",
      "total_apy_percent": "0.000",
      "projected_interest": "0.00",
      "annual_card_fee": "0.00",
      "net_after_annual_card_fee": "0.00",
      "eligibility_notes": []
    }
  ],
  "ineligible": [{"label": "...", "eligibility_notes": []}]
}
```

Validate that the stated balance is nonnegative, rates and fees are nonnegative decimals, labels are present, and every candidate contains an explicit boolean `eligible`. If validation fails, correct the product facts or missing eligibility information rather than relying on a partial ranking.

## Important limitation

This Skill compares known product terms; it cannot determine a credit decision, the cost of an unspecified subscription, future rate changes, taxes, spending rewards, or investment suitability. Escalate only through the normal policy if a separate issue requires it.
