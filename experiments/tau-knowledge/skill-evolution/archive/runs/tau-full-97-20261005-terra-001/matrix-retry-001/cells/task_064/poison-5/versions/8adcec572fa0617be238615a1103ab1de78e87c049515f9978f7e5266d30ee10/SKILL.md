---
name: savings-card-yield-advisor
version: 3.0.0
description: Compare disclosed savings-account and rewards-card pairings for a customer balance and withdrawal need, recommend one supported non-excluded combination, estimate one-year interest less annual fees, and clearly separate product fit from unconfirmed eligibility.
---

# Savings and Credit Card Yield Advisor

Use this Skill when a customer asks which savings account and credit card pairing best maximizes documented savings yield after annual card fees, asks whether a savings account supports a planned withdrawal frequency, or asks about a card-linked APY benefit.

A product comparison, disclosure explanation, or estimate is informational advice, not a banking action. Use the supplied product disclosures as the source of product terms. Do not claim that supplied disclosures are unavailable, transfer merely to obtain terms already supplied, or withhold a supported recommendation because underwriting has not occurred.

## Banking-action boundary

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

Do **not** open an account, submit a card application, transfer money, or imply approval based only on a comparison request or an interest in products. Each action requires separate affirmative customer authorization and all applicable checks. Do not require identity verification or account-opening eligibility merely to provide product information and an estimate.

## Comparison workflow

1. Collect only facts needed for the advice: balance assumption, time horizon, planned withdrawals per month, requested card type or exclusions, annual-fee objective, prerequisites the customer reports meeting, unresolved eligibility facts, and whether the customer actually authorized an action.
2. Read the current supplied disclosures. Keep exact official product names separate from similarly named products. For each relevant account/card pair, record:
   - savings base APY, opening minimum, ongoing minimum, below-minimum fee, and withdrawal limit;
   - card annual fee, card type, and card requirements;
   - the card APY bonus applicable to that *specific* savings account; and
   - same-customer-profile linkage and any non-stacking rule.
3. Exclude only pairings with a known conflict: an express customer exclusion, insufficient stated funds for the opening minimum, withdrawal need above the documented limit, or a requirement known to be unmet.
4. Treat unknown underwriting, credit score, or linkage status as a condition. Do not silently discard the strongest pairing just because it is conditional.
5. If a disclosure states that card bonuses do not stack, use only the highest applicable card bonus. Do not add rewards spending, checking boosts, tax effects, or other benefits unless their amount and applicability are both documented and established for this customer.
6. Rank viable pairs by documented one-year interest less annual card fees and maintenance fees expected under the stated balance assumption. If the best result is conditional, identify it as the best **conditional** recommendation.
7. When the product terms and customer facts are sufficient, answer in the same turn. Do not replace the recommendation with a vague comparison, an unnecessary question, or a handoff.

## Calculation method

For a stable, eligible balance, calculate:

```text
effective APY = base APY + applicable documented additive APY bonuses
one-year interest estimate = assumed balance × effective APY / 100
one-year net estimate = interest estimate − annual card fee − expected annual maintenance fees
```

APY is annualized; do not compound it a second time. Include a maintenance fee only when the assumed balance triggers it. Do not assign a dollar value to cash back or other purchase rewards without documented customer spending.

If the customer expects withdrawals but asks for a stable-balance projection, address both points: confirm whether the *number* of withdrawals fits the limit, and state that the yield illustration assumes the eligible balance remains stable. Explain that interest will be lower to the extent withdrawals reduce the daily balance. State that estimates are before taxes unless tax treatment is documented.

Use `scripts/recommend_savings_pair.py` for repeated arithmetic and ranking after transcribing facts from the current conversation and disclosures. The script is advisory only: it cannot access customer systems or take banking actions.

## Mandatory response contents

For a request for one best combination where disclosures support a recommendation, provide one direct customer-facing conclusion. Before sending, ensure the response explicitly includes all applicable items below:

1. The official savings-account name and official card name in one unambiguous recommendation.
2. The documented withdrawal-limit number and a direct comparison showing whether the customer's planned monthly withdrawals fit.
3. The opening minimum, ongoing minimum, below-minimum fee rule, and whether the assumed balance avoids that fee while maintained.
4. Base APY, exact card-linked APY bonus, and resulting effective APY.
5. Transparent arithmetic: balance × effective APY; annual card fee; expected annual maintenance fees; and the one-year interest-minus-fee estimate.
6. The same-profile linkage condition for the bonus, if disclosed.
7. Every material card requirement at its actual disclosed threshold. State reported prerequisites separately from unknown facts.
8. If a credit score or underwriting result is unknown, explicitly say that the card recommendation, approval, and linked APY bonus are **conditional on eligibility and approval**, not guaranteed.
9. Stable-balance, continuing-terms, and before-tax assumptions.
10. If no separate action authorization was given, state that the answer is informational and that no account was opened and no card application was submitted.

Use concrete disclosed numbers in the response rather than generic phrases such as “a high withdrawal limit,” “a strong rate,” or “standard eligibility.” Never say product disclosures are unavailable when they were supplied.

## Script interface

Run `scripts/recommend_savings_pair.py` with one JSON object on stdin. It emits one JSON object on stdout.

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
      "withdrawal_limit": "integer; -1 only if documented as unlimited",
      "eligibility_status": "eligible | unknown | ineligible",
      "other_additive_apy_pct": "optional established non-card bonus; defaults to 0"
    }
  ],
  "cards": [
    {
      "name": "official card name",
      "annual_fee": "decimal amount",
      "is_crypto_related": "boolean",
      "eligibility_status": "eligible | unknown | ineligible",
      "same_profile_required": "boolean",
      "same_profile_status": "met | unknown | unmet if required",
      "requirements": [
        {"label": "exact disclosed requirement and threshold", "status": "met | unknown | unmet"}
      ],
      "bonus_apy_by_savings": {
        "official savings-account name": "decimal percentage points"
      }
    }
  ]
}
```

The output contains `ok`, ranked `eligible` and `conditional` candidates, excluded candidates with reasons, a selected `recommendation`, and a customer-facing draft. If `ok` is false, correct the fact transcription; do not guess missing terms. Review the draft against the live conversation, especially customer-specific eligibility conditions, before responding.

## Later account-opening workflow

Use this section only after the customer separately authorizes opening a particular personal savings account.

1. Verify identity and authority using the available process.
2. Confirm active checking status and required tenure, current savings-account count, account standing, ownership, product eligibility, and opening-deposit availability.
3. Confirm the exact official account class and material terms with the customer.
4. If any prerequisite is missing or unmet, do not open or fund the account; explain the blocker.
5. Use an available documented agent banking tool only after authorization and all prerequisites are satisfied. Do not ask the customer to invoke an internal tool.
6. Obtain separate authorization before an opening-deposit transfer. Verify source ownership, destination, available balance, amount, fees, limits, cutoffs, and final confirmation.
7. If funding is deferred, communicate any documented funding deadline and consequence.

If no agent-side card-application tool is documented, give the disclosed application route only after the customer asks to proceed. Never invent an application action.
