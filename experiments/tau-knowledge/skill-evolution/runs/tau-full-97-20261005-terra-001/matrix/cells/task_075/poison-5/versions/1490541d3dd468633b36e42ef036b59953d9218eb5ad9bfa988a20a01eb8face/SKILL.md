---
name: foreign-atm-checking-cost-comparison
description: Compare documented personal checking accounts for a customer's planned international ATM withdrawals, recommend the lowest supported eligible option, explain known and variable costs, and prevent account opening until the customer explicitly selects an official account class.
---

# Foreign ATM Checking Cost Comparison

Use this Skill when a customer asks which checking account is least expensive for foreign ATM withdrawals, asks whether a travel account is best, or requests a comparison before opening an account.

The product documents, clarification answers, and supplied observations are the current source of truth. Treat supplied product documents as available account terms. Do **not** claim that the product catalog or fee schedule is unavailable, and do not transfer the customer merely because the comparison requires arithmetic.

## Mandatory response gate

If the customer has already provided a withdrawal plan and the supplied documents establish enough facts for a supported recommendation, provide the complete comparison in the **next customer-facing response**. Do this even when third-party operator surcharges are unknown.

Do not ask again for facts that are already in the conversation, including trip duration, withdrawal frequency, withdrawal amount, balance capability, or account terms. Do not wait for exact operator surcharges: calculate the documented bank costs and describe the operator-fee result as variable and capped.

A question such as “Is [account] really best?” remains a request for advice, not authorization to open an account. Answer the question; do not call an opening tool.

## Collect live comparison facts

From the current request and supplied documents, identify:

- number of calendar months, withdrawals per month, number of withdrawals, and amount per withdrawal;
- total withdrawal amount using the stated USD equivalent or stated assumption;
- each materially comparable account's foreign-ATM fee formula, free-withdrawal allowance, operator-fee rebate, monthly maintenance fee, waiver rule, currency-conversion markup, and daily ATM limit;
- account eligibility, including confirmed age, opening-deposit, ongoing-balance, and fee-waiver facts; and
- whether third-party ATM operator fees are known.

Keep products separate by exact official account class. Do not merge terms from similarly named accounts.

## Comparison method

1. Exclude an account from an actionable recommendation when the customer cannot satisfy a documented mandatory condition, such as age, required opening deposit, or required ongoing balance. State the specific reason briefly.
2. For every eligible account, calculate the Rho foreign-ATM fee per withdrawal and apply monthly free-withdrawal allowances separately for each calendar month.
3. Apply maintenance fees only if the customer cannot or will not meet the documented waiver condition. Do not add a waived fee.
4. Treat ATM operator surcharges as third-party charges, separate from Rho fees. Never invent a “typical” operator surcharge.
5. Apply operator-fee rebates only to eligible posted operator charges and only up to the documented cap for each month. With unknown operator fees, report the maximum possible rebate across the trip, not guaranteed savings.
6. Calculate a documented currency-conversion markup separately from ATM fees: total withdrawal amount × markup percentage. It is a conversion cost, not a Rho foreign-ATM withdrawal fee.
7. Compare the individual stated withdrawal with the daily ATM limit. If same-day grouping is unknown, do not assume every withdrawal occurs on a separate day; state that each withdrawal fits if it does and that aggregate withdrawals on one day must remain within the limit.
8. Recommend the account with the lowest supported eligible cost. When otherwise comparable eligible zero-Rho-fee accounts differ because only one documents a positive eligible operator-fee rebate, that account is the supported lower-cost recommendation for operator charges, subject to the monthly cap and variable surcharge amounts.

## Required customer-facing response

Lead with a direct conclusion, then show the reasoning. A completed response must include:

1. The exact official recommended account class and the conclusion that it is the supported lowest-cost eligible choice for the stated use.
2. Its Rho foreign-ATM withdrawal fee.
3. Its eligible operator-fee rebate cap per month and the maximum potential rebate over the stated number of months.
4. A clear statement that ATM operator surcharges are imposed by third parties, vary by ATM, may be ineligible, and remain payable above the monthly rebate cap.
5. Its monthly maintenance fee, balance required to waive it, and whether the customer confirmed that they can meet the waiver.
6. Its daily ATM limit and whether one stated withdrawal fits that limit.
7. Every documented currency-conversion markup and its approximate cost on the stated total withdrawal amount, explicitly separate from ATM fees.
8. Why a materially stronger-looking alternative is unavailable, where relevant.
9. A brief contrast with a materially comparable alternative when it helps establish the recommendation.
10. An invitation to explicitly select the exact official account class if the customer wants to proceed.

When operator surcharges are unknown, do not present an exact final total. Say that the known bank-fee subtotal excludes third-party operator charges, and describe rebates as “up to” the documented caps.

### Response structure

Use this structure with current facts rather than copying prior customer information:

> **Recommendation: [Official Account Class].** Based on your [months]-month plan of [withdrawals] foreign ATM withdrawals of about [amount] each, it is the supported lowest-cost eligible option.
>
> - **Rho foreign-ATM fee:** [fee/formula].
> - **Third-party ATM fees:** ATM operators set these separately and their charges vary. [Account] rebates eligible posted operator fees up to [monthly cap] per month—up to [trip cap] across [months] months. Charges above a monthly cap or charges that are not eligible remain your responsibility.
> - **Maintenance fee:** [monthly maintenance fee], waived with [waiver balance]. [Confirmed waiver status].
> - **Conversion cost:** [markup]% above the interbank rate, approximately [computed markup] on about [total withdrawals] of withdrawals. This is separate from ATM fees.
> - **Withdrawal limit:** [daily limit] daily; a single [amount] withdrawal [does/does not] fit. Combined withdrawals in one day must remain within the daily limit.
> - **Comparison:** [Unavailable alternative] is not actionable because [mandatory requirement not met]. [Comparable alternative] has [relevant contrast].
>
> If you want to open **[Official Account Class]**, please explicitly confirm that exact account class. I will then complete the required identity and eligibility checks before any opening action.

## Calculation helper

Use `scripts/compare_atm_costs.py` for repeatable arithmetic. The script receives one JSON object on standard input and emits one JSON object on standard output. Use only live facts and current documented terms.

### Input schema

```json
{
  "months": [
    [{"amount": "decimal USD-equivalent", "operator_fee": "optional decimal"}]
  ],
  "products": [{
    "name": "exact official account class",
    "eligible": true,
    "daily_atm_limit": "optional decimal",
    "monthly_maintenance_fee": "decimal",
    "maintenance_waived": true,
    "operator_rebate_monthly_cap": "decimal",
    "currency_conversion_markup_percent": "decimal",
    "foreign_atm_fee": {
      "type": "zero|flat|percent_min|percent_max|free_allowance_then_flat",
      "amount": "required for flat or free_allowance_then_flat",
      "rate_percent": "required for percent_min or percent_max",
      "minimum": "required for percent_min",
      "maximum": "required for percent_max",
      "free_withdrawals": "required for free_allowance_then_flat"
    }
  }]
}
```

`months` contains one list per calendar month. Each withdrawal requires `amount`. Supply `operator_fee` for every withdrawal only when every operator fee is known; otherwise omit it from all withdrawals. The helper rejects mixed known/unknown operator-fee input.

The output contains per-product Rho ATM fees, maintenance fees, conversion costs, the maximum trip rebate, whether a final total is known, and daily-limit warnings. If `total_cost_known` is false, `total_known_cost` excludes all third-party operator fees and is not a final total.

### Runnable call example

Run `scripts/compare_atm_costs.py` in the Skill runtime with a JSON object matching the schema. Read any `errors` before relying on a result, then use the calculated values in the customer-facing response.

## Validate before responding

Confirm all of the following:

- the trip length, withdrawal count, and total withdrawal amount match the current request;
- fee formulas, free allowances, and rebate caps use the correct per-withdrawal or per-month cadence;
- no rebate exceeds either eligible known operator fees or its monthly cap;
- maintenance fee treatment matches the customer's confirmed waiver facts;
- any unavailable product is not recommended as actionable;
- conversion markup is disclosed separately when documented;
- the individual withdrawal is checked against the daily limit;
- unknown operator charges are not fabricated or folded into a claimed final total; and
- the response actually names the recommendation and gives the documented numerical rationale.

## If the customer explicitly elects to open an account

Do not open an account from a comparison request, an inquiry about whether an account is best, or an ambiguous preference. Obtain explicit confirmation to open the exact official account class first.

Before any account-opening action, use normal banking tools and the current opening procedure to verify customer identity and authority; verify age; check that the customer has no more than four personal checking accounts; verify no checking account was closed for cause in the previous six months; check account-specific eligibility, opening funding, and ongoing-balance commitments; disclose fees and limits; and confirm the chosen official account class. Retrieve current account information when needed. Only after every prerequisite is verified may the documented opening tool be called. If any prerequisite cannot be verified, do not open the account and explain what is missing.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.
