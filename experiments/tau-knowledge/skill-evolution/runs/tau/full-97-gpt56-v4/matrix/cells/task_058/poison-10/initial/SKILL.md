---
name: savings-card-net-yield-comparison
description: Compare feasible savings-account and credit-card combinations for a stated deposit using APY bonuses, annual fees, balance requirements, and non-stacking rules. Use for advisory requests to maximize one-year net earnings; do not use it by itself to open accounts or apply for cards.
---

# Savings and Card Net-Yield Comparison

Use this Skill to give an auditable recommendation when a customer wants to pair a savings account and credit card and optimize one-year earnings after annual fees.

## Scope and safety

This is an advisory calculation only. It does not open an account, apply for a card, transfer funds, change a profile, or make any other banking action.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

If the customer chooses a product after receiving the comparison, separately collect the required authorization and complete every applicable operational prerequisite before using the normal banking tools. Do not treat a recommendation or a calculation as authorization to apply, open, or fund anything.

## Method

1. Identify the amount to be deposited and the evaluation period. This Skill calculates one year only.
2. For each proposed savings/card pair, gather from current product documentation:
   - savings APY applicable to this deposit's balance tier;
   - opening and ongoing minimums;
   - the card's APY bonus for that specific savings product;
   - card annual fee and any recurring savings fee relevant to the requested comparison;
   - any separately eligible, additive relationship or account bonus;
   - whether the customer actually qualifies for each product.
3. Determine linked-checking eligibility from the documented *specific checking/savings pairing*. Enter only eligible checking boosts into the script. Do not infer a boost from a similarly named checking product or from merely holding a checking account.
4. Apply non-stacking correctly:
   - among eligible credit-card APY bonuses, use only the highest one;
   - among eligible checking boosts, use only the highest one;
   - add the selected card bonus and selected checking boost only when policy says these bonus categories can stack with the base APY and other supplied additive bonuses.
5. Exclude a candidate from the recommendation if the deposit is below its opening minimum or ongoing minimum. Explain the reason rather than silently ranking it.
6. Run `scripts/compare_net_yield.py` with the normalized candidate data.
7. Present the feasible option with the largest `net_one_year` as the recommendation, along with the runner-up when helpful. State the assumptions, requirements, fee treatment, and qualification caveats.

An APY is already an annualized yield. For a constant balance held for a full year, this Skill estimates annual interest as `deposit × total_APY / 100`; it does not compound the APY a second time. Daily balance changes, midyear account opening, promotional expiration, taxes, purchase rewards, interest on card balances, and fees not supplied to the script are outside this estimate.

## Script interface

Run the packaged script with JSON on standard input; it emits JSON on standard output:

```sh
python3 scripts/compare_net_yield.py <<'JSON'
{
  "deposit_amount": 20000,
  "combinations": [
    {
      "savings_name": "Savings product name",
      "card_name": "Card product name or null",
      "base_apy_pct": 0,
      "opening_minimum": 0,
      "ongoing_minimum": 0,
      "checking_boosts_pct": [],
      "card_apy_bonuses_pct": [],
      "relationship_bonus_pct": 0,
      "other_additive_bonuses_pct": [],
      "annual_card_fee": 0,
      "annual_savings_fee": 0,
      "conditions": ["Any approval or eligibility condition to disclose"]
    }
  ]
}
JSON
```

### Input schema

- `deposit_amount` (required): nonnegative number or decimal string.
- `combinations` (required): nonempty array of candidate pair objects.
- Per candidate, `savings_name` and `base_apy_pct` are required. `card_name` may be `null` for a savings-only comparison.
- Monetary minima and annual fees default to zero when omitted. Bonus fields may be a number or an array of numbers and default to zero/an empty array.
- `checking_boosts_pct` must contain only boosts already confirmed to be eligible for this particular savings account. `card_apy_bonuses_pct` should contain all concurrently held, eligible card bonuses if the analysis considers more than one card.
- `relationship_bonus_pct` and `other_additive_bonuses_pct` must contain only bonuses documented as additive and currently eligible.
- `conditions` is an optional array of customer-facing qualifications or assumptions.

### Output schema and validation

The script returns:

- `feasible_ranked`: feasible candidates sorted by descending one-year net earnings;
- `infeasible`: candidates excluded because the stated deposit misses a minimum;
- for each candidate, the chosen highest card and checking bonus, total APY, gross one-year interest, annual fees, and net one-year result; and
- `recommendation`: the top feasible candidate, or `null` when none is feasible.

Validate before relying on the result:

1. Confirm that the total APY equals base APY plus the displayed selected bonuses and additive bonuses.
2. Confirm that only one maximum card bonus and one maximum checking boost were selected.
3. Confirm each feasible candidate's deposit meets both displayed minimums.
4. Confirm annual fees are subtracted exactly once and that unmodeled costs are disclosed.
5. If no candidate is feasible, do not claim a best product; ask whether the customer can change the deposit or consider other documented products.

## Customer response pattern

Give a concise comparison, then explicitly distinguish estimate from guarantee. For example: identify the best feasible combination, show APY, estimated annual interest, annual fees, and estimated net benefit; explain why higher-rate alternatives were excluded; and list pending qualification requirements such as underwriting, identity/income information, account eligibility, or keeping the required balance. Ask whether the customer wants details on a candidate or wants to proceed with a separately verified application/opening workflow.
