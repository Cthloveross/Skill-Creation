---
name: savings-card-net-yield-advisor
description: Compare a proposed savings account and credit-card combination by annual savings interest less annual card fees. Use when a customer wants a recommendation based on a deposit amount, APY tiers, account/card eligibility, linked-account boosts, and card APY bonuses.
---

# Savings and Card Net-Yield Advisor

Use this Skill to provide a transparent, non-binding product comparison. It supports advice and calculation only; it does not open accounts, apply for cards, move funds, or otherwise perform a banking action.

## Required controls for any subsequent banking action

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Do not treat a product recommendation as authorization to open an account, apply for a card, transfer an opening deposit, or make any other change. Obtain a clear selection and authorization first, then complete all applicable checks above using the declared banking tools.

## Method

1. Identify the decision objective and horizon. For this Skill, calculate annual net savings yield as:

   `deposit balance × effective APY ÷ 100 − annual fee for the newly selected card`

   This is a comparison estimate using quoted APY. It is not a daily-balance interest posting forecast. Do not subtract fees that have not been established as applicable.
2. Collect the current deposit amount; every savings option's opening and ongoing balance requirements; base APY or balance tiers; relevant account fees; and any additional explicitly documented relationship bonuses.
3. Collect each card's annual fee, eligibility requirements, current promotional conditions and dates if relevant, and the APY bonus for the particular savings account. Do not infer eligibility from a vague credit description. Mark a card as conditional when a score, subscription, invitation, approval, or another requirement is not confirmed.
4. Determine the applicable savings base APY at the proposed balance. Exclude options whose required opening deposit or ongoing balance cannot be met, unless presenting them separately as alternatives requiring additional funding.
5. For each savings account, select at most one card APY bonus: the highest applicable bonus among all active linked cards, including a contemplated new card if approved. Never add multiple card bonuses together. Add that selected card bonus to the base APY and to separately documented eligible relationship or linked-checking bonuses.
6. If multiple linked checking accounts have qualifying boosts for the savings account, select only the highest applicable checking boost. A checking account that is not an explicitly eligible pairing contributes zero. Checking boosts can be added to the selected credit-card bonus when both are applicable.
7. Run `scripts/compare_net_yield.py` with structured facts gathered at runtime. Use only confirmed values in the final recommendation. Explain excluded or conditional candidates and show the arithmetic for the top option.
8. Tell the customer that card approval remains subject to underwriting and that rates, terms, and eligibility should be confirmed before an application. If they choose to proceed, switch to the governing account-opening/card-application workflow and its prerequisite checks; do not attempt action through the calculator.

## Calculator interface

Run:

```text
run_skill_script(relative_path="scripts/compare_net_yield.py", input_json={...})
```

The script reads one JSON object from stdin and emits one JSON object on stdout.

### Input schema

```json
{
  "balance": 20000,
  "savings": [
    {
      "name": "Official savings account name",
      "base_apy_pct": 2.0,
      "tiers": [{"minimum_balance": 0, "apy_pct": 2.0}],
      "minimum_opening_deposit": 0,
      "minimum_ongoing_balance": 0,
      "relationship_bonus_pct": 0,
      "checking_boosts": [
        {"checking_name": "Official checking name", "boost_pct": 0, "eligible": true}
      ]
    }
  ],
  "cards": [
    {
      "name": "Official card name",
      "annual_fee": 0,
      "eligible": true,
      "bonuses": {"Official savings account name": 0}
    }
  ],
  "existing_cards": [
    {
      "name": "Existing active card",
      "bonuses": {"Official savings account name": 0}
    }
  ]
}
```

`balance`, monetary requirements, fee, and APY fields must be non-negative numbers. Supply either `base_apy_pct` or nonempty `tiers` for each savings option. A tier applies when `balance >= minimum_balance`; the tier with the greatest qualifying minimum is selected. `eligible` must be `true` only when all material eligibility requirements known for that card have been confirmed. Omit unavailable options rather than inventing values. `existing_cards` is optional and is used only to enforce the highest-card-bonus rule.

### Output interpretation and validation

The output includes `ranked_eligible_combinations`, `conditional_combinations`, and `excluded_savings`. Each ranked item shows the selected APY components, annual interest estimate, annual fee, and net annual estimate. Check before relying on the result that:

- `errors` is empty;
- all intended account and card facts were represented;
- in each result, `selected_card_bonus_pct` equals the maximum of the proposed card's and existing active cards' account-specific bonuses, not their sum;
- `selected_checking_boost_pct` is the maximum eligible checking boost, not a sum;
- any savings account below an opening or ongoing requirement is listed in `excluded_savings` rather than ranked; and
- the displayed formula equals interest minus the proposed card's stated annual fee.

The `conditional_combinations` list is informational only. Do not present it as a qualified recommendation until its eligibility facts are confirmed.

## Customer-facing response pattern

State the recommended eligible combination, its effective APY, expected one-year interest, annual card fee, and net estimate. Briefly identify why apparently attractive alternatives were excluded (for example, unmet balance requirement, annual fee, unavailable subscription, invitation-only status, or lower account-specific bonus). State whether the customer's existing checking relationship produces a documented boost; do not assume a boost merely because a checking account exists. Ask whether the customer would like to proceed only after delivering the comparison.

## If the customer elects to open a personal savings account

Use the documented personal-savings opening procedure, not this calculator, and only after the required controls above are satisfied. Confirm identity, an active Rho-Bank checking account held at least 14 days, fewer than five personal savings accounts, no collections or negative balances, and the exact official savings `account_class` ending in `Account`. Confirm the selection, use the normal account-opening tool with `account_type` set to `savings`, then ask whether the customer authorizes an immediate opening-deposit transfer. Before any transfer, verify the source account, available balance, amount, recipient/new-account details, fees, limits, and confirmation. If funding is deferred, state the documented funding deadline and consequence. Do not claim an account or card was opened unless the appropriate declared banking tool reports success.
