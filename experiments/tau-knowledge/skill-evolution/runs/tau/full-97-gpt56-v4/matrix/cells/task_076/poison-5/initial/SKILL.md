---
name: travel-checking-account-advisor
description: Compare checking accounts for a traveler who needs early direct deposit and wants to minimize overseas ATM costs. Use when account eligibility, early-pay availability, per-withdrawal ATM fees, fee minimums, rebates, and maintenance-fee waivers must be reconciled into a clear customer-facing recommendation.
---

# Travel checking-account advisor

Provide a recommendation only after separating (1) account eligibility, (2) required early-direct-deposit availability, (3) the bank's own foreign and out-of-network ATM fees, (4) third-party ATM operator surcharges and any limited rebates, and (5) non-ATM account fees. Do not treat a third-party surcharge rebate as a waiver of the bank's own ATM fee.

## Runtime input

Use the conversation and supplied public inputs as the source of customer facts. In particular, retain answers already provided in clarifications; do not ask the customer the same question again.

For repeated calculations, run `scripts/compare_accounts.py`. It reads one JSON object from stdin and emits one JSON object on stdout.

Input schema:

```json
{
  "trip_months": 2,
  "withdrawals_per_month": 4,
  "withdrawal_amount": 300,
  "early_direct_deposit_min_days": 1,
  "treat_withdrawals_as_out_of_network": true,
  "accounts": [
    {
      "name": "string",
      "eligible": true,
      "ineligibility_reason": "optional string",
      "early_direct_deposit_days": 0,
      "foreign_atm_fee": {"kind": "none"},
      "out_of_network_atm_fee": {"kind": "flat", "amount": 0},
      "operator_rebate_monthly_cap": 0,
      "monthly_maintenance_fee": 0,
      "maintenance_fee_waived": false,
      "notes": ["optional factual caveat"]
    }
  ]
}
```

Supported fee kinds are `none`, `flat`, `percent`, `percent_with_min`, and `unknown`. Amounts are USD and `percent` is expressed as a decimal (for example, `0.03` means 3%). `operator_fee_per_withdrawal` is optional. Do not supply a value unless the customer supplied or the account evidence establishes that amount. With no known operator fee, the script reports the rebate cap but does not invent a rebate total.

The `treat_withdrawals_as_out_of_network` switch is an explicit scenario assumption. Set it to `true` only when the comparison should include a bank's separate out-of-network charge for each expected withdrawal. If account language makes the relationship between foreign and out-of-network fees unclear, present both the listed foreign-fee result and the conservative out-of-network scenario rather than silently choosing one.

## Method

1. **Build the eligible set.** Exclude accounts the customer cannot open or cannot maintain under stated conditions. Explain the exclusion briefly, especially for age restrictions, required opening deposits, and required ongoing balances. Do not present an unavailable account as the recommendation.
2. **Apply the must-have feature.** Remove accounts with no early direct deposit when the customer requires early access to pay. Report the number of days offered by the recommended account.
3. **Check transaction feasibility.** Confirm that an expected single withdrawal does not exceed a disclosed daily ATM limit. If total expected daily withdrawals are unknown, say that the check applies to each described withdrawal and advise staying within the daily limit.
4. **Calculate only supported fees.** For each remaining account, use the disclosed fee formula for every planned withdrawal:
   - flat: `flat amount × number of withdrawals`;
   - percent: `withdrawal amount × rate × number of withdrawals`;
   - percent with minimum: `max(withdrawal amount × rate, minimum) × number of withdrawals`.
   Keep foreign-ATM fees distinct from out-of-network fees. A $0 foreign fee does not by itself prove that a separate out-of-network fee cannot apply.
5. **Handle rebates accurately.** Operator surcharges are imposed by the ATM owner and can be unknown. State any monthly rebate cap and that it only offsets eligible posted operator charges up to that cap. Do not claim a customer will receive the entire cap unless their actual surcharge total supports it.
6. **Disclose total-cost caveats.** If the selected account has a maintenance fee that will not be waived, calculate it separately over the trip. It is not an ATM fee, but it materially affects the customer's account choice. Do not add it to the ATM-fee ranking unless explicitly comparing overall known bank costs.
7. **Give an actionable answer.** Lead with the eligible recommendation and the estimated bank ATM cost. Then give the main runner-up comparison, rejected alternatives that explain why apparent zero-fee choices do not meet requirements, relevant monthly fees, third-party-fee caveat, and a practical action such as using in-network ATMs and checking surcharge screens.

## Product evidence to apply for this account-comparison corpus

Use these facts only when the current task concerns these named checking products. Product data is reference material, not customer data; customer quantities and eligibility answers must always come from the runtime conversation.

- **Purple Account:** early direct deposit up to 2 days; listed foreign ATM withdrawal fee $0; separate out-of-network ATM withdrawal fee $2.50 per withdrawal; third-party ATM operator fee rebates up to $30 per month; daily ATM withdrawal limit $1,000; monthly maintenance fee $15, waived at a $3,750 minimum daily balance.
- **Bluest Account:** early direct deposit 2 days; listed foreign ATM withdrawal fee $0; third-party ATM fee rebates up to $50 per month; required opening deposit $75,000 and $112,500 daily balance to maintain benefits. It also has a separate $2 out-of-network ATM withdrawal fee.
- **Gold Years Account:** eligibility begins at age 62; early direct deposit up to 2 days; out-of-network ATM fee $0; foreign ATM fee $3.50 per withdrawal, waived at a $10,000 balance.
- **Green Fee-Free Account:** foreign and out-of-network ATM fees $0, but early direct deposit is 0 days.
- **Evergreen Account:** early direct deposit up to 2 days; foreign ATM fee is 2% of each withdrawal with a $3 minimum.
- **Blue Account:** early direct deposit 1 day; foreign ATM fee is 3% of the USD-equivalent withdrawal with a $5 minimum; its out-of-network fee is 1%, capped at $3; monthly maintenance fee is $20, waived at $625 minimum daily balance; daily ATM limit $500.
- **Green Account (checking):** early direct deposit up to 1 day; foreign ATM fee is 3% of the USD-equivalent withdrawal with a $5 minimum; separate out-of-network ATM fee $3; monthly maintenance fee $22.50, waived at $1,350 minimum daily balance; daily ATM limit $600.

## Required response quality checks

Before responding, ensure that:

- all known customer exclusions are honored;
- the recommended account meets the early-deposit requirement;
- fee minimums are applied per withdrawal, not once for the trip;
- amounts are stated as estimates and rounded to cents;
- operator surcharge and rebate uncertainty is explicit;
- disclosed maintenance fees are not mislabeled as ATM fees;
- no unsupported enrollment, account-opening action, or fee waiver is promised.

If key facts such as withdrawal frequency, amount, or balance are missing, provide a conditional comparison and ask only for the missing facts needed to distinguish the viable options. If all eligible accounts fail a must-have requirement, say so plainly and offer the closest alternatives rather than selecting a noncompliant account.
