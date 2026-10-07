---
name: international-atm-checking-cost-comparison
description: Compare personal checking accounts for expected domestic or foreign ATM use, including maintenance fees, withdrawal fees, allowances, rebates, eligibility constraints, limits, and unknown third-party surcharges. Use for informational product recommendations; do not use to open, alter, or transact on an account.
---

# International ATM Checking Cost Comparison

Provide a transparent, evidence-based cost comparison for a customer's planned ATM withdrawals. This Skill is for product information and recommendations only. It does not perform banking actions.

## Required inputs

Collect or use the supplied conversation and product documents to establish:

- Trip/usage duration in whole or partial months, expected withdrawals per month, and expected amount per withdrawal.
- Whether withdrawals are foreign/international, where that distinction matters.
- The customer's ability to meet each account's opening, balance, age, or other eligibility requirements.
- For each candidate account: monthly maintenance fee and waiver condition; ATM fee formula or allowance; ATM-operator-fee rebate and cap; relevant daily withdrawal limit; and whether third-party operator surcharges remain possible.
- Known operator surcharge, if available. Do not invent one.

Do not conflate a bank's foreign transaction fee with its foreign ATM withdrawal fee. Treat ATM-operator surcharges as third-party costs unless the product evidence says the bank rebates them.

## Method

1. Exclude accounts the customer cannot open or whose quoted benefits require conditions the customer cannot meet. Explain the reason without implying that an account has been opened.
2. Check the planned single withdrawal and expected daily use against each applicable ATM limit. A limit does not itself establish a fee.
3. Determine the bank fee for every planned withdrawal. Apply an allowance per stated period (normally each month), fee tiers, percentage/minimum or maximum rules, and maintenance-fee waivers exactly as documented.
4. Calculate the maintenance cost only after evaluating the waiver condition. Multiply recurring costs by the trip duration.
5. If operator surcharges are known, include them and subtract only documented, eligible rebates up to their stated cap. If they are unknown, keep them explicitly unknown rather than estimating them.
6. Compare both known bank cost and exposure to unknown third-party charges. State a conditional break-even when a rebate account could be cheaper only above a known surcharge level.
7. Recommend the account that best fits the customer's stated eligibility and low-cost preference. For uncertainty-averse customers, distinguish a guaranteed low bank-cost choice from an account that may be cheaper only if unrevealed third-party fees are sufficiently high.

Use `scripts/compare_atm_costs.py` for arithmetic when account facts have been normalized into its JSON schema. The script does not retrieve product facts, decide eligibility, or take actions.

## Script interface

Run `scripts/compare_atm_costs.py` with JSON on stdin:

```json
{
  "months": 3,
  "withdrawals_per_month": 6,
  "withdrawal_amount": 350,
  "operator_surcharge_per_withdrawal": null,
  "accounts": [
    {
      "name": "Account label from current evidence",
      "eligible": true,
      "eligibility_note": "optional reason if not eligible",
      "monthly_maintenance_fee": "0",
      "maintenance_fee_waived": true,
      "daily_atm_limit": "500",
      "foreign_atm_fee": {"type": "flat", "amount": "0"},
      "free_foreign_withdrawals_per_month": 0,
      "operator_fee_rebate_cap_per_month": "0"
    }
  ]
}
```

`foreign_atm_fee.type` may be `flat`, `percentage_minimum`, `percentage_maximum`, or `tiers`. For `tiers`, supply ascending `up_to` thresholds (or `null` for the final tier) and `amount` values. For percentage types, supply `rate_percent` and the applicable `minimum` or `maximum`. Monetary values are decimal strings or JSON numbers in one currency. `operator_surcharge_per_withdrawal` is a nonnegative amount or `null` when unknown.

The script emits JSON with eligibility, limit warnings, bank-cost totals, and—when an operator surcharge is supplied—operator charges, rebates, and total estimated cost. When it is unknown, it emits known bank costs and an explicit unknown-operator-cost status.

## Response format

Give the customer a concise recommendation followed by:

- Planned usage assumptions.
- A small comparison of eligible accounts, showing maintenance cost, bank foreign-ATM cost, and known total for the full period.
- The treatment of third-party operator fees and any monthly rebate cap.
- Why excluded accounts do not qualify.
- Applicable limit confirmation and a reminder that operator fees can be charged by the ATM owner.

Cite the current product evidence by product/document title in prose. Do not claim an exact all-in total when operator surcharges are unknown. Do not create an account, move money, or represent product availability beyond the provided evidence.

## Validation

Before responding, verify that recurring monthly fees and allowances reset at the documented cadence, that waivers reflect the customer's stated ability to qualify, that per-withdrawal fees are applied to each withdrawal, and that rebates never exceed either eligible operator charges or the documented cap. Flag invalid or incomplete inputs instead of silently assuming a value.
