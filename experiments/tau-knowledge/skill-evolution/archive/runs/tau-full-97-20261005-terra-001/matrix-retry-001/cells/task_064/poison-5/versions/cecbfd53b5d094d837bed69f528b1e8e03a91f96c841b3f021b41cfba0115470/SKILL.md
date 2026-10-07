---
name: savings-card-yield-advisor
version: 2.1.0
description: Provide one documented savings-account and non-crypto rewards-card recommendation for a stated balance and withdrawal need; calculate one-year interest less annual fees and clearly distinguish product fit from unresolved eligibility.
---

# Savings and Credit Card Yield Advisor

Use this Skill when a customer asks for the best savings-account and credit-card combination, whether a savings account supports a planned withdrawal pattern, or the value of a card-linked APY bonus.

A product comparison, term explanation, or estimate is **advice**, not a banking action. Use the supplied product disclosures and established conversation facts. Do not claim that supplied disclosures are unavailable, defer a supported recommendation merely because an approval condition is unknown, or transfer a customer solely to obtain terms already present in the disclosures.

## Banking-action boundary

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

Do not open an account, submit a card application, transfer funds, or imply approval based on a request for comparison or details. Each such action needs separate affirmative customer authorization and its applicable verification and eligibility checks.

For advice-only requests, answer the recommendation directly. Do not require identity verification, account-opening eligibility, or underwriting completion merely to provide documented product information. Treat an unknown credit score, underwriting outcome, or profile linkage as a clearly stated condition rather than a reason not to compare products.

## Recommendation method

1. Identify the requested objective and facts: assumed balance, time horizon, maximum monthly withdrawals, card preferences/exclusions, known product prerequisites, and whether the customer authorized an action or requested advice.
2. Read the disclosures for the exact product names. Keep similarly named accounts and account-specific bonuses separate. Do not infer missing APYs, fees, eligibility rules, checking boosts, cash-back dollars, taxes, or application outcomes.
3. For each candidate savings/card pair, record the savings base APY, card bonus applicable to that exact savings account, annual card fee, opening and ongoing balance requirements, below-minimum fee, withdrawal limit, same-profile condition, and stated card requirements.
4. Exclude only a pair with a known material conflict: it violates an express customer exclusion, the stated balance cannot meet its opening minimum, the withdrawal limit is below the stated need, or a documented condition is known to be unmet. An unknown condition is conditional, not an exclusion.
5. If card bonuses do not stack, use only the highest applicable documented card bonus. Do not add a checking boost unless its exact amount and conditions are both documented and established.
6. Rank remaining pairs by documented annual interest minus annual card fees and any maintenance fees that the stated balance is expected to trigger. If the leading pair has unresolved eligibility, give it as the leading **conditional** recommendation and identify every material unresolved condition.

## Calculation rules

For an assumed stable eligible balance:

```text
effective APY = base APY + documented applicable additive APY bonuses
one-year interest estimate = balance × effective APY / 100
one-year net estimate = interest estimate − annual card fee − expected annual maintenance fees
```

APY is annualized; do not compound it again. Include a maintenance fee only when the stated balance would trigger it. Do not estimate cash-back dollars without documented qualifying spending.

If the customer expects withdrawals but asks for a stable-balance projection, state both facts: the withdrawal count fits or does not fit the account limit, and the estimate assumes the eligible balance remains stable. Interest will be lower to the extent withdrawals reduce the daily balance. State that estimates are before taxes unless tax treatment is documented.

Use `scripts/recommend_savings_pair.py` when a deterministic ranking or arithmetic check is useful. Transcribe current disclosure facts into the input schema; the script is advisory only and cannot perform banking actions.

## Required customer-facing response for one best combination

When disclosures support a comparison, provide one direct recommendation, rather than a vague ranking, refusal, or handoff. Ensure the response includes all of the following:

1. The official savings-account name and official permitted card name in one unambiguous recommendation.
2. The documented withdrawal limit and an explicit comparison to the customer's planned withdrawals.
3. Relevant opening and ongoing minimums, the below-minimum fee rule, and whether the assumed balance avoids that fee while maintained.
4. The base APY, exact applicable card-linked bonus, and effective APY.
5. Transparent arithmetic: assumed balance × effective APY, annual card fee, expected annual maintenance fees, and estimated one-year interest-minus-fee result.
6. Any same-customer-profile requirement for the bonus.
7. Each material eligibility condition using its actual disclosed threshold. If a required credit score is unknown, explicitly state the score threshold and that card approval and the linked bonus are conditional, not guaranteed.
8. Requirements the customer says they meet, separated from unverified facts and underwriting results.
9. Stable-balance, continuing-terms, and before-tax assumptions.
10. If the customer did not separately authorize action, state that the response is informational and that no account was opened and no card application was submitted.

Before sending, confirm that the response actually contains product names, the withdrawal-limit number, APY components, annual-fee amount, net estimate, and explicit conditional eligibility language. Never substitute a claim of unavailable disclosures for these facts.

## Script interface

Run `scripts/recommend_savings_pair.py` with one JSON object on stdin and read one JSON object from stdout.

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
      "withdrawal_limit": "non-negative integer, or -1 only when documented unlimited",
      "eligibility_status": "eligible | unknown | ineligible",
      "other_additive_apy_pct": "optional documented, established bonus; defaults to 0"
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
        {"label": "exact documented requirement including any threshold", "status": "met | unknown | unmet"}
      ],
      "bonus_apy_by_savings": {
        "official savings-account name": "decimal percentage points"
      }
    }
  ]
}
```

The script returns `ok`, ranked `eligible` and `conditional` candidates, excluded candidates with reasons, and a `customer_reply` draft. If `ok` is false, correct the disclosure transcription rather than guessing. Treat the draft as a completeness aid: reconcile it with the actual conversation, disclose all material customer-specific conditions, and do not use it to initiate any action.

## Later account-opening workflow

Use this section only after the customer separately authorizes opening a specific personal savings account.

1. Verify identity and authority through the available process.
2. Confirm active checking status and any required tenure, savings-account count, account standing, ownership, product eligibility, and opening-deposit availability.
3. Confirm the exact official account class and material terms with the customer.
4. If any prerequisite is unavailable or unmet, do not open or fund the account; explain the blocker.
5. Use a documented agent banking tool only after prerequisites and authorization are complete. Do not ask the customer to invoke internal agent tools.
6. Obtain separate authorization before an opening-deposit transfer and verify source ownership, destination, available balance, amount, fees, limits, cutoffs, and final confirmation.
7. If funding is deferred, communicate any documented funding deadline and consequence.

If no agent-side card-application tool is documented, provide the documented application route only after the customer asks to proceed. Never invent an application action.
