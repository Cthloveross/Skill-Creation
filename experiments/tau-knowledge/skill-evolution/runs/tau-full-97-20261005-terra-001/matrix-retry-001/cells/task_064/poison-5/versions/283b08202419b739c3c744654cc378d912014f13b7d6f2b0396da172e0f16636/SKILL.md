---
name: savings-card-yield-advisor
version: 2.2.0
description: Give one documented savings-account and non-crypto rewards-card recommendation for a stated balance and withdrawal need, calculate one-year interest less annual fees, and distinguish known product fit from unresolved card eligibility.
---

# Savings and Credit Card Yield Advisor

Use this Skill when a customer asks which savings account and credit card combination will maximize documented yield after annual fees, asks whether an account accommodates a withdrawal pattern, or asks about a card-linked APY benefit.

A comparison, disclosure explanation, or projection is **advice**, not a banking action. Use the supplied product disclosures and facts established in the conversation. Do not claim that supplied disclosures are unavailable, transfer solely to obtain terms already supplied, or withhold a supported recommendation just because card approval is not yet known.

## Banking-action boundary

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

Do not open an account, submit a card application, transfer funds, or imply approval merely because a customer asks for a comparison, says they may want products, or asks to proceed later. Each action requires separate affirmative authorization and applicable checks.

For advice-only requests, provide documented information directly. Do not require identity verification, account-opening eligibility, or underwriting completion to explain products. Treat an unknown credit score, underwriting result, or linkage status as a stated condition, not a reason to decline to compare products.

## Recommendation workflow

1. Identify the requested objective and established facts: assumed balance, time horizon, planned monthly withdrawals, card exclusions, stated prerequisites, and whether the customer requested advice or authorized a specific action.
2. Read the supplied disclosures. Preserve exact official product names and keep similarly named accounts, their rates, and their account-specific card bonuses separate.
3. For each relevant pair, record the savings base APY; the card bonus applicable to that exact account; annual card fee; opening and ongoing balance requirements; below-minimum fee rule; withdrawal limit; profile-linkage condition; and card requirements.
4. Exclude a pair only for a known material conflict: it violates an express exclusion, the stated funds cannot satisfy the opening minimum, the withdrawal limit is below the stated need, or a required condition is known to be unmet. An unknown condition makes the recommendation conditional; it does not eliminate it.
5. If disclosures say card APY bonuses do not stack, use only the highest applicable card bonus. Do not add checking boosts, spending rewards, tax effects, or other benefits unless their exact amount and conditions are both documented and established for the customer.
6. Rank qualifying pairs by documented one-year interest less annual card fees and maintenance fees expected from the stated balance. If the leading pair is conditional, recommend it as the leading conditional choice and name the condition plainly.
7. Once the disclosures and customer facts are sufficient, answer in that turn. Do not ask an unnecessary follow-up or offer a handoff instead of the requested recommendation.

## Calculation rules

For an assumed stable eligible balance:

```text
effective APY = base APY + documented applicable additive APY bonuses
one-year interest estimate = balance × effective APY / 100
one-year net estimate = interest estimate − annual card fee − expected annual maintenance fees
```

APY is annualized; do not compound it a second time. Include a maintenance fee only if the assumed balance would trigger it. Do not estimate cash-back dollars without documented qualifying spending.

When a customer expects withdrawals but requests a stable-balance estimate, state both facts: whether the count fits the account limit, and that the illustration assumes the eligible balance stays stable. Explain that interest decreases to the extent withdrawals reduce the daily balance. State that estimates are before taxes unless tax treatment is documented.

Use `scripts/recommend_savings_pair.py` for deterministic ranking or arithmetic. Transcribe facts from the current disclosures and conversation into its input schema. The script is advisory only and cannot access customer systems or perform banking actions.

## Required customer-facing response for one best combination

When supplied disclosures support a comparison, give one direct recommendation—not a vague ranking, refusal, or handoff. The response must contain:

1. The official savings-account name and official permitted card name in one unambiguous recommendation.
2. The documented withdrawal-limit number and an explicit comparison with the customer's planned monthly withdrawals.
3. Relevant opening and ongoing minimums, the below-minimum fee rule, and whether the stated balance avoids that fee while maintained.
4. The base APY, exact applicable card-linked APY bonus, and resulting effective APY.
5. Transparent arithmetic: assumed balance × effective APY, annual card fee, expected annual maintenance fees, and estimated one-year interest-minus-fee result.
6. Any requirement that both products be held under the same customer profile for the bonus.
7. Each material card condition at its actual disclosed threshold. If a required credit score is unknown, state the threshold and explicitly say card approval and the linked APY bonus are conditional, not guaranteed.
8. Prerequisites the customer reports meeting, separated from unverified facts and underwriting outcomes.
9. Stable-balance, continuing-terms, and before-tax assumptions.
10. If no separate action authorization was given, say the response is informational and that no account was opened and no card application was submitted.

Before sending, verify that the actual response includes the product names, withdrawal-limit number, APY components, annual-fee amount, net estimate, and conditional eligibility language. Do not replace these facts with a statement that disclosures are unavailable.

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
      "other_additive_apy_pct": "optional documented and established bonus; defaults to 0"
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

The script returns `ok`, ranked `eligible` and `conditional` candidates, excluded candidates with reasons, a selected `recommendation`, and a `customer_reply` completeness draft. If `ok` is false, correct the disclosure transcription rather than guessing. Reconcile the draft with the current conversation, including all customer-specific conditions. Never use the script to initiate an action.

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
