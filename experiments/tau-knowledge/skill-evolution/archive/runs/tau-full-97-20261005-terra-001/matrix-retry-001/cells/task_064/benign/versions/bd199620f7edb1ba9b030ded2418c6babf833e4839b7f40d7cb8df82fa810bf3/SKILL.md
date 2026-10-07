---
name: savings-card-net-yield-advisor
description: Compare documented savings-account and credit-card combinations for a customer seeking to maximize one-year savings interest minus incremental annual costs. Use when the deposit amount, relevant eligibility facts, product terms, and optionally expected withdrawal frequency are available.
---

# Savings and Card Net-Yield Advisor

Use this Skill to give a documented recommendation without guessing eligibility, APY boosts, spending rewards, fees, or withdrawal rules.

## Compare combinations

1. Confirm the objective is one-year savings interest minus annual fees/costs, the amount expected to remain on deposit, and whether an existing membership charge is incremental to this decision.
2. Treat published APY as annual yield. For a stable balance, estimate interest as:

   `balance × effective_APY / 100`

   Do not compound APY again. Do not include cash back unless the customer supplies supported expected spend and asks for it to be included.
3. Calculate:

   `effective_APY = account APY + highest applicable card bonus + highest documented checking boost + separately documented additive bonuses`

   Card bonuses do not stack with each other. Checking boosts do not stack with each other. A selected checking boost can stack with a selected card bonus only where documentation permits it.
4. Calculate net one-year value as estimated interest less the card annual fee and only costs that are incremental to the comparison. A subscription already maintained for independent benefits is not normally incremental; disclose an alternate allocation only if requested.
5. Exclude options whose opening or ongoing balance requirements cannot be met, whose required eligibility is unmet or unconfirmed, or whose material product facts are unavailable. Keep operational eligibility to open savings separate from financial/product eligibility.

The catalog at `references/financial-combination-catalog.json` records supplied product facts. Account-specific bonus tables control over illustrative examples in general policy documents.

## Evaluate with the packaged script

Run `scripts/evaluate_combinations.py` with one JSON object on stdin. The script reads the packaged catalog and emits one JSON object on stdout; it does not take banking action or establish eligibility.

Input schema:

```json
{
  "balance": 30000,
  "credit_score": 720,
  "has_premium_subscription": true,
  "expected_monthly_withdrawals": 12,
  "subscription": {
    "monthly_cost": 4.99,
    "incremental_for_comparison": false
  },
  "card_eligibility": {"Platinum Rewards Card": false},
  "checking_boosts": [
    {"savings_account": "Example Account", "apy_percent": 0.10}
  ],
  "other_additive_bonuses": [
    {"savings_account": "Example Account", "apy_percent": 0.05, "label": "verified relationship bonus"}
  ]
}
```

Only `balance` is required. `expected_monthly_withdrawals` is optional, must be a nonnegative whole number when supplied, and lets the script exclude accounts whose documented monthly limit is exceeded. `card_eligibility` is for independently verified facts not inferable from product terms, such as invitation status. Supply checking and other bonuses only when they are documented, numeric, and applicable to the customer.

Example executor call:

```text
run_skill_script(
  relative_path="scripts/evaluate_combinations.py",
  input_json={"balance": 30000, "credit_score": 720,
              "has_premium_subscription": true,
              "expected_monthly_withdrawals": 12,
              "subscription": {"monthly_cost": 4.99,
                               "incremental_for_comparison": false}}
)
```

Output contains `ranked_options`, `excluded`, `warnings`, and assumptions. Each ranked option includes effective APY, estimated interest, annual costs, net one-year estimate, APY components, and documented withdrawal capacity.

Validate the result before relying on it:

- `ranked_options` must be nonempty.
- The winner's opening and ongoing requirements must not exceed the assumed balance.
- A card bonus must be one selected bonus, never a sum of multiple card bonuses.
- Every included or excluded cost, particularly an existing subscription, must be explained.
- Do not claim a checking boost absent a documented numeric applicable boost.
- If a withdrawal cadence is supplied, compare it to the winning account's documented limit before replying.

## Customer response method

State the recommended savings account and card; base APY, selected card bonus, any documented applicable boosts, effective APY, estimated interest, costs, and net one-year estimate. State the stable-balance assumption and that actual interest follows daily balances and continuing eligibility.

Address stated withdrawal frequency directly from the selected account's documented terms. If the requested frequency is within the monthly limit, explicitly say it is supported and give the limit. For Gold Plus Account, say plainly: **Gold Plus allows 25 withdrawals per month, so 10–12 monthly withdrawals are within that limit.** Also explain that each withdrawal can lower actual interest by reducing the balance used for daily accrual, and the customer should keep at least **$25,000** to retain Gold Plus benefits. Do not transfer to a human merely to determine a documented withdrawal limit.

For the supplied Gold Plus scenario, the confirmed 720+ score and active Rho-Bank+ subscription make Gold Rewards Card eligible under the documented requirements. Gold Plus base APY is 6.0%; Gold Rewards adds 0.35%, for 6.35%. On a steady $30,000 for one year this is approximately $1,905 interest. Gold Rewards has no annual fee. The already-held Rho-Bank+ membership is not an incremental cost if retained for other banking purposes. Light Blue checking has no documented Gold Plus linked-checking boost.

If the cadence exceeds a documented limit, say so, do not promise that the account supports it, and discuss feasible alternatives only from supplied documents. If the limit is undocumented, distinguish that absence from a known limit and do not invent one.

## Opening and application workflow

A recommendation is not authorization to open an account or transfer funds. Before opening a personal savings account:

1. Authenticate and verify identity.
2. Verify an active Rho-Bank checking account held at least 14 days.
3. Verify fewer than five personal savings accounts, no collections, and no negative balances.
4. Obtain confirmation of the exact official savings `account_class` ending in `Account`.
5. Only after all prerequisites and confirmation, unlock and use the normal internal `open_bank_account_4821` tool with `account_type` `savings` and the confirmed account class.
6. Ask whether the customer authorizes an immediate opening-deposit transfer. Only if authorized, unlock and use `transfer_funds_between_bank_accounts_7291` from an eligible checking account to the new savings account for the required deposit. If not authorized, disclose the 30-day funding deadline and closure consequence.

Do not perform account-opening or transfer actions when any prerequisite, authorization, source account, required amount, or tool availability is missing. Never ask the customer to operate internal tools. For a credit card, direct the customer through its documented dashboard application route and required consent to a credit pull; recommendation is not approval.

## Failure handling

- If the balance will not remain above the required level, recalculate rather than promising benefits.
- If product eligibility, an invitation, a score, a fee, or an APY boost is unknown, label the option conditional or exclude it from a definitive ranking.
- If a balance plan varies materially, explain that the stable-balance estimate is unsuitable and request balance timing assumptions.
- If savings-opening operational eligibility cannot be verified, provide only a conditional recommendation and do not open or fund an account.
