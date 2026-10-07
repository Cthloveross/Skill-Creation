---
name: banking-product-combination-advisor
version: 1.0.0
description: Compare savings-account and credit-card combinations using current product terms and a customer's balance, spending, and eligibility; then safely progress to opening a selected personal savings account only after all banking prerequisites and explicit confirmations are satisfied.
---

# Banking Product Combination Advisor

Use this Skill when a customer asks which savings account and credit card combination provides the best expected value, or asks to open a recommended personal savings account. It supports advisory comparisons first; it does not assume that a recommendation authorizes an account opening, a transfer, or a credit-card application.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## 1. Establish the request and collect only necessary comparison inputs

For advice, identify or ask for:

- Savings amount, expected holding period, expected balance changes, and whether it is an opening deposit.
- Expected card spend for the same period and a rough category mix.
- Whether the customer expects to carry a balance; if so, do not present rewards as a reason to borrow, and include applicable APR considerations separately.
- Existing products only when a documented relationship, linked-account, or card APY benefit may apply.
- Product constraints the customer values, such as minimum balances, monthly fees, annual fees, withdrawals, foreign use, or promotional offers.

Use the supplied runtime time when testing offer windows. Do not infer eligibility, account linkage, credit approval, merchant coding, direct-deposit status, or a bonus qualification from the customer's interest in a product.

## 2. Extract product terms from supplied materials

For each viable savings product, collect the applicable balance-tier APY, opening deposit, ongoing balance requirement, maintenance fee, relevant feature conditions, and credit-card APY bonus. For each viable card, collect annual fee, ordinary-spend reward rate, category conditions, reward conversion value, relevant welcome-offer requirements/window, and any linked-savings bonus.

Apply these interpretation rules:

1. Select the savings APY tier using the customer's expected balance and the product's documented threshold.
2. Determine bonuses only for products documented as held under the same customer profile and subject to all stated conditions.
3. If multiple credit-card APY bonuses apply, use only the highest applicable credit-card bonus when the documented policy says card bonuses do not stack. Do not add them.
4. If multiple checking boosts apply, use only the highest applicable checking boost when the documented policy says checking boosts do not stack. Add a valid checking boost only where a documented matching account pairing and percentage are available.
5. Add distinct bonus types only if documentation explicitly permits them to stack. State each assumption.
6. Treat reward points as monetary value only when the product documentation supplies a redemption conversion. Treat category rewards as conditional on posted eligible merchant classification.
7. Count a welcome offer only when the account-opening date, new-customer status, spending threshold, qualifying-period rules, and good-standing conditions are all met or explicitly modeled as a conditional scenario.

Do not fill gaps with generic banking assumptions. Mark a candidate as unavailable or conditional when a material rate, fee, eligibility condition, or product pairing is not documented.

## 3. Calculate and explain first-period value

Construct a candidate record for each valid savings/card combination. Its `effective_apy` must already include only bonuses that were established in step 2. Its reward value should use the customer's applicable ordinary or category-weighted reward rate; do not claim a category rate for mostly general spending without support.

Run the packaged calculator:

```sh
python3 scripts/evaluate_combinations.py < comparison.json
```

The script reads a JSON object from standard input and writes one JSON object to standard output. It is advisory only and never performs banking actions.

### Input schema

```json
{
  "balance": "nonnegative decimal",
  "days": "positive integer, normally 365",
  "annual_card_spend": "nonnegative decimal",
  "candidates": [
    {
      "savings_name": "string",
      "card_name": "string",
      "effective_apy": "nonnegative percentage, e.g. 4.25",
      "monthly_savings_fee": "nonnegative decimal",
      "annual_card_fee": "nonnegative decimal",
      "reward_value_per_dollar": "nonnegative decimal, e.g. 0.01",
      "welcome_bonus_value": "nonnegative decimal",
      "welcome_bonus_status": "eligible|conditional|ineligible",
      "notes": ["optional documented assumptions or conditions"]
    }
  ]
}
```

`welcome_bonus_value` is included only when `welcome_bonus_status` is `eligible`; conditional and ineligible bonuses are excluded from the total. For a customer with expected balance changes, split the comparison into intervals with stable balances or clearly label the constant-balance estimate.

### Output schema

The output has `results`, sorted from highest to lowest `net_value_excluding_conditional_bonus`. Each result reports savings interest, fees, rewards, included welcome bonus, conditional welcome bonus, the net value, and the assumptions copied from its candidate. `errors` contains per-candidate validation failures without suppressing other valid candidates.

Explain the recommendation in customer-facing terms: the expected interest, each fee, ordinary-spend rewards, any excluded conditional promotion, and decisive limitations. Present a clearly better documented candidate as the recommendation; if values are close or material terms are unknown, present the trade-off rather than asserting a winner.

## 4. Handle a request to open the selected savings account

Give advice without identity verification, but before any account action perform the mandatory control above. For a personal savings-account opening, verify all of the following from authoritative account records:

- Customer identity and authority.
- At least one active qualifying checking account and the required checking-account tenure.
- Fewer than the documented maximum number of personal savings accounts.
- No disqualifying collections activity or negative balances.
- The exact official savings `account_class` selected by the customer.
- Required opening deposit, source-account ownership, available balance, and all applicable fees or deadlines.

Ask for explicit confirmation of the exact account class before opening it. Opening a savings account does not authorize moving money. After a successful opening, separately ask whether the customer authorizes an immediate opening-deposit transfer, including source account and amount. If authorization is absent, explain the documented funding deadline and consequence rather than transferring funds.

Use only the normal banking tools and parameters declared for the runtime and documented procedure. If a required tool is described as discoverable, unlock it and call it only after the listed prerequisites are verified. Report tool outcomes accurately; do not claim an account was opened or funded until the action reports success. If a prerequisite cannot be confirmed, stop the action and explain the missing requirement.

## 5. Final response checklist

- State the recommendation or comparison outcome and the assumptions used.
- Separate confirmed value from conditional promotions and eligibility-dependent features.
- State that card approval and credit limits remain subject to underwriting where applicable.
- For any completed banking action, identify what succeeded and the resulting funding status; otherwise state the next explicit confirmation or verification needed.
- Do not expose internal identifiers, fabricate account data, or make actions on the basis of implied consent.
