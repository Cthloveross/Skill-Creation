---
name: foreign-atm-checking-cost-comparison
description: Compare documented personal checking accounts for planned foreign ATM withdrawals, separate bank charges from third-party surcharges, make a conditional recommendation when costs are unknown, and prevent account opening until the customer expressly chooses an official account class.
---

# Foreign ATM Checking Cost Comparison

Use this Skill when a customer asks which personal checking account will minimize costs for international ATM withdrawals, requests a travel-account comparison, or asks whether a particular account is best before opening it.

Treat the supplied product documents, customer clarifications, and read-only observations as current evidence. Do not say that fee terms are unavailable when they are supplied. Do not transfer the customer merely because a comparison requires arithmetic.

## Response timing and opening boundary

When the customer has provided a withdrawal plan and the documents support a comparison, give the documented comparison in the next customer-facing response. Do not ask again for facts already supplied, including travel duration, withdrawal frequency, amount, balance capability, or unknown operator surcharges.

A request such as “Is Purple Account best?” is a request for advice, **not** an instruction to open an account. Never open an account unless the customer expressly confirms that they want to open the exact official account class.

## Gather comparison inputs

Use current facts to identify:

- the number of calendar months, withdrawals in each month, amount per withdrawal, and total withdrawal amount;
- each candidate account's foreign-ATM fee, monthly maintenance fee and waiver, operator-fee rebate rule, currency-conversion markup, and daily ATM limit;
- documented eligibility and whether the customer meets required opening deposits, age rules, ongoing balance requirements, and maintenance-fee waiver conditions; and
- whether third-party ATM operator charges are known.

Keep similarly named products distinct. Do not borrow a fee, limit, or feature from another account class.

## Comparison rules

1. Exclude accounts with unmet mandatory eligibility, opening-deposit, or ongoing-balance requirements from an actionable recommendation. Briefly explain why.
2. Compute bank foreign-ATM fees using the documented per-withdrawal formula and reset any free-withdrawal allowance each calendar month.
3. Include a maintenance fee only if the applicable documented waiver condition is not met. Do not add a fee that the customer can waive.
4. Treat ATM-owner/operator surcharges as third-party fees, separate from bank foreign-ATM fees. Never invent a “typical” surcharge.
5. Apply an operator-fee rebate only to eligible posted operator fees and only up to its cap in each calendar month. If operator fees are unknown, state the maximum possible rebate over the trip, not guaranteed savings.
6. Calculate a documented conversion markup separately: total withdrawal amount multiplied by the documented markup percentage. It is not a foreign-ATM withdrawal fee.
7. Check each stated withdrawal against the daily ATM limit. If withdrawal timing is unknown, do not assume withdrawals occur on separate days; combined same-day withdrawals must also remain within the limit.
8. Do not treat an undocumented charge as zero. State that the supplied materials do not establish that term.

## Conditional recommendations

Unknown third-party surcharges can make the total-cost result conditional. In particular, an account with an eligible operator-fee rebate may offset more operator fees, while another zero-bank-ATM-fee account may have a lower documented conversion cost. Explain the tradeoff rather than declaring a categorical winner without support.

For a customer who can waive both maintenance fees, compare the documented incremental costs. For example, if one account has a documented conversion markup and another comparable account has no documented rebate and no documented conversion markup, say:

- the rebate account can be preferable when eligible operator fees rebated over the trip outweigh its documented conversion markup; but
- the other account can be cheaper when operator fees are low or ineligible, subject to any terms the supplied materials do not establish.

Do not claim that a rebate cap is a guaranteed refund. Do not call an account's undocumented conversion markup zero.

## Required customer-facing content

Provide a direct answer followed by the numbers. A completed comparison must include:

1. The exact official names of the materially comparable account classes.
2. Each comparable account's documented Rho foreign-ATM fee.
3. The recommended account or a clearly conditional recommendation, with the reason and uncertainty stated.
4. A clear distinction between Rho fees and variable third-party ATM operator surcharges.
5. Each relevant operator-fee rebate cap per month and maximum potential rebate over the stated trip; describe it as “up to” and eligible-only.
6. The maintenance fee and waiver threshold for relevant accounts, plus whether the customer can meet the applicable waiver.
7. Each documented conversion markup and its calculated cost on the stated withdrawal total, stated separately from ATM fees.
8. Relevant daily ATM limits and whether one planned withdrawal fits.
9. Any unavailable otherwise-attractive account and its unmet mandatory requirement.
10. A request for explicit confirmation of the exact official account class only if the customer wishes to proceed with opening.

When operator fees or other material terms are not documented, do not state an exact final total. Label a subtotal as known/documented costs and state what it excludes.

### Applied-response pattern

Use current facts, not copied example values:

> **Comparison:** [Account A] and [Account B] both have [documented bank foreign-ATM fee].
>
> - **[Account A]:** [foreign-ATM fee]; eligible posted operator-fee rebates of up to [monthly cap] each month, or up to [trip cap] during this trip; [conversion markup and calculated cost]; [maintenance waiver]; [daily limit].
> - **[Account B]:** [foreign-ATM fee]; [documented rebate status]; [maintenance waiver]; [documented or not-established conversion-term status]; [daily limit].
> - **Result:** Because operator surcharges vary and are unknown, the lowest total is conditional. [Account A] is preferable if [eligible rebate condition]; [Account B] can cost less if [low/ineligible-fee condition]. Third-party operator fees above a cap, or not eligible for a rebate, remain payable.
> - **Eligibility:** [Any excluded account] is not actionable because [unmet mandatory requirement].
>
> If you want to open **[exact official account class]**, explicitly confirm that choice. I will then complete the required checks before any opening action.

## Calculation helper

Use `scripts/compare_atm_costs.py` for deterministic arithmetic. It reads one JSON object from standard input and writes one JSON object to standard output. It performs no banking action.

### Input schema

```json
{
  "months": [
    [{"amount": "decimal USD-equivalent", "operator_fee": "optional decimal"}]
  ],
  "products": [
    {
      "name": "exact official account class",
      "eligible": true,
      "daily_atm_limit": "optional decimal",
      "monthly_maintenance_fee": "optional decimal",
      "maintenance_waived": true,
      "operator_rebate_monthly_cap": "optional decimal",
      "currency_conversion_markup_percent": "optional decimal",
      "foreign_atm_fee": {
        "type": "zero|flat|percent_min|percent_max|free_allowance_then_flat",
        "amount": "required for flat/free_allowance_then_flat",
        "rate_percent": "required for percent_min/percent_max",
        "minimum": "required for percent_min",
        "maximum": "required for percent_max",
        "free_withdrawals": "required for free_allowance_then_flat"
      }
    }
  ]
}
```

Each entry in `months` is one calendar month. Supply `operator_fee` for every withdrawal only if all operator fees are known; otherwise omit it for every withdrawal. Omit an optional product field when the material does not establish it; the output marks that cost category as not established rather than assuming zero.

The helper returns documented foreign-ATM fees, maintenance fees, documented conversion costs, maximum rebate ceilings, per-withdrawal limit warnings, and a documented-cost subtotal. With unknown operator fees or omitted material cost fields, that subtotal is not an exact total.

### Runnable call

Run `scripts/compare_atm_costs.py` with a JSON object matching the schema, inspect top-level and per-product `errors`, and use its totals only together with the documented-status fields in the response.

## Validate before responding

Confirm that:

- duration, withdrawal count, and total amount match the current request;
- monthly allowances and monthly rebate caps reset correctly;
- waived maintenance fees were not included;
- no operator surcharge was estimated or presented as guaranteed reimbursed;
- documented conversion markups are separate from ATM fees;
- undocumented terms were not converted into zero-dollar assumptions;
- each stated withdrawal was checked against the documented daily limit;
- every excluded account has a documented unmet requirement; and
- the response names the comparable accounts and gives a supported conditional or categorical conclusion.

## If the customer expressly elects to open an account

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For a personal checking opening, first verify identity and authority; verify the customer is at least 18; verify they do not exceed four personal checking accounts; verify no checking account was closed for cause in the prior six months; verify account-specific eligibility, opening funding, ongoing-balance commitments, fees, and limits; and obtain confirmation of the exact official account class. Retrieve current account information when necessary. Only after every prerequisite is verified may the documented opening tool be called. If a prerequisite is missing or fails, do not open the account and explain what is needed.
