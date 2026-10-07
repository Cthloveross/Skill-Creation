---
name: foreign-atm-checking-cost-comparison
description: Compare personal checking accounts for a planned pattern of foreign ATM withdrawals, including account fees, monthly operator-fee rebates, balance/eligibility constraints, and daily limits. Use for a recommendation or before beginning an account-opening workflow; it does not itself open an account.
---

# Foreign ATM Checking Cost Comparison

Use this Skill when a customer wants the lowest-cost checking account for international ATM use, or asks to validate a prior ATM-fee recommendation. Calculate only charges supported by the supplied product materials. Do not invent a “typical” ATM-operator surcharge: operator fees vary by machine and are separate from bank fees.

## Scope and distinction of costs

For every candidate account, separately identify:

1. the bank's foreign-ATM fee;
2. third-party ATM-operator surcharges;
3. documented operator-fee rebates and their monthly cap;
4. account monthly maintenance fees and whether the customer can satisfy a documented waiver; and
5. any relevant currency-conversion markup, only if the customer asks for total cash-access/conversion cost rather than ATM fees alone.

A $0 bank foreign-ATM fee does **not** mean that third-party ATM operators charge nothing. A rebate is not a waiver: calculate it only against known eligible operator fees and never beyond the stated period cap.

Do not conflate similarly named products. Use the exact official `account_class` in the product source and retain citations/document IDs for every material term.

## Required inputs and fact collection

Collect or derive, from the current task materials at runtime:

- planned withdrawals by month, including amount and currency/USD equivalent used for the applicable fee formula;
- whether multiple planned withdrawals may occur on the same day (or daily totals), so daily ATM limits can be checked;
- account-specific foreign ATM fee schedule, rebate terms, daily ATM limit, maintenance fee, and waiver criterion;
- whether the customer meets product eligibility, opening-deposit requirements, ongoing balance requirements, and any fee waiver;
- operator surcharges if known. If unknown, state that total out-of-pocket operator cost cannot be estimated exactly;
- whether the customer seeks ATM fees only or all foreign cash-access costs.

Treat an account as unavailable if the customer cannot meet a mandatory eligibility, opening, or benefit-preservation condition. Do not portray an unavailable premium account as the recommendation merely because its published fee is lower.

## Procedure

1. Identify the exact account products from the supplied materials. Exclude products the customer cannot open or cannot use under required conditions, explaining why.
2. Convert the withdrawal plan into a monthly list. Check each transaction and, where available, each daily aggregate against the product's daily ATM withdrawal limit. If dates/daily aggregates are unknown, flag that limit compliance cannot be fully established.
3. Calculate each product's bank fee from its documented formula on each withdrawal. Apply monthly free-withdrawal allowances and rebate caps separately for each month.
4. Add maintenance fees only when the customer cannot meet their waiver or when the product has a non-waivable fee. Do not add a fee that documented facts say is waived.
5. If operator fees are known, compute per-month `operator fees − eligible rebate`, floored at zero. If they are unknown, report bank-fee totals, the maximum documented rebate, and the fact that operator-fee total remains unknown.
6. Recommend an eligible account only when the available evidence supports it. A product with the same $0 bank fee as another product and an applicable positive operator-fee rebate weakly dominates the other on ATM fees, provided all other relevant conditions are met and both face the same operator surcharges.
7. Give a concise customer-facing conclusion with assumptions, the three-month/other requested totals, relevant cap and limit, and the distinction between bank fees and operator fees. Do not claim exact third-party costs without surcharge data.
8. Do not open an account based on a recommendation or an informational question. Obtain an explicit choice of the exact account class and confirmation to proceed first.

## Calculation helper

Run `scripts/compare_atm_costs.py` through the Skill runtime for deterministic arithmetic. It uses only the Python standard library and accepts JSON on stdin and emits JSON on stdout.

### Input schema

```json
{
  "months": [[{"amount": "decimal amount", "operator_fee": "optional decimal"}]],
  "daily_totals": [["optional decimal total for each known day"]],
  "can_meet_maintenance_waiver": true,
  "products": [{
    "name": "exact account class",
    "eligible": true,
    "opening_requirements_met": true,
    "daily_atm_limit": "optional decimal",
    "monthly_maintenance_fee": "decimal",
    "maintenance_waived": true,
    "operator_rebate_monthly_cap": "decimal",
    "foreign_atm_fee": {
      "type": "zero|flat|percent_min|percent_max|tiered|free_allowance_then_flat",
      "amount": "required for flat/free_allowance_then_flat",
      "rate_percent": "required for percent_min/percent_max",
      "minimum": "required for percent_min",
      "maximum": "required for percent_max",
      "free_withdrawals": "required for free_allowance_then_flat",
      "tiers": [{"up_to": "decimal or null", "fee": "decimal"}]
    }
  }]
}
```

`months` is required and must contain at least one month. `operator_fee` must be supplied for every withdrawal to produce an exact operator-fee total; omit it for all withdrawals when unknown. Do not mix known and unknown operator fees within a calculation. Tier boundaries are inclusive and must be sorted ascending, with the final tier normally having `up_to: null`.

The helper output contains one entry per product: eligibility status, bank fees, maintenance fees, known operator fees less rebates when available, total ATM cost when determinable, maximum rebate, and daily-limit warnings. Monetary output is rounded to cents using conventional half-up rounding.

### Runtime call

Invoke the packaged script with a JSON object matching the schema above, for example through the runtime's `run_skill_script` facility with `relative_path` set to `scripts/compare_atm_costs.py`. Populate it solely from the live task facts and product documents. Read `errors` in the result before relying on any total; correct missing or inconsistent inputs rather than guessing.

## Validation checklist

Before responding, verify that:

- the number of withdrawals and number of months match the customer's plan;
- every fee formula is calculated on the documented base (for example, USD equivalent when specified);
- free allowances and rebate caps reset each month, not over the whole trip;
- rebates never exceed actual known eligible operator fees or the monthly cap;
- monthly maintenance treatment matches the confirmed balance/waiver facts;
- ineligible or unaffordable accounts are not recommended as actionable choices;
- individual and known daily withdrawal totals comply with stated ATM limits; and
- the response does not claim an unsupported estimate for third-party operator fees.

## If the customer elects to open an account

Recommendation is read-only. Before an account-opening action, use the normal banking tools and the current product/opening procedure. Confirm customer identity and authority; obtain explicit confirmation of the exact official account class; retrieve the customer's accounts to check account count, status, balance/tenure where relevant, and closures-for-cause requirement; confirm age and all product-specific eligibility/opening requirements; confirm required funding and balance commitments; disclose relevant fees and limits; and only then use the documented account-opening tool. If any prerequisite cannot be verified, do not open the account; explain what is missing or request the required confirmation. Log identity verification only after the required identity-field confirmation procedure succeeds.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.
