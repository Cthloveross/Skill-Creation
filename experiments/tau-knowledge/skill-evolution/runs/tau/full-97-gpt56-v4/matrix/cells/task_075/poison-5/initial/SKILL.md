---
name: overseas-atm-cost-comparison
description: Compare checking-account costs for a planned period of overseas ATM use, including per-withdrawal out-of-network charges, conditional maintenance fees, and monthly ATM-operator-fee rebate caps. Use when a customer asks which available account is least costly for anticipated foreign ATM withdrawals or asks for the reasoning behind a recommendation.
---

# Overseas ATM Cost Comparison

Provide a transparent, period-specific comparison rather than treating a stated "$0 foreign ATM withdrawal fee" as a guarantee that every foreign ATM withdrawal is free. That benefit can coexist with a fee for an out-of-network ATM and with third-party ATM-owner surcharges.

## Source facts

Use `references/account_terms.md` for the account facts supplied with this Skill. Do not infer missing account requirements or fees. If current task materials contain newer or account-specific terms, use those terms and identify the source used.

## Method

1. Extract the trip duration, expected withdrawals per month (or total and distribution), expected balance, and any known ATM-owner surcharge information.
2. Determine whether the relevant daily balance threshold will be met. Apply the monthly maintenance fee only when it will not be met.
3. Treat each expected foreign ATM as out-of-network only if that is a reasonable stated assumption. If network status is unknown, say the estimate assumes out-of-network use and explain that in-network use can reduce the bank fee.
4. Calculate each account's known bank cost:
   - `withdrawals × out-of-network fee`, plus
   - `months × applicable maintenance fee`.
5. Treat ATM-owner fees separately. When fees are known, rebate only `min(monthly operator fees, monthly rebate cap)` in each month. Do not apply a monthly cap once across the entire trip.
6. When operator fees are unknown, do not invent an estimate. State that both accounts may be charged the ATM owner's surcharge, then compare the monthly rebate caps. If the same operator-fee pattern is assumed for both accounts, the difference in unreimbursed operator fees is bounded by the difference between their monthly caps.
7. Mention material constraints separately from the arithmetic, including opening-deposit requirements, balance requirements, and the daily withdrawal limit. Do not call a requirement satisfied without the customer's confirmation.

Use `scripts/calculate_atm_costs.py` for the arithmetic. It accepts generic account terms and does not contain account-specific values.

## Script interface

Run:

```text
python3 scripts/calculate_atm_costs.py < input.json
```

Input JSON:

```json
{
  "months": 0,
  "withdrawals_per_month": [0],
  "operator_fees_by_month": null,
  "accounts": [
    {
      "name": "Account name",
      "out_of_network_fee": "0.00",
      "monthly_maintenance_fee_applies": "0.00",
      "operator_fee_rebate_cap": "0.00"
    }
  ]
}
```

- `withdrawals_per_month` may be one nonnegative integer (repeated for every month) or a list with one nonnegative integer per month.
- `operator_fees_by_month` is either `null` when the ATM-owner fees are unknown, one nonnegative monetary value repeated for every month, or a list of one nonnegative total operator-fee amount per month.
- Monetary fields are decimal strings or JSON numbers. `monthly_maintenance_fee_applies` must already be `0` if the fee is waived.

The script emits JSON with withdrawal counts, each account's bank withdrawal cost, maintenance cost, known base cost, and—when operator fees were supplied—rebated and unreimbursed operator costs plus the all-in total. Reject malformed, negative, or inconsistent period data instead of silently producing a result.

## Customer response

Give a short recommendation followed by the calculation in plain language. Clearly label known costs versus unknown ATM-owner charges. Explain the distinction between foreign-transaction/foreign-ATM benefits and out-of-network fees. If the customer has not confirmed opening an account, answer the comparison question only and ask whether they want to proceed afterward; do not represent an account as opened or take an opening action.

Do not perform profile changes, verification logging, or any account-opening action merely to explain costs. If a later request requires a banking action, use only the declared banking tools and satisfy their verification prerequisites first. If a necessary capability is absent, explain the limitation without fabricating completion.

## Validation checklist

Before responding, confirm that:

- withdrawal counts cover the stated trip duration;
- maintenance fees reflect the customer's stated balance expectation;
- every rebate is capped per month, not per trip;
- third-party operator surcharges are not called bank fees and are not fabricated when unknown;
- opening/balance constraints and relevant daily ATM limits are distinguished from cost estimates; and
- no account-opening confirmation or banking action is claimed unless it actually occurred.
