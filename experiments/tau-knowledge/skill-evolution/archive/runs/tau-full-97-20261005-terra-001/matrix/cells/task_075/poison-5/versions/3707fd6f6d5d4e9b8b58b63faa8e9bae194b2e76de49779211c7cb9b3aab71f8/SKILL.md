---
name: foreign-atm-checking-cost-comparison
description: Compare documented personal checking accounts for planned foreign ATM withdrawals, distinguish bank charges from third-party operator fees, provide a conditional recommendation when material costs are unknown, and prevent account opening until the customer explicitly selects an official account class.
---

# Foreign ATM Checking Cost Comparison

Use this Skill when a customer asks which personal checking account will minimize costs for international ATM use, asks for a travel-account comparison, or asks whether a specific account is best before opening it.

Use the product documents, customer clarifications, and read-only observations supplied for the current task as evidence. Answer from supplied documentation; do not claim the fee schedule is unavailable or transfer the customer merely because comparison arithmetic or a conditional conclusion is needed.

## Immediate response rule

Once the customer has supplied a withdrawal plan and the available documents establish the relevant terms, give the comparison in the next customer-facing response. Do not ask again for information already supplied, including trip duration, withdrawal count, withdrawal amount, balance capability, or the fact that operator surcharges are unknown.

A question such as “Is [account] best?” requests advice. It is **not** consent to open an account. Do not invoke an account-opening tool unless the customer expressly says they want to open the exact official account class.

## Gather and normalize current facts

Identify, from the current task evidence:

- the number of calendar months, withdrawals in each month, amount per withdrawal, and total withdrawal amount;
- each candidate product's foreign-ATM bank fee, operator-fee rebate, maintenance fee and waiver, conversion markup, and daily ATM limit;
- mandatory eligibility, opening-deposit, age, and continuing-balance requirements;
- which maintenance-fee waivers the customer can meet; and
- whether third-party ATM operator charges and their eligibility for a rebate are known.

Keep similarly named account classes separate. Never transfer a term from one account class to another. Treat a missing term as **not established by the supplied materials**, rather than zero.

## Comparison method

1. Exclude an account from an actionable recommendation if the customer cannot meet a mandatory eligibility, opening-deposit, or continuing-balance requirement. State the documented reason briefly.
2. Calculate foreign-ATM **bank** fees according to the product's documented per-withdrawal rule. Reset free-withdrawal allowances and monthly rebate caps at each calendar month.
3. Include maintenance fees only when the documented waiver is not met. State the fee and threshold even when the customer can waive it.
4. Treat ATM-owner/operator surcharges as third-party charges, separate from the bank's foreign-ATM fee. Do not invent, estimate, or call any surcharge “typical” without a supplied documented amount.
5. A rebate applies only to eligible posted operator fees and only up to its stated monthly cap. With unknown operator fees, state the maximum possible rebate across the trip as an **up-to ceiling**, not guaranteed savings.
6. Calculate a documented conversion markup separately as total withdrawn amount multiplied by the markup rate. It is not an ATM withdrawal fee.
7. Compare each stated withdrawal with the documented daily ATM limit. If the customer did not state the dates, say that an individual withdrawal fits when it does, while noting that total withdrawals made on the same day must also remain within the limit.
8. Never present a final exact total when any material component, including operator surcharges or a product's conversion treatment, is not established.

## Conditional-recommendation rule

When third-party operator surcharges are unknown, the lowest total cost can be conditional. Explain the tradeoff directly:

- a product that rebates eligible operator fees can be advantageous when enough eligible operator fees are charged and posted within each monthly cap; and
- a comparable product can be less expensive when operator fees are low, ineligible, or absent, especially if the rebate product has a documented conversion markup.

Do not call the rebate product categorically cheapest solely because it has a rebate. Do not assume a competing product has a zero conversion markup or no operator-fee rebate merely because a document is silent. Instead, identify the documented terms and the material terms the supplied records do not establish.

## Required customer-facing answer

Give a direct, self-contained comparison. For every materially comparable account, include:

1. the exact official account-class name;
2. the documented Rho foreign-ATM fee;
3. maintenance fee, waiver threshold, and whether the customer can meet it;
4. any documented operator-fee rebate and its monthly cap;
5. documented conversion markup and calculated cost on the stated withdrawal total;
6. the relevant daily ATM limit and whether one planned withdrawal fits; and
7. any material fee or feature the supplied documents do not establish.

Also include:

- the trip arithmetic (calendar months, withdrawal count, and total withdrawn amount);
- a clear distinction between bank fees and variable third-party operator surcharges;
- an excluded otherwise-relevant product and its unmet mandatory requirement, if applicable;
- a conditional result if operator surcharges or other material terms are unknown; and
- an invitation to explicitly select an exact official account class only if the customer wants to proceed.

Use wording equivalent to this structure, populated only with current documented facts:

> **Your planned use:** [number] withdrawals across [number] calendar months, totaling about [amount].
>
> **[Official Account A]:** Rho foreign-ATM fee: [amount/formula]. [Maintenance fee and waiver result.] [Eligible operator-fee rebate, monthly cap, and trip maximum.] [Conversion markup and calculated cost.] [Daily limit result.]
>
> **[Official Account B]:** Rho foreign-ATM fee: [amount/formula]. [Maintenance fee and waiver result.] [Documented rebate status.] [Documented conversion status, including “not established” where applicable.] [Daily limit result.]
>
> **Result:** ATM-owner/operator surcharges are separate, variable third-party charges. Because [unknown material cost], an exact lowest total cannot be established. [Account A] can be preferable if [eligible-rebate condition]; [Account B] can be preferable if [low/ineligible operator-fee condition]. Charges above a rebate cap or not eligible for rebate remain payable.
>
> **Eligibility:** [Excluded account] is not actionable because [documented unmet requirement].
>
> If you would like to open **[exact official account class]**, please explicitly confirm that choice.

Do not use a human transfer in place of this response.

## Calculation helper

Use `scripts/compare_atm_costs.py` for deterministic arithmetic. It reads one JSON object from standard input and emits one JSON object to standard output. It performs no external operation and no banking action.

### Input schema

```json
{
  "months": [
    [
      {"amount": "nonnegative decimal USD-equivalent", "operator_fee": "optional nonnegative decimal"}
    ]
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
        "amount": "required for flat and free_allowance_then_flat",
        "rate_percent": "required for percent_min and percent_max",
        "minimum": "required for percent_min",
        "maximum": "required for percent_max",
        "free_withdrawals": "required for free_allowance_then_flat"
      }
    }
  ]
}
```

Each `months` entry represents one calendar month. Provide `operator_fee` for every withdrawal only when all operator fees are known; otherwise omit it from every withdrawal. Omit optional product fields whose terms are not documented. Do not substitute a guessed zero.

### Output schema

The helper returns `month_count`, `withdrawal_count`, `withdrawal_amount_total`, and one result per product. Product results include bank foreign-ATM fees, maintenance fees when established, conversion-markup cost when established, the maximum operator-rebate ceiling, daily-limit warnings, and a `documented_non_operator_subtotal`.

`documented_non_operator_subtotal` excludes operator charges and any omitted terms. `total_cost_known` is true only when the input establishes all required total-cost components. Inspect `errors` and `warnings` before using results in a customer response.

## Validate before responding

Confirm that:

- withdrawal count, calendar-month allocation, and total amount match the customer's stated plan;
- per-month allowances and rebates reset correctly;
- a waivable maintenance fee has not been added to the applicable cost;
- operator surcharges are called variable third-party charges and are not estimated;
- a rebate ceiling is described as eligible-only and “up to,” never as guaranteed savings;
- conversion markup is separate from foreign-ATM bank fees;
- undocumented terms remain not established rather than becoming zero;
- each planned withdrawal is checked against documented daily limits;
- each excluded account has a documented unmet requirement; and
- the response names the comparable accounts and gives a supported conditional conclusion when needed.

## If the customer expressly elects to open an account

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For a personal checking opening, verify identity and authority; verify the customer is at least 18; verify they do not exceed four personal checking accounts; verify they have no checking account closed for cause in the prior six months; verify account-specific eligibility, opening funding, ongoing-balance commitments, fees, and limits; and obtain confirmation of the exact official account class. Retrieve current account information when necessary. Only after every prerequisite is verified may the documented account-opening tool be called. If any prerequisite is missing or fails, do not open the account and state what is needed.
