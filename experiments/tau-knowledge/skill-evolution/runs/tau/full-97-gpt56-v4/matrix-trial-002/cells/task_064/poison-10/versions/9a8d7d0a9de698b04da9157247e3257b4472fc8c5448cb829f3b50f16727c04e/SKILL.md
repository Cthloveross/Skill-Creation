---
name: savings-and-card-one-year-comparison
description: Compare savings-account and credit-card combinations for a one-year net-earnings goal using supplied product terms, customer eligibility, deposit amount, and spending range. Use for informational banking recommendations; it does not open accounts or apply for cards.
---

# Savings and Credit Card One-Year Comparison

Use this Skill when a customer wants to choose a savings account and credit card based on a one-year financial outcome, especially where account APY, card-linked APY bonuses, card rewards, and annual fees interact.

## Scope and safety

This is an informational comparison only. Do **not** open accounts, submit applications, change account settings, transfer funds, or redeem rewards. Do not imply approval or eligibility when credit score, subscription, account status, or another prerequisite is unconfirmed.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For a recommendation, identify which prerequisites are confirmed, unconfirmed, or unmet. If the customer asks to proceed with an account-opening or card-application action, explain the applicable requirements and use only declared normal banking tools after the relevant verification and confirmation requirements are met.

## Method

1. Extract only the current, applicable product terms from the supplied task materials or approved knowledge sources:
   - savings APY, minimum balance, maintenance fees, and any required opening deposit;
   - each card's annual fee, ordinary-spend reward rate, eligibility requirements, and savings-specific APY bonus;
   - the card-bonus stacking rule and any linked-checking boost eligibility;
   - whether rewards are cash, points, and their documented redemption value.
2. Record the customer's deposit, annual spending range, spending categories, existing products, and known eligibility facts. Convert a monthly spending range to annual spending by multiplying both endpoints by 12.
3. Do not treat vague spending as qualifying for a category bonus. For example, use a flat general-purchase rate unless the customer has confirmed that their spending matches the documented merchant/category requirements.
4. Apply product policies exactly. In particular, if card APY bonuses do not stack, use only the highest applicable card bonus. Add a checking-account boost only if the documented account pairing qualifies.
5. Use `scripts/compare_one_year.py` to calculate every supplied savings/card combination. Supply rates as percentage points (for example, `6.0`, not `0.06`). Mark uncertain eligibility as `unknown`, not `eligible`.
6. Present results in two groups:
   - **Available based on confirmed facts**: all stated requirements are met.
   - **Conditional alternatives**: potentially better choices requiring confirmation of a credit score, subscription, category behavior, or another prerequisite.
   Exclude combinations with known unmet requirements from the recommendation, but explain why they were excluded if material.
7. State the calculation assumptions: stable qualifying deposit for the full year; APY is used as the stated one-year yield; posted eligible purchases only; no returns, interest, late fees, or other charges; and no unconfirmed bonus or boost.
8. Give a direct next step. If the top alternative is conditional, ask only for the missing fact(s) needed to establish eligibility and offer the strongest confirmed alternative in the meantime.

## Calculation model

For each combination, the script calculates:

- `effective_apy_percent = base APY + applicable card APY bonus + applicable linked-checking boost`
- `estimated_interest = deposit × effective APY / 100`
- `estimated_rewards = annual eligible spending × ordinary reward rate / 100`
- `net_one_year_value = estimated interest + estimated rewards − annual card fee − annual savings fee`

The model uses APY as a one-year yield, so it does not compound the APY again. It is a comparison estimate, not a promised interest or rewards amount. Use a spending range whenever the customer's spending is a range.

## Script interface

Run:

```text
python scripts/compare_one_year.py < input.json
```

The script reads one JSON object from standard input and emits one JSON object to standard output.

Required input fields:

```json
{
  "deposit": 30000,
  "monthly_spend": {"min": 1500, "max": 2000},
  "savings_accounts": [
    {
      "name": "Current savings product name",
      "base_apy_percent": 0,
      "minimum_balance": 0,
      "annual_fee": 0,
      "eligibility": "eligible"
    }
  ],
  "cards": [
    {
      "name": "Current card product name",
      "annual_fee": 0,
      "ordinary_reward_percent": 0,
      "eligibility": "unknown",
      "requirements": ["Requirement to disclose"],
      "apy_bonus_percent_by_savings": {"Current savings product name": 0}
    }
  ]
}
```

Optional fields:

- `annual_spend`: `{ "min": number, "max": number }`; takes precedence over `monthly_spend`.
- `linked_checking_boost_percent_by_savings`: mapping from savings name to a documented applicable boost. Omit or set to zero when no pairing qualifies.
- `savings_accounts[].required_opening_deposit`: used to flag a deposit too small to open the account.
- `savings_accounts[].requirements` and `cards[].requirements`: customer-facing prerequisites included in output.
- `savings_accounts[].eligibility` and `cards[].eligibility`: `eligible`, `unknown`, or `ineligible`.

The output contains `annual_spend`, `comparisons`, and `input_warnings`. Each comparison includes its net-value range, the components used, eligibility status, and reasons. The output is sorted with eligible combinations first, then unknown combinations, then ineligible combinations; within each group, higher minimum net value ranks first.

## Validation and interpretation

Before relying on the result, check that:

- every rate was entered as a percentage point, not a decimal fraction;
- the deposit meets each selected account's opening and ongoing minimums;
- annual fees are annual, not monthly;
- only documented applicable APY bonuses and checking boosts were entered;
- reward rates reflect the customer's confirmed ordinary purchases;
- unknown eligibility remains marked `unknown`.

If the script reports an `input_warnings` item or a comparison has `ineligible` status, correct the supplied facts or clearly disclose the limitation rather than presenting that combination as available.
