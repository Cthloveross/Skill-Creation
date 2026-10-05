---
name: savings-card-net-yield-advisor
description: Compare documented savings-account and credit-card combinations for a customer who wants to maximize one-year savings interest minus annual product costs. Use when a balance, intended holding period, eligibility facts, and relevant product policies are available. Supports a transparent calculation, handling of non-stacking APY bonuses, and a gated savings-opening workflow.
---

# Savings and Card Net-Yield Advisor

Use this Skill to make a recommendation without guessing eligibility, undocumented APY boosts, spending rewards, or fees.

## Scope and calculation

1. Confirm the objective is **one-year savings interest minus annual fees/costs**, the amount expected to remain on deposit, and whether any existing membership cost is incremental to this decision.
2. Treat a published APY as an annual yield: for a stable balance, estimate interest as:

   `balance × effective_APY / 100`

   Do not compound an APY again. Do not include card cash back unless the customer gives a supported expected spend and explicitly wants it included.
3. Calculate:

   `effective_APY = account APY + highest applicable card bonus + highest documented checking boost + separately documented relationship/direct-deposit bonuses`

   Card bonuses do not stack with one another. Checking boosts likewise do not stack with one another, but the selected checking boost may stack with the selected card bonus. Do not assign a boost where the account pairing is not documented or its percentage is unavailable.
4. Calculate net one-year value as interest less the selected card's annual fee and only costs that are incremental under the stated comparison. A membership already held independently is normally not incremental; disclose a sensitivity calculation if the customer wants to allocate that cost anyway.
5. Exclude an option if the deposit cannot meet its opening or ongoing balance requirement, if a required eligibility condition is unmet, or if a material fee/eligibility fact is unknown. Mark operational savings-opening eligibility separately from product financial eligibility.

`references/financial-combination-catalog.json` contains the supplied product facts needed for the supported comparison. Account-specific bonus tables take precedence over examples in general policy material.

## Running the calculator

Run `scripts/evaluate_combinations.py` with JSON on stdin. It reads the packaged catalog and emits JSON only.

Input schema:

```json
{
  "balance": 30000,
  "credit_score": 720,
  "has_premium_subscription": true,
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

Required input is `balance`; the remaining fields are optional but missing facts can make a card ineligible. `card_eligibility` is for facts not inferable from the catalog, such as an invitation or a separately confirmed eligibility determination. `checking_boosts` must contain only documented numeric boosts applicable to the customer; the script selects the largest one for each savings account. `other_additive_bonuses` must likewise be independently documented and applicable.

Example invocation in an executor that exposes packaged scripts:

```text
run_skill_script(
  relative_path="scripts/evaluate_combinations.py",
  input_json={"balance": 30000, "credit_score": 720, "has_premium_subscription": true,
              "subscription": {"monthly_cost": 4.99, "incremental_for_comparison": false}}
)
```

Output schema:

```json
{
  "assumptions": {"...": "..."},
  "ranked_options": [
    {
      "savings_account": "...",
      "credit_card": "...",
      "effective_apy_percent": "...",
      "estimated_interest": "...",
      "annual_costs": "...",
      "estimated_net_one_year": "...",
      "components": {"...": "..."}
    }
  ],
  "excluded": [{"savings_account": "...", "credit_card": "...", "reasons": ["..."]}],
  "warnings": ["..."]
}
```

Validate before relying on output:

- `ranked_options` must be nonempty.
- Confirm the winning account's opening and ongoing minimums are no greater than the balance under the stable-balance assumption.
- Confirm the winning bonus equals the highest one card bonus, not a sum of card bonuses.
- Confirm every cost inclusion/exclusion is explained, especially a pre-existing subscription.
- Check that the result does not claim a checking boost without a documented numeric applicable boost.
- Present amounts as estimates, because actual interest follows daily balances, eligibility status, and posting rules.

The calculator makes no banking action and does not establish eligibility.

## Response method

Give the customer a short ranked recommendation that states:

- the recommended savings account and card;
- account APY, selected card bonus, any verified checking/relationship boost, and effective APY;
- estimated interest, annual/incremental costs, and net one-year estimate;
- important assumptions (stable balance, qualified/active linked products, no cash-back estimate);
- why any existing checking account does or does not add a boost; and
- material requirements and tradeoffs.

For the supplied Gold Plus scenario, use the account-specific Gold Plus bonus table and explain that the Gold Rewards Card's membership requirement is satisfied only while the premium subscription remains active. Its card annual fee is distinct from the membership charge. If the membership predates and is retained for other purposes, do not silently subtract it as an incremental pairing cost; optionally show the alternate allocation if the customer asks.

## Opening and application workflow

A recommendation or a general request to explore products is not authorization to open an account or transfer money. Before an agent opens a personal savings account, obtain confirmation of the exact account and follow the documented internal prerequisites:

1. Authenticate and verify identity.
2. Verify an active Rho-Bank checking account with at least 14 days' tenure.
3. Verify fewer than five personal savings accounts, no collections, and no negative balances.
4. Confirm the exact official savings `account_class` ending in `Account`.
5. Only then unlock and use the normal internal `open_bank_account_4821` banking tool with `account_type` `savings` and the confirmed full account class.
6. After opening, ask whether the customer authorizes an immediate opening-deposit transfer. If authorized, unlock and use `transfer_funds_between_bank_accounts_7291` from the customer's eligible checking account to the new savings account for the required deposit. If not authorized, disclose the 30-day funding deadline and closure consequence.

Do not perform either action when a prerequisite, authorization, source account, required amount, or tool availability is missing. Never ask the customer to operate internal tools.

For a credit card, follow the product's documented application route. The supplied Gold Rewards Card application is completed in the customer's Rho-Bank dashboard and requires application information and consent to a credit pull; no internal card-opening tool is documented here. Do not represent a recommendation as approval, and do not claim a credit limit.

## Failure handling

- If the customer cannot maintain the required balance, recalculate with feasible accounts rather than promising benefits.
- If an APY boost percentage, annual fee, invitation, score, or membership status is unknown, label that option conditional or exclude it from a definitive ranking.
- If the customer supplies a varying-balance plan, explain that the stable-balance estimate is unsuitable and request daily/monthly balance assumptions; do not fabricate an earnings forecast.
- If operational eligibility cannot be verified, provide the conditional recommendation but do not open or fund an account.
