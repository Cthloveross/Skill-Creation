---
name: savings-card-first-year-value-and-opening
version: 1.0.0
description: Compare savings-account and credit-card combinations for estimated first-year net value, explain eligibility uncertainty, and safely open a selected personal savings account only after verified identity, eligibility, and explicit authorization. Use for customers seeking savings growth, card rewards, or both.
---

# Savings and Credit-Card Combination Evaluation

Use this Skill to distinguish a product recommendation from an account-opening request. It supports a documented estimate; it does not guarantee approval, APY, rewards, promotional eligibility, or future account performance.

## Safety control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Do not treat a supplied name, a prior lookup, or an assertion that the customer has an account as verified identity. Do not disclose profile fields while asking the customer to verify them. Have the customer confirm two of date of birth, email address, phone number, and street address; retrieve the profile through the normal authorized lookup; then obtain the current time and call `log_verification` with the complete retrieved profile and timestamp.

For an account opening or transfer, record the customer’s explicit authorization and exact requested product. A general request to compare products or “help me open accounts” is not authorization to create an account or move funds.

## 1. Gather current facts before comparing

1. Establish the planning inputs: amount intended for savings, expected monthly card spend, spending mix (especially any category-dependent rewards), whether funds will stay on deposit for the year, and willingness to meet account requirements.
2. Retrieve current, authoritative product terms for every candidate. Capture base APY and tiers, opening and ongoing balance rules, account fees, withdrawal or statement requirements, card annual fees, earning rates, approval prerequisites, and promotion windows.
3. Determine all applicable linked-checking and credit-card APY bonuses from the current product documentation. An unlisted checking/savings pairing has no linked-checking boost. Where multiple checking boosts or card bonuses could apply, use only the highest in each category; do not sum bonuses within either category. Add only bonuses that the applicable documentation says can stack.
4. Mark every requirement as `eligible`, `ineligible`, or `unknown`. Unknown credit score, subscription status, current offer applicability, product-link status, or account eligibility must remain unknown, not assumed favorable.
5. For the selected savings account, obtain authoritative account records before any opening action and verify all personal-savings opening requirements: verified identity, at least one active Rho-Bank checking account held at least 14 days, fewer than five personal savings accounts, and no accounts in collections or with negative balances. If any check fails or cannot be verified, do not open the account.

If the available runtime lacks an authorized way to inspect a required account-status fact, explain that the opening cannot yet be completed; do not infer the fact from the customer’s statement.

## 2. Estimate and recommend

Build one candidate for each plausible savings/card combination. A card is optional in the comparison: if a customer’s stated goal is maximizing net value, do not recommend a card merely because they initially asked for one.

Use `scripts/compare_combinations.py` to calculate a consistent estimate. Supply current product facts at runtime rather than embedding stale values in the request or changing the script.

The estimate for a candidate is:

- estimated savings interest = planned balance × effective combined APY;
- estimated card rewards = annual card spending × documented blended reward rate;
- estimated first-year net = interest + rewards + verified one-time value − known annual account and card fees.

APY already expresses an annualized yield. Do not compound an APY a second time in the estimate. For tiered accounts, choose the documented tier for the planned balance; if projected balance movement changes tiers, calculate separate periods or clearly label the simpler estimate.

Do not include conditional sign-up bonuses, category bonuses, or waived fees unless the customer is eligible and the required spend, timing, and other conditions are explicitly reflected in the candidate input. Do not treat a credit-card application as approved based on a comparison.

Present:

- the recommended eligible combination and its assumptions;
- the best potential but currently unconfirmed option, if it could outrank the recommendation;
- material fees, balance requirements, approval/subscription conditions, and reasons an option was excluded;
- that the estimate assumes the supplied balance and spending remain as modeled.

If the customer wants a credit card but no supplied agent tool can submit card applications, direct them to the documented online/dashboard application process after explaining its requirements. Do not use the savings-opening tool for a credit-card application and do not invent a card-opening tool.

### Comparator script interface

`compare_combinations.py` reads one JSON object from stdin and emits one JSON object to stdout.

Input schema:

```json
{
  "balance": "decimal dollars",
  "monthly_card_spend": "decimal dollars",
  "candidates": [
    {
      "name": "display name",
      "eligibility": "eligible | unknown | ineligible",
      "eligibility_notes": ["requirement or uncertainty"],
      "savings": {
        "base_apy_percent": "decimal percentage",
        "checking_apy_boosts_percent": ["decimal percentage"],
        "credit_card_apy_bonuses_percent": ["decimal percentage"],
        "additive_apy_bonuses_percent": ["decimal percentage"],
        "annual_fee": "decimal dollars",
        "opening_deposit_min": "decimal dollars",
        "ongoing_balance_min": "decimal dollars"
      },
      "card": {
        "annual_fee": "decimal dollars",
        "blended_rewards_rate_percent": "decimal percentage",
        "first_year_bonus_value": "decimal dollars"
      },
      "additional_annual_fees": "decimal dollars"
    }
  ]
}
```

All card fields are optional when a candidate has no card. The script rejects malformed numbers, invalid eligibility values, negative fees/balances, and non-list bonus fields. It selects the highest checking boost and the highest card APY bonus, then adds only the explicitly supplied additive bonuses.

Invoke it through the runtime as `run_skill_script` with `relative_path` set to `scripts/compare_combinations.py` and an `input_json` object conforming to the schema. Review that `ok` is true, candidate eligibility is accurate, opening funding is sufficient, and all conditional values used in the model were verified before relying on its ranking.

## 3. Open a chosen personal savings account only after authorization

After the customer chooses an eligible savings product and explicitly asks to open it:

1. Complete and log identity verification as described in the safety control.
2. Verify authority and ownership, product eligibility, active checking account and tenure, existing personal-savings count, good standing of all accounts, selected account requirements, applicable fees and limits, source available balance, and all confirmation requirements.
3. Confirm the exact official `account_class` name with the customer. It must be the full official name ending in `Account`. Confirm `account_type` is `savings` and that the required opening deposit can be funded.
4. If and only if every prerequisite passes, unlock `open_bank_account_4821` and call it with the authenticated `user_id`, `account_type: "savings"`, and the exact confirmed `account_class`.
5. Preserve the returned new account identifier and details. If opening fails or does not return an identifiable destination account, do not attempt a transfer; report the failure through the supported channel.
6. Ask whether the customer authorizes an immediate opening-deposit transfer from a specified owned checking account. Confirm source account, new savings destination, exact required amount, available balance, transfer fees, limits, cutoffs, and final confirmation.
7. Only with affirmative transfer authorization, unlock and call `transfer_funds_between_bank_accounts_7291` using the confirmed source account ID, newly opened destination account ID, and amount. Report the resulting funding status.
8. If the customer declines immediate funding, state that the account must be funded within 30 days by internal transfer or external deposit or it will be closed. Confirm the new account details and this funding deadline.

Never open an account when the customer has five personal savings accounts, a checking account held fewer than 14 days, any collection status or negative balance, or an unverified eligibility item. State the unmet condition and, where applicable, when the customer may become eligible.

## 4. Completion response

For a recommendation-only interaction, provide the comparison, assumptions, and next decision needed. For an opened account, provide the official account class, returned account details, funding result or 30-day deadline, and any remaining card-application step. Never claim a credit card was opened, approved, linked, or bonus-qualified unless an authorized tool or authoritative account record confirms it.
