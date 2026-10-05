---
name: foreign-atm-checking-cost-comparison
description: Compare personal checking accounts for a customer's planned foreign ATM withdrawals using supplied product documents. Use to make a documented low-cost recommendation, disclose rebates, balance conditions, ATM limits, and conversion markups, and safely transition to account opening only after explicit account-class selection.
---

# Foreign ATM Checking Cost Comparison

Use this Skill when a customer asks which personal checking account is least expensive for international ATM use, asks whether a proposed account is best, or wants a recommendation before opening an account.

Use the current task's supplied product documents, clarification answers, and read-only observations as the source of truth. Do not say that fees or product terms are unavailable when they are present in those materials. Do not invent a typical third-party ATM surcharge: such charges vary by ATM operator and an unknown surcharge cannot support an exact total-cost claim.

## Required comparison dimensions

For each materially comparable account whose terms are documented, identify separately:

1. Rho-Bank foreign-ATM withdrawal fees;
2. third-party ATM operator surcharges;
3. eligible operator-fee rebates, including their monthly cap and posting/eligibility qualifications;
4. monthly maintenance fees and the confirmed waiver condition;
5. product eligibility, opening-deposit, and ongoing-balance conditions;
6. the daily ATM withdrawal limit; and
7. currency-conversion markup, if documented.

A $0 Rho-Bank foreign-ATM fee does not mean an ATM operator charges nothing. Likewise, a rebate is not a guarantee that all operator fees will be eliminated: it is limited to eligible posted fees and the stated monthly cap.

Use exact official account-class names from the product documents. Do not conflate accounts with similar color names or compare a checking account to a different product class.

## Information to derive from the live request

Determine, from the current materials:

- number of trip months;
- planned withdrawal count and amount per month;
- whether withdrawals may be combined on one day, or whether each stated amount is a single daily withdrawal;
- the customer's ability to meet each relevant opening, ongoing-balance, and maintenance-fee-waiver requirement;
- documented account-specific fee formulas, monthly allowances, rebates, limits, and conversion terms; and
- whether actual operator surcharges are known.

If the customer has supplied an amount and count but not exact dates, do not assume multiple withdrawals occur on the same day. State whether the documented daily limit accommodates each planned single withdrawal, and explain that multiple same-day withdrawals must remain within the limit.

Treat an account as unavailable for a recommendation when the customer cannot meet a mandatory age, opening-deposit, eligibility, or required ongoing-balance condition. Explain that conclusion briefly. Do not recommend an otherwise cheaper premium product that the customer has expressly said they cannot qualify for.

## Method

1. Read the supplied account documents and extract the documented terms for viable accounts. Retain the document title or ID internally so material statements are traceable.
2. Exclude accounts that the customer cannot open or maintain under confirmed facts. Do not treat missing eligibility facts as confirmed eligibility.
3. Divide the withdrawal plan by calendar month. Apply each fee formula per withdrawal, monthly free-withdrawal allowance, and operator-fee rebate cap separately for each month.
4. Apply maintenance fees only if a documented fee applies and the customer cannot meet its waiver. Do not add a waived fee.
5. Calculate the known bank foreign-ATM fees. If all operator surcharges are known, calculate net operator charges as `eligible operator fees minus rebates`, never below zero and never above the monthly cap. If operator fees are unknown, report the bank-fee result and maximum possible documented rebate, not a fabricated exact operator-cost total.
6. Where a conversion markup is documented, separately calculate `total converted withdrawal amount × markup percentage`. Label it a conversion/exchange cost rather than a Rho foreign-ATM withdrawal fee. This must be disclosed when making an overall foreign-cash-cost recommendation, even if the customer initially emphasized ATM fees.
7. Check every known withdrawal and daily aggregate against the account's ATM limit. State whether the stated per-withdrawal plan fits.
8. Recommend the eligible product supported by the documented comparison. When two candidates have the same zero bank foreign-ATM fee and only one supplies an applicable positive operator-fee rebate, it is the supported lower-cost choice for operator charges, subject to the unknown surcharge amount and its rebate cap.

## Required customer-facing response

Answer the customer's final question directly when the supplied facts establish a recommendation; do not ask them to re-provide product terms already supplied. A complete response should:

- name the recommended official account class and say why it is the supported lowest-cost eligible option;
- state its Rho foreign-ATM fee, monthly operator-fee rebate cap, and trip-wide maximum rebate (`monthly cap × trip months`);
- explain that operator surcharges are set by third parties, may vary, and amounts above the cap or otherwise ineligible charges remain the customer's cost;
- state the maintenance fee and the confirmed balance needed to waive it;
- state the daily ATM limit and whether the planned individual withdrawal fits it;
- disclose any documented conversion markup and calculate its approximate cost on the stated total withdrawal amount, clearly separated from ATM charges;
- briefly identify why a materially better-looking account is unavailable, where relevant; and
- invite the customer to explicitly select the exact official account class if they want to proceed.

For a plan with unknown operator surcharges, permissible wording is: the account has a known bank-fee total of a stated amount and can rebate *up to* a stated amount per month; the final operator-fee cost is variable. Do not call the maximum rebate a guaranteed saving.

## Deterministic calculation helper

Use `scripts/compare_atm_costs.py` for arithmetic when comparing one or more products. The script uses only the Python standard library, receives one JSON object on stdin, and emits one JSON object on stdout. Populate it only with current task facts and product terms.

### Input schema

```json
{
  "months": [[{"amount": "decimal USD-equivalent", "operator_fee": "optional decimal"}]],
  "daily_totals": [["optional decimal total for each known day"]],
  "products": [{
    "name": "exact official account class",
    "eligible": true,
    "opening_requirements_met": true,
    "daily_atm_limit": "optional decimal",
    "monthly_maintenance_fee": "decimal",
    "maintenance_waived": true,
    "operator_rebate_monthly_cap": "decimal",
    "currency_conversion_markup_percent": "optional decimal",
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

`months` must be a nonempty list. Every withdrawal needs `amount`. To compute an exact operator-fee total, supply `operator_fee` for every withdrawal; otherwise omit it for all withdrawals. Do not mix known and unknown operator fees. `daily_totals`, when known, has one list per month. Tier ceilings are inclusive, ordered ascending, and should end with a `null` ceiling if needed.

The output reports per-product eligibility, Rho foreign-ATM fees, maintenance fees, maximum trip rebate, known net operator fees where possible, conversion-markup amount, known total, and daily-limit warnings. Read top-level and product `errors` before using an output. `total_known_cost` includes documented maintenance and conversion charges but excludes unknown third-party operator charges; it must not be described as an exact final total when `operator_fees_known` is false.

### Runnable call example

Use the Skill runtime to run `scripts/compare_atm_costs.py` with a live JSON object matching the schema, then use its output in the explanation. Do not hardcode a customer identity, account choice, or result from an earlier case in the input.

## Validation checklist

Before responding, confirm that:

- trip duration, withdrawal count, and total withdrawal amount match the customer's stated plan;
- each formula uses the documented base and correct per-transaction or per-month cadence;
- monthly allowances and rebate caps reset each month;
- rebates do not exceed known eligible fees or a monthly cap;
- maintenance-fee treatment matches the customer's confirmed waiver facts;
- a product the customer cannot qualify for is not recommended as actionable;
- the stated individual withdrawal and any known daily total comply with the relevant limit;
- conversion markup is disclosed separately when documented; and
- no unsupported exact third-party surcharge or total is claimed.

## If the customer elects to open an account

A recommendation, a question such as “is that account best?”, or a request for more information is not authorization to open an account. First obtain explicit confirmation of the exact official account class and confirmation to proceed.

Before any account-opening action, use the normal banking tools and current opening procedure to verify identity and authority; verify age; check the number of personal checking accounts; verify that no checking account was closed for cause in the preceding six months; check product-specific eligibility, required opening funding, and ongoing balance commitments; disclose fees and limits; and confirm the selected official account class. Retrieve current account information where required to perform those checks. Only after every prerequisite is verified may the documented opening tool be called. If a prerequisite cannot be verified, do not open the account; explain what is missing.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.
