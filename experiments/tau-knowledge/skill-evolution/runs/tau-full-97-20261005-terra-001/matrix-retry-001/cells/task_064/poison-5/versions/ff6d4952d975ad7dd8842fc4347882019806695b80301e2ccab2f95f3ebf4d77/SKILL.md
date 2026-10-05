---
name: savings-card-yield-advisor
version: 1.6.0
description: Provide one documented savings-account and non-crypto rewards-card recommendation for a stated balance and withdrawal need, with transparent APY/fee arithmetic and conditional eligibility language.
---

# Savings and Credit Card Yield Advisor

Use this Skill when a customer asks which savings account and credit card combination best maximizes one-year savings interest minus annual card fees, asks whether a savings account supports a withdrawal pattern, or asks about a card-linked APY benefit.

Use the current product disclosures supplied in the task and facts established in the conversation. Supplied product disclosures are sufficient evidence for advice: do not claim that they are unavailable merely because an account-opening or card-underwriting result is unavailable.

This Skill gives advice only unless the customer separately and explicitly authorizes a banking action.

## Banking-action boundary

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

A disclosure-based comparison, estimate, or recommendation is not a banking action. Do not characterize advice as an account-opening approval, a credit approval, an underwriting decision, or confirmed product eligibility.

When the customer asks to compare products, requests details before proceeding, or requests advice only:

- answer the comparison and give the requested recommendation in the same response when documented terms permit it;
- do not open an account, submit a card application, transfer funds, or transfer the customer to another agent solely because a requirement is unknown; and
- state that no product was opened or application submitted if the customer has not separately authorized one.

A separate affirmative authorization is required for account opening, a card application, and each funds transfer.

## Advice-first method

1. Extract the customer’s balance, planning horizon, expected maximum withdrawals per month, product exclusions, stated preferences, and whether they asked to proceed or only to receive advice.
2. Read terms only from documents for the exact product names. Do not combine benefits from similarly named accounts or cards.
3. For every documented candidate pairing, identify its savings APY, card annual fee, withdrawal limit, opening and ongoing balance requirements, maintenance-fee rule, and exact card-to-savings APY bonus.
4. Exclude only a pairing that has a known material failure: an explicit customer exclusion, insufficient opening funds, a documented withdrawal limit below the need, or a known unmet requirement.
5. Keep the highest-value otherwise suitable pairing as a **conditional recommendation** when an important requirement is unknown. An unknown credit score, underwriting result, same-profile linkage, or opening eligibility does not justify withholding the one choice requested by the customer.
6. Apply a card APY bonus only where the exact savings-account/card pairing documents it. State any requirement that both products be under the same customer profile.
7. If multiple card bonuses could apply, use only the highest documented card bonus when the supplied policy says card bonuses do not stack. Do not infer an undocumented checking-account boost.
8. Select the highest documented interest-minus-annual-fee result among eligible candidates; if no candidate is fully established as eligible, select the highest documented conditional candidate and name its unresolved conditions.

Do not estimate card cash-back dollars without documented qualifying purchase volume. Do not invent taxes, opening fees, transfer costs, APY boosts, approval results, or eligibility facts.

## Calculation method

For a stable eligible balance, calculate:

```text
effective APY = base APY + documented applicable additive APY bonuses
one-year interest estimate = balance × effective APY / 100
one-year net estimate = one-year interest estimate − annual card fee − expected annual maintenance fees
```

APY is annualized, so do not compound an APY a second time. Include maintenance fees only if the assumed balance triggers the documented fee. If the customer expects withdrawals but the estimate assumes a stable balance, say so plainly: actual interest is lower to the extent withdrawals reduce the daily balance. State that the estimate is before taxes unless tax treatment is documented.

Use `scripts/recommend_savings_pair.py` for repeatable arithmetic and candidate ranking after transcribing the applicable current disclosures into its input schema. The script is advisory only and cannot take banking actions.

## Required customer-facing answer

For a request for one best combination, provide one direct answer rather than a vague ranking, handoff, or refusal. Include all of the following together:

1. A clear lead sentence: “My single recommendation is [official savings name] paired with [official permitted card name].”
2. The account’s withdrawal limit and an explicit comparison showing that it does or does not accommodate the stated number of monthly withdrawals.
3. The opening minimum and ongoing minimum when relevant, plus the exact below-minimum fee rule. Explain whether the assumed balance avoids that fee while maintained.
4. The base APY, the exact applicable card-linked APY bonus, and the resulting effective APY.
5. The arithmetic: assumed balance × effective APY; annual card fee; expected annual maintenance fees; and the resulting one-year interest-minus-fee estimate.
6. The condition that both products must be held on the same customer profile whenever that condition applies to the bonus.
7. All material eligibility uncertainty using the actual disclosed requirement and threshold. If a credit-score threshold is known but the customer does not know their score, state the threshold and say card approval and the linked APY bonus are conditional, not guaranteed.
8. Requirements the customer says they meet, distinguished from facts not verified and from underwriting approval.
9. Assumptions that the balance remains eligible and stable for the year, terms remain in effect, the result is before taxes, and daily-balance reductions lower interest.
10. If there is no separate authorization to proceed, state that no savings account was opened and no card application was submitted.

Before sending, check that the answer includes the official product names, withdrawal number, APY components, annual-fee figure, net estimate, and specific conditional language. Never replace these items with a statement that disclosures cannot be accessed or with an unnecessary transfer.

## Script interface

Run `scripts/recommend_savings_pair.py` with one JSON object on stdin. It emits one JSON object on stdout.

Input schema:

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
      "withdrawal_limit": "non-negative integer, or -1 only when documented as unlimited",
      "eligibility_status": "eligible | unknown | ineligible",
      "other_additive_apy_pct": "decimal percentage points, optional"
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
        {"label": "documented requirement and threshold", "status": "met | unknown | unmet"}
      ],
      "bonus_apy_by_savings": {
        "official savings-account name": "decimal percentage points"
      }
    }
  ]
}
```

`eligible` means no known unmet condition; `unknown` means the information is not established from the conversation or supplied records; `ineligible` means a known failure. The script returns ranked eligible and conditional candidates, exclusions with reasons, and a response-ready advisory message. If `ok` is false, correct missing or invalid disclosure transcription rather than guessing.

## Later opening workflow

Use this section only after the customer separately authorizes opening a personal savings account and confirms the exact official account class.

1. Verify identity and authority through the available process.
2. Verify every applicable opening prerequisite, including active checking relationship, required tenure, savings-account count, account standing, and required opening deposit.
3. Confirm the exact account class and material terms with the customer.
4. If a prerequisite is unavailable or unmet, do not open or fund the account; explain the blocker.
5. Use a documented agent banking tool only after prerequisites and authorization are complete. Never ask the customer to invoke an internal agent tool.
6. Obtain separate authorization before an opening-deposit transfer and verify source ownership, available balance, destination, amount, fees, limits, cutoffs, and final confirmation.
7. If funding is deferred, communicate any documented funding deadline and consequence.

If no agent-side card-application tool is documented, provide the disclosed application route only after the customer asks to proceed; do not invent an application action.
