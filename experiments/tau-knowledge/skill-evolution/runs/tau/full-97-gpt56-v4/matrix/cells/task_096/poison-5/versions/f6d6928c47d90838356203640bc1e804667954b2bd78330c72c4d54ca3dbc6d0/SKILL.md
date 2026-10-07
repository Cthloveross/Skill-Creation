---
name: savings-interest-discrepancy-explainer
description: Explain a customer's apparent savings-interest discrepancy when account APYs, linked-checking boosts, card bonuses, daily compounding, daily-balance changes, or automatic sweeps may matter. Use for informational reconciliation, not for posting corrections or accessing account data.
---

# Savings interest discrepancy explainer

Use this Skill to give a transparent, non-speculative explanation of a savings interest credit. It is especially useful where a base APY may receive one linked-checking boost and one credit-card bonus, but multiples within either category do not stack.

## Scope and guardrails

- Treat product documentation and the customer's supplied facts as the source of truth. Do not invent a statement period, displayed APY, average balance, sweep activity, or account linkage.
- Do not say that a correction is due unless actual statement data establishes an error.
- General rate explanations do not require identity verification or account-changing tools. Do not access or alter customer data merely to explain a calculation.
- An account's qualification must be established by the applicable product pairing and the accounts being under the same customer profile. If that is not confirmed, state the resulting rate as conditional.
- An automatically swept balance is no longer part of the savings balance for later daily accrual. Do not assume a sweep occurred merely because a balance exceeded a threshold.

## Method

1. Identify each savings account's documented base APY and whether interest compounds daily and is credited monthly.
2. Identify qualifying linked checking accounts for that savings type and their individual boosts. Select **only the highest applicable checking boost**; do not add checking boosts together.
3. Identify eligible linked credit cards and their individual bonuses. Select **only the highest applicable card bonus**; do not add card bonuses together.
4. Add the base APY, selected checking boost, and selected card bonus, because the selected checking and card components may stack with each other.
5. Explain that a monthly credit depends on every day's eligible balance and the statement-cycle length, not simply the approximate balance quoted by the customer. A balance change, a shorter/longer cycle, or a sweep can change the amount materially.
6. If enough inputs are known, use `scripts/estimate_interest.py` to make a clearly labeled estimate. Do not round daily accrual; round only the final displayed estimate to cents.
7. Reconcile exactly only after obtaining the statement start/end dates, APY shown on each statement, and daily balance history or material transaction dates/amounts. For accounts with possible sweeps, also obtain sweep status and sweep transaction dates/amounts.

## Daily-compounding estimate

The helper accepts APY and boost inputs in percentage points (for example, `6.0` means 6.0%). It selects the maximum value in each bonus category and computes:

- `total_apy_percent = base + highest checking boost + highest card bonus`
- daily effective rate estimate: `(1 + total_apy_percent / 100) ** (1 / 365) - 1`
- for a constant balance over `n` days: `balance * ((1 + daily_rate) ** n - 1)`

This is an estimate based on the disclosed APY and daily compounding. The statement's actual daily-balance method, eligibility rules, and posted credit control the exact result.

### Script input and output

`python3 scripts/estimate_interest.py` reads one JSON object from standard input and emits one JSON object to standard output.

Input schema:

- `base_apy_percent` (required number, >= 0)
- `checking_boost_percents` (optional list of nonnegative numbers; default `[]`)
- `card_bonus_percents` (optional list of nonnegative numbers; default `[]`)
- exactly one optional balance representation:
  - `constant_balance` (nonnegative number) together with `days` (positive integer), or
  - `daily_balance_schedule`: a nonempty list of `{ "days": positive integer, "balance": nonnegative number }`

The schedule form is suitable for periods with known balance segments. If no balance representation is supplied, the script still returns the selected bonuses and combined APY, but no interest estimate.

Example call (illustrative values only):

```sh
printf '%s' '{"base_apy_percent": 4.0, "checking_boost_percents": [0.2, 0.5], "card_bonus_percents": [0.1, 0.3], "constant_balance": 10000, "days": 30}' | python3 scripts/estimate_interest.py
```

Validate that `selected_checking_boost_percent` and `selected_card_bonus_percent` are maxima rather than sums, that `total_apy_percent` equals their permitted sum with base APY, and, when a balance was supplied, that `estimated_interest` is present and `estimated_interest_rounded` is a two-decimal currency string.

## Customer-facing response pattern

Provide a concise explanation in this order:

1. Acknowledge the two credits can look counterintuitive because dollar interest depends on rate, daily eligible balances, and cycle length.
2. State each known or conditionally applicable rate component, explicitly noting that only the highest checking boost and highest card bonus apply within their respective categories.
3. State the calculated combined APY when all qualifying components are known. Do not conflate that annual rate with one month's interest.
4. Explain daily compounding/monthly crediting and any plausible, documented balance effect (such as an unconfirmed sweep) without asserting it happened.
5. Compare the posted amounts only as approximate estimates if statement dates and daily balances are unavailable.
6. List the exact items needed for a definitive reconciliation: statement dates, displayed APY, daily balance changes, and relevant sweep details. Offer to recalculate when those details are available.

If the customer asks for a correction or maintains that the posted interest is wrong after supplying records, follow the available institution workflow for review; this Skill does not authorize an adjustment.