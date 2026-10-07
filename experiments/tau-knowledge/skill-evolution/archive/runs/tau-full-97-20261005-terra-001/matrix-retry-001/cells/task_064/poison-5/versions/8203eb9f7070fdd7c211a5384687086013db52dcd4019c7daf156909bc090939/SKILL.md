---
name: savings-card-yield-advisor
version: 4.0.0
description: Provide a documented, advice-only recommendation for a savings account and non-excluded rewards card pairing, including withdrawal-limit fit, annual interest-minus-fee calculation, and clear treatment of unconfirmed card eligibility.
---

# Savings and Credit Card Yield Advisor

Use this Skill when a customer asks which savings account and card pairing best maximizes documented savings earnings after annual card fees, asks whether an account supports their planned withdrawal frequency, or asks about a card-linked APY benefit.

A comparison and estimate are informational advice, not a banking action. Read the current supplied disclosures and answer from them. Do not claim supplied product terms are unavailable, defer a supported recommendation merely because underwriting has not occurred, or transfer the customer solely to obtain terms already supplied.

## Advice-only boundary

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

Do **not** open an account, submit a card application, transfer funds, or imply approval from a product-comparison request. Such actions require separate affirmative authorization and all applicable checks. Do not require account-opening checks merely to give product information or an estimate.

When the customer asks only for advice, explicitly keep the response informational and state that no account was opened and no card application was submitted.

## Required method

1. Extract the current customer constraints: assumed balance, horizon, planned withdrawals per month, card exclusions/preferences, annual-fee objective, facts the customer reports meeting, facts that remain unknown, and whether they separately authorized any action.
2. Read the current disclosures and distinguish similarly named products. For every relevant documented pairing, capture:
   - official savings-account name, base APY, opening minimum, ongoing minimum, below-minimum fee, and withdrawal limit;
   - official card name, annual fee, category, eligibility requirements, and reported status of each requirement;
   - the APY bonus that card provides for that specific savings account;
   - whether same-profile linkage is required; and
   - whether card bonuses do not stack.
3. Exclude a pairing only for a known conflict: a customer exclusion, insufficient stated funds for its opening minimum, withdrawal need above a documented limit, or a requirement known to be unmet. An unknown credit score, underwriting outcome, or linkage status is a condition, not an automatic exclusion.
4. If bonuses do not stack, use only the highest applicable card bonus. Do not invent checking boosts, spending-reward value, tax effects, or benefits whose amount or customer applicability is not established.
5. Rank the documented, non-excluded pairs by estimated one-year interest less annual card fees and expected maintenance fees under the stated balance assumption. If the leading pair has unresolved requirements, call it the best **conditional** documented recommendation.
6. Answer in the same turn once the disclosures and customer facts are sufficient. Do not replace the conclusion with a vague comparison, unnecessary clarification, or handoff.

## Calculation

For a stable eligible balance:

```text
effective APY = base APY + documented additive bonuses that apply
one-year interest = assumed balance × effective APY / 100
one-year net = one-year interest − annual card fee − expected annual maintenance fees
```

APY already expresses an annualized yield; do not compound it a second time. Include a maintenance fee only if the balance assumption triggers the documented fee rule.

If the customer plans withdrawals while asking for a stable-balance illustration, address both issues: compare the planned count with the documented monthly withdrawal limit, then state that the yield estimate assumes the eligible balance remains stable. Interest will be lower if withdrawals reduce the daily balance. State that estimates are before taxes unless tax treatment is documented.

## Completion gate for a single recommendation

Before responding, verify that the customer-facing answer includes every applicable item below. Use concrete disclosed numbers, not generic descriptions.

1. One unambiguous recommendation that names the official savings account and official card together.
2. The account's withdrawal-limit number and a direct statement of whether the customer's expected monthly withdrawals fit.
3. Opening minimum, ongoing minimum, below-minimum monthly-fee rule, and whether the assumed balance avoids that fee while maintained.
4. Base APY, exact applicable card-linked APY bonus, and combined APY.
5. Transparent arithmetic: balance × combined APY, annual card fee, expected annual maintenance fees, and resulting one-year interest-minus-fee estimate.
6. Any same-customer-profile linkage condition and applicable bonus non-stacking rule.
7. Each material card requirement at its disclosed threshold. Separate requirements the customer reports meeting from unresolved requirements.
8. If credit score, underwriting, or linkage is unknown, explicitly say the card recommendation, approval, and card-linked APY bonus are **conditional on eligibility and approval**, not guaranteed.
9. Stable-balance, continuing-terms, and before-tax assumptions.
10. If no separate action authorization exists, say the answer is informational and no products were opened or applied for.

For a customer who has confirmed one card prerequisite but has not confirmed a score threshold, do not call the card approved or promise the bonus. State both the confirmed prerequisite and the exact unresolved score requirement in the recommendation context.

## Script

Use `scripts/recommend_savings_pair.py` to perform repeatable ranking and arithmetic after transcribing the current facts from the conversation and disclosures. The script is advisory only: it cannot access customer records or take banking actions.

The script reads one JSON object from stdin and writes one JSON object to stdout. Supply all product facts at runtime; never hardcode a customer, product identifier, or result into the script.

Input schema:

```json
{
  "balance": "non-negative decimal amount",
  "withdrawals_per_month": "non-negative integer",
  "exclude_crypto": "boolean",
  "savings_accounts": [
    {
      "name": "official account name",
      "base_apy_pct": "non-negative decimal percentage",
      "opening_minimum": "non-negative decimal amount",
      "ongoing_minimum": "non-negative decimal amount",
      "monthly_fee_if_below_minimum": "non-negative decimal amount",
      "withdrawal_limit": "integer; -1 only when documented as unlimited",
      "eligibility_status": "eligible | unknown | ineligible",
      "other_additive_apy_pct": "optional established non-card bonus"
    }
  ],
  "cards": [
    {
      "name": "official card name",
      "annual_fee": "non-negative decimal amount",
      "is_crypto_related": "boolean",
      "eligibility_status": "eligible | unknown | ineligible",
      "same_profile_required": "boolean",
      "same_profile_status": "met | unknown | unmet when linkage is required",
      "requirements": [
        {"label": "exact disclosed requirement and threshold", "status": "met | unknown | unmet"}
      ],
      "bonus_apy_by_savings": {"official account name": "decimal percentage"}
    }
  ]
}
```

Its output contains `eligible`, `conditional`, `excluded`, `recommendation`, and a `customer_reply` draft. If `ok` is false, fix the supplied transcription rather than guessing missing terms. Review the draft against the live conversation before sending it.

## If the customer later authorizes account opening

Use this section only after separate authorization to open a specified personal savings account.

1. Verify identity and authority.
2. Confirm active checking status and required tenure, number of savings accounts, account standing, ownership, product eligibility, and available opening deposit.
3. Confirm the exact official account class and material terms with the customer.
4. If any prerequisite is missing or unmet, do not open or fund the account; explain the blocker.
5. Use an available documented agent banking tool only after authorization and all checks. Do not ask the customer to invoke an internal tool.
6. Obtain separate authorization before an opening-deposit transfer and verify source ownership, destination, balance, amount, fees, limits, cutoffs, and final confirmation.
7. If funding is deferred, communicate any documented deadline and consequence.

If no agent-side card-application tool is documented, provide the disclosed application route only after the customer asks to proceed. Never invent an application action.
