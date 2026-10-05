---
name: savings-card-yield-advisor
version: 1.5.0
description: Recommend one documented savings-account and non-crypto rewards-card pairing for a stated balance and withdrawal need, with transparent APY/fee math and conditional eligibility language.
---

# Savings and Credit Card Yield Advisor

Use this Skill when a customer wants one best savings-account and credit-card combination based on one-year interest minus annual fees, asks whether an account supports a withdrawal pattern, or asks about a card-linked savings APY benefit.

Use current supplied disclosures and facts established in the conversation. This Skill provides advice only unless the customer separately and explicitly authorizes a banking action.

## Banking-action boundary

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

A disclosure-based comparison or recommendation is not a banking action. Do not represent advice as an account-opening approval, card approval, underwriting decision, or confirmed product eligibility.

If the customer asks for advice or asks to review details before proceeding:

- provide the recommendation; and
- do not open an account, submit a card application, transfer money, or transfer the customer to another agent merely because a requirement is unknown.

A separate affirmative authorization is required before each product-opening, application, or transfer action.

## Advice-first decision procedure

When the customer asks for one best combination and the supplied disclosures contain enough terms, answer in the same response. Do not claim that supplied disclosures are unavailable and do not substitute a vague ranking, referral, or transfer for the requested recommendation.

1. Extract the customer constraints: balance, horizon, maximum expected monthly withdrawals, stated product exclusions, and whether advice only was requested.
2. For each exact savings/card pairing, read only the disclosures for those exact product names. Do not merge terms from similarly named products.
3. Exclude a pairing only when a material constraint is known to fail: an explicit product exclusion, insufficient opening funds, a documented withdrawal limit below the stated need, or a known unmet requirement.
4. Retain a potentially better pairing as **conditional** when a requirement is unknown. Unknown credit score, underwriting outcome, same-profile linkage, or opening eligibility is not a reason to withhold a requested recommendation.
5. Apply a card APY bonus only when it is documented for the exact savings account and card. State any same-customer-profile condition.
6. Where card bonuses do not stack, use only the highest applicable card bonus. Do not infer an undocumented checking-account boost.
7. Select the highest documented net estimate among eligible candidates; if none are fully eligible, select the highest documented conditional candidate when the customer requested one choice.

Do not estimate cash-back dollars unless annual qualifying purchase volume is supplied. Do not invent taxes, transfer charges, fees, boosts, or eligibility facts absent from the disclosures.

## Calculation method

For a stable, eligible balance:

```text
effective APY = base APY + documented applicable additive APY bonuses
one-year interest estimate = balance × effective APY / 100
one-year net estimate = one-year interest estimate − annual card fee − expected annual maintenance fees
```

APY is already annualized; do not compound it a second time. Include annual maintenance fees only when the assumed balance triggers the disclosed fee. State that actual interest will be lower if withdrawals reduce the daily balance, and that the calculation is before taxes unless tax treatment is specifically documented.

Use `scripts/recommend_savings_pair.py` for repeatable ranking and arithmetic after transcribing the applicable current disclosures. The script is advisory only and cannot take banking actions.

## Required customer-facing response

For a one-choice request, the response must include all of the following plainly and together:

1. An unmistakable single recommendation naming one savings account and one permitted card.
2. The account's withdrawal limit and a direct comparison to the customer's stated monthly withdrawals.
3. The opening and ongoing balance requirements when relevant to the customer's stated balance, including the maintenance-fee consequence.
4. The base APY, exact card-linked bonus, and resulting effective APY.
5. Transparent arithmetic using the customer's balance, estimated one-year interest, card annual fee, expected maintenance fees, and resulting interest-minus-fee estimate.
6. The same-profile condition when the bonus requires both products on one customer profile.
7. Every material eligibility uncertainty. Name the actual disclosed threshold when known (for example, an unknown minimum credit-score threshold), and state that card approval and any linked bonus are conditional rather than guaranteed.
8. Requirements the customer says they meet, while distinguishing those statements from unverified requirements and underwriting approval.
9. Assumptions: the eligible balance stays stable for the year, stated rates and benefits remain in effect, the estimate is before taxes, and reducing the daily balance reduces interest.
10. If the customer requested advice only, a statement that no account was opened and no card application was submitted.

Before sending, ensure the response includes the official product names, the withdrawal number, all stated APY components and fee figures, the net estimate, and specific conditional language. Never replace this content with a transfer or a claim that product terms are inaccessible.

## Script interface

Run `scripts/recommend_savings_pair.py` with one JSON object on stdin. It writes one JSON object on stdout.

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
        {"label": "documented requirement", "status": "met | unknown | unmet"}
      ],
      "bonus_apy_by_savings": {
        "official savings-account name": "decimal percentage points"
      }
    }
  ]
}
```

`eligible` means no known unmet condition; `unknown` means not established from the conversation or available records; `ineligible` means known unmet. The output contains ranked eligible and conditional candidates, exclusions with reasons, and a response-ready advisory message. If `ok` is false, correct missing or invalid disclosure transcription rather than guessing.

## Later opening workflow

Use this section only after separate authorization to open a personal savings account and confirmation of the exact official account class.

1. Verify identity and authority through the available process.
2. Verify every disclosed account-opening prerequisite, including active checking relationship, tenure, savings-account count, account standing, and required opening deposit.
3. Confirm the exact account class and all relevant terms with the customer.
4. If a prerequisite is unavailable or unmet, do not open or fund the account; explain the blocker.
5. Use a documented agent banking tool only after all prerequisites and authorization are complete. Never ask the customer to invoke an internal agent tool.
6. Obtain separate authorization before an opening-deposit transfer and verify source ownership, available balance, destination, amount, fees, limits, cutoffs, and final confirmation.
7. If funding is deferred, communicate the documented funding deadline and consequence.

If no agent-side card-application tool is documented, provide the disclosed application route after the customer asks to proceed; do not invent an application action.
