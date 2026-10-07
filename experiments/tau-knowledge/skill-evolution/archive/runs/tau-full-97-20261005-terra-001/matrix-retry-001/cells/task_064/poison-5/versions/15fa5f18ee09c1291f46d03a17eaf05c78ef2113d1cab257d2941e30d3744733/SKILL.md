---
name: savings-card-yield-advisor
version: 2.0.0
description: Recommend one documented savings-account and non-crypto rewards-card pairing for a stated balance and withdrawal need, calculate one-year interest minus annual fees, and clearly distinguish documented fit from conditional card eligibility.
---

# Savings and Credit Card Yield Advisor

Use this Skill when a customer asks which savings account and credit card pairing maximizes one-year savings interest minus annual card fees, asks whether a savings account supports a planned withdrawal pattern, or asks about a card-linked APY bonus.

Use the supplied current product disclosures and the established conversation facts. A product comparison is advice, not a banking action. Do **not** say disclosures are unavailable, defer the recommendation, or transfer the customer merely because underwriting or an opening prerequisite has not been established. Unknown eligibility makes a recommendation conditional; it does not prevent a documented comparison.

## Banking-action boundary

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

A comparison, calculation, or product recommendation does not itself open an account, apply for a card, transfer funds, or establish approval. A separate affirmative customer authorization is required for each of those actions.

When the customer asks for information, a comparison, details before proceeding, or advice only:

- provide the requested recommendation in the same response when disclosures support it;
- do not open an account, submit a card application, transfer funds, or hand off solely because an eligibility item is unknown; and
- say that no savings account was opened and no card application was submitted if the customer has not separately authorized either action.

## Decision method

1. Extract the balance, horizon, maximum expected withdrawals per month, requested card style, exclusions, and whether the customer authorized action or only requested advice.
2. Read terms from documents for the exact savings account and card names. Do not mix similarly named account benefits or infer a missing rate, fee, boost, or qualification rule.
3. For each supported pairing, capture: base APY; documented additive card APY bonus for that exact savings account; annual card fee; opening and ongoing minimums; below-minimum fee; withdrawal limit; same-profile condition; and all disclosed eligibility conditions.
4. Exclude a pairing only for a known material failure: a customer exclusion, insufficient opening funds, a withdrawal limit below the stated need, or a documented requirement known to be unmet. Treat an unknown score, underwriting result, same-profile status, or opening eligibility as a condition, not an exclusion.
5. If card-bonus policy says card bonuses do not stack, apply only the highest applicable documented card bonus. Do not infer a checking-account boost unless its exact percentage and conditions are documented and established.
6. Rank suitable pairings by documented annual interest less annual card fees and expected documented maintenance fees. If no fully established pairing exists, give the highest-value conditional pairing and name every unresolved material condition.
7. Do not estimate cash-back dollars without documented qualifying spending. Do not invent taxes, opening fees, transfer costs, approval results, or relationship boosts.

## Calculation

For a stable eligible balance, use:

```text
effective APY = base APY + applicable documented additive APY bonuses
one-year interest estimate = balance × effective APY / 100
one-year net estimate = one-year interest estimate − annual card fee − expected annual maintenance fees
```

APY is already annualized; do not compound it again. Include a maintenance fee only when the assumed balance triggers the documented fee. If the customer expects withdrawals while the calculation assumes a stable balance, explain that the estimate assumes the balance remains eligible and stable; interest will be lower to the extent withdrawals reduce the daily balance. State that the estimate is before taxes unless tax treatment is documented.

Use `scripts/recommend_savings_pair.py` for repeatable validation, calculation, and ranking after transcribing the applicable disclosures into its input schema. The script is advisory only and cannot take a banking action.

## Required customer-facing answer

For a request for **one best combination**, give one direct recommendation, not a vague ranking, refusal, or handoff. Include these points together:

1. “My single recommendation is [official savings-account name] paired with [official permitted card name].”
2. The documented withdrawal limit and an explicit statement whether it accommodates the stated number of withdrawals.
3. Opening and ongoing minimums when relevant, the below-minimum fee rule, and whether the assumed balance avoids that fee while maintained.
4. Base APY, exact card-linked APY bonus, and resulting effective APY.
5. Transparent arithmetic: balance × effective APY; annual card fee; expected annual maintenance fees; and the one-year interest-minus-fee estimate.
6. Any same-customer-profile requirement for the bonus.
7. Each material unknown requirement using its actual disclosed threshold. For example, when a card has a disclosed minimum credit score and the customer does not know their score, name that threshold and state that card approval and the linked APY bonus are conditional, not guaranteed.
8. Requirements the customer reports meeting, clearly separated from unverified facts and underwriting approval.
9. The stable-balance, continuing-terms, and before-tax assumptions.
10. If action was not separately authorized, state that no account was opened and no card application was submitted.

Before responding, check that the answer contains official product names, a withdrawal number, APY components, annual-fee figure, net estimate, and specific conditional eligibility wording. Never replace these required facts with a claim that product terms cannot be accessed.

## Script interface

Run `scripts/recommend_savings_pair.py` with exactly one JSON object on stdin; it emits exactly one JSON object on stdout.

```json
{
  "balance": "decimal amount",
  "withdrawals_per_month": "non-negative integer",
  "exclude_crypto": "boolean",
  "savings_accounts": [
    {
      "name": "official savings-account name",
      "base_apy_pct": "decimal percentage points",
      "opening_minimum": "decimal amount",
      "ongoing_minimum": "decimal amount",
      "monthly_fee_if_below_minimum": "decimal amount",
      "withdrawal_limit": "non-negative integer, or -1 only if documented unlimited",
      "eligibility_status": "eligible | unknown | ineligible",
      "other_additive_apy_pct": "optional decimal percentage points"
    }
  ],
  "cards": [
    {
      "name": "official card name",
      "annual_fee": "decimal amount",
      "is_crypto_related": "boolean",
      "eligibility_status": "eligible | unknown | ineligible",
      "same_profile_required": "boolean",
      "same_profile_status": "met | unknown | unmet when required",
      "requirements": [
        {"label": "exact documented requirement and threshold", "status": "met | unknown | unmet"}
      ],
      "bonus_apy_by_savings": {
        "official savings-account name": "decimal percentage points"
      }
    }
  ]
}
```

For a runnable call, send the disclosure transcription JSON object above to the script using the runtime's packaged-script runner with `relative_path` set to `scripts/recommend_savings_pair.py`. Inspect `ok`: if false, correct missing or malformed transcription from the supplied disclosures rather than guessing. If true, use `customer_reply` as a completeness aid, then ensure it accurately reflects the conversation and includes any customer-facing context required above.

`eligible` means no known unmet condition; `unknown` means the conversation or records have not established it; `ineligible` means a known failure. Requirement labels must retain actual thresholds from the source disclosure so the returned conditional wording is meaningful.

## Later account-opening workflow

Use this section only after the customer separately authorizes opening a personal savings account and confirms the exact official account class.

1. Verify identity and authority through the available process.
2. Confirm every applicable prerequisite: active checking relationship, required checking tenure, savings-account count, account standing, ownership, product eligibility, and opening-deposit availability.
3. Confirm the exact official account class and material terms with the customer.
4. If any prerequisite is unavailable or unmet, do not open or fund the account; explain the blocker.
5. Use a documented agent banking tool only after prerequisites and authorization are complete. Do not ask a customer to invoke an internal agent tool.
6. Obtain separate authorization before an opening-deposit transfer and verify source ownership, destination, available balance, amount, fees, limits, cutoffs, and final confirmation.
7. If funding is deferred, communicate any documented funding deadline and consequence.

If no agent-side card-application tool is documented, provide the disclosed application route only after the customer asks to proceed; never invent an application action.
