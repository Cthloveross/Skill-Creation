---
name: savings-credit-card-net-return-advisor
description: Give a rigorous, customer-specific one-year comparison of savings and credit-card combinations, including APY bonuses, rewards, recurring fees, eligibility, and the transition from advice to a requested banking action.
---

# Savings and Credit-Card Net-Return Advisor

Use this Skill for a customer who wants the best savings account and credit card combination based on a stated deposit balance and expected spending. It produces an informational recommendation; it does not itself open an account, apply for a card, move money, or change account settings.

## 1. Establish the decision facts

Collect only facts necessary for the estimate:

1. Deposit amount and whether it will remain on deposit for a full year.
2. Monthly spend range and its main merchant category. If no category is known, use only the documented general/default rate.
3. Whether the card will be paid in full monthly. Do not estimate card interest when it will be paid in full.
4. Credit-score information or a stated preference to avoid score requirements, subscriptions, annual fees, or other eligibility hurdles.
5. Current checking products and the account profile relationship, but use a checking APY boost **only** if both the exact pairing and exact boost percentage are documented.
6. Each opening threshold, ongoing balance threshold, fee trigger, annual/monthly fee, rewards redemption condition, and promotion condition relevant to the selected products.

Do not treat “I prefer no high score requirement” as proof of a score. Mark score-gated products conditional. For a recommendation that honors this preference, do not select them as the primary choice. If the customer instead asks for the absolute highest return regardless of eligibility, identify the best conditional option separately and name every condition.

## 2. Interpret terms precisely

- APY is already an annualized yield. Estimate yearly interest as `deposit × applicable APY / 100`; do not compound an APY again.
- Add a card APY bonus only if it applies to that specific savings product under the same customer profile. If multiple card bonuses exist, use only the highest one when the policy says bonuses do not stack.
- A checking boost likewise needs a documented matching pair and percentage; do not infer a boost from a similarly named checking account.
- Apply maintenance fees when the planned balance is below the applicable waiver/minimum threshold. A card can change that threshold only when its terms explicitly say so. Evaluate that override per pair, not once for every savings account.
- Include card annual fees and required subscription fees for all 12 months. Do not count one-time bonuses, category rates, promotional APR value, or rewards with an unmet spend/redemption condition.
- A redemption minimum matters in a one-year net-return comparison. Convert a points threshold to its documented cash-equivalent value, calculate potential rewards at **each** end of the spend range, and count a reward only at an endpoint where it can be redeemed during the year. Show unreached accrued rewards separately rather than calling them net return.
- For a cash-back percentage, annual value is `annual eligible spend × rate / 100`. For points per dollar, annual value is `annual eligible spend × points per dollar × documented dollar value per point`. Do not mix these units.
- If the customer may carry a balance, state the APR and say an interest estimate needs payment timing and carried-balance data; a high APR can outweigh rewards.

When product material conflicts, do not silently choose a favorable figure. Prefer the specific governing term for the product and situation; otherwise describe the conflict and avoid a precise ranking that depends on it.

## 3. Calculate and recommend

Create candidates only from documented product terms. First exclude `ineligible` candidates and then calculate the remaining confirmed and conditional pairs with `scripts/compare_combinations.py`. Review its output before responding: the calculator does arithmetic, not eligibility research.

Primary recommendation rule:

1. Rank only combinations that meet the customer’s stated requirements and whose material conditions are confirmed.
2. If none is confirmed, recommend the best fit as conditional and state what must be confirmed.
3. If a conditional product would earn more, label it clearly as a **conditional higher-return alternative**, never as the customer’s available result.
4. If the customer asks for “one” option, give one primary selection and its concise calculation. Do not overwhelm them with a catalog; mention another option only if its eligibility condition materially changes the answer.

The response should show deposit, APY components, interest, annual spend/rewards, all recurring fees, and net low–high range rounded to cents. State assumptions (balance held, eligible posted spend, paid in full, and no undocumented checking boost). Avoid guarantees and state that card approval remains subject to underwriting.

## 4. Calculator interface

Run:

```sh
python3 scripts/compare_combinations.py < comparison_request.json
```

It reads one JSON object from stdin and emits one JSON object on stdout. Malformed input yields `{"ok":false,"error":"..."}`.

Required fields:

- `initial_savings_balance`, `monthly_spend_low`, `monthly_spend_high` (nonnegative numbers; low no greater than high)
- nonempty `savings_accounts` and `cards` arrays.

Savings candidate fields: `name`, `base_apy_pct`, `monthly_maintenance_fee`; optional `additional_apy_pct`, `fee_waiver_balance`, `fee_applies`, and `eligibility_status` (`confirmed`, `conditional`, or `ineligible`). `fee_applies`, if explicitly supplied, takes precedence; otherwise the fee applies when balance is below `fee_waiver_balance`.

Card candidate fields: `name`, `annual_fee`; optional `required_membership_monthly_fee`, `card_apy_bonuses_pct` (account-name to percentage-point bonus), `fee_waiver_balance_overrides` (account-name to an overridden waiver threshold), `eligibility_status`, and `rewards_redeemable`. Use `minimum_redeemable_reward_value` for a reward redemption minimum expressed in cash-equivalent value. The calculator reports potential and currently redeemable reward values separately.

Rewards use either:

- `reward_rate_unit: "percent"` with `reward_rates` and/or `default_reward_rate`, such as `1` for 1%; or
- `reward_rate_unit: "points_per_dollar"` with `reward_rates` and/or `default_reward_rate`, plus `point_value`, such as `1` and `0.01` for one point per dollar worth one cent.

`spend_category` selects a matching rate; otherwise the default rate is used. `selected_card_apy_bonus_pct` is only for an already-held multi-card portfolio after the documented nonstacking selection has been made.

Example shape (illustrative placeholders, not product terms):

```json
{"initial_savings_balance":5000,"monthly_spend_low":100,"monthly_spend_high":200,"spend_category":"general","savings_accounts":[{"name":"Savings A","base_apy_pct":4,"monthly_maintenance_fee":0}],"cards":[{"name":"Card A","annual_fee":0,"reward_rate_unit":"percent","default_reward_rate":1,"card_apy_bonuses_pct":{"Savings A":0.5}}]}
```

Validate that a reported APY equals base plus only supported bonuses, the maintenance-fee flag matches the threshold, points and percent rewards use the right unit, each endpoint meets any redemption threshold before its rewards are counted, and all annualized fees were subtracted.

## 5. If the customer asks to apply, open, fund, link, or transfer

This becomes a banking action, not a recommendation. Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

Use the declared banking tools only. Do not invent an account-opening, application, transfer, or funding tool. Before using an action tool, verify identity: obtain a customer record with an allowed lookup, compare two customer-provided identity fields against that record, get the current time, and call `log_verification` with the matching record and timestamp. Do not log verification if the fields do not match. Then verify authority, ownership, eligibility, available balance or credit, fees, limits, cutoffs, recipients/card details, and confirmation requirements.

Confirm the exact product, applicable terms, funding source and amount, availability, and the customer’s final authorization immediately before an action. A statement that the customer will fund later does not satisfy an account’s minimum opening-deposit requirement; explain the minimum and do not imply an account was opened. If no declared tool can perform the requested action after the required review, say so plainly, confirm that no application/account/transfer was submitted, and direct the customer to the documented self-service application flow without fabricating navigation or tool names.
