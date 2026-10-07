---
name: foreign-atm-checking-cost-comparison
description: Compare documented personal checking accounts for a customer's planned international ATM withdrawals. Use this to recommend the lowest supported eligible option, calculate known charges, disclose variable operator fees and conversion costs, and prevent account opening until the customer explicitly selects an official account class.
---

# Foreign ATM Checking Cost Comparison

Use this Skill when a customer asks which personal checking account is cheapest for foreign ATM use, asks whether an account is best for travel, or wants a comparison before opening an account.

Use the supplied product documents, clarification answers, and read-only observations as the source of truth. Product documents supplied with the task are available terms: do **not** say that the catalog, fees, or terms are unavailable, and do not transfer the customer merely because a comparison requires arithmetic.

## Immediate response rule

When the customer has supplied a withdrawal plan and the documents establish an eligible best option, answer the comparison directly in the same customer-facing response. Do not ask again for product terms, balance facts, or trip details already supplied.

Unknown third-party ATM operator surcharges do not block a recommendation. Do not invent a “typical” surcharge or claim an exact final total. Instead, calculate documented bank charges, state the applicable maximum rebate, and explain that the remaining operator-fee cost is variable.

## Gather current facts

From the current request and documents, determine:

- trip months, withdrawals per month, total withdrawal count, and amount per withdrawal;
- total converted withdrawal amount;
- each relevant account's foreign-ATM fee formula, free allowance, operator-fee rebate, maintenance fee, waiver requirement, conversion markup, and ATM limit;
- confirmed eligibility, age, opening-deposit, ongoing-balance, and waiver-balance facts; and
- whether actual operator surcharges are known.

Keep accounts distinct by their exact official account-class name. Do not combine terms from similarly named accounts or different product classes.

## Comparison method

1. Extract documented terms for materially comparable personal checking accounts.
2. Exclude an account from an actionable recommendation if the customer cannot meet a mandatory age, opening-deposit, eligibility, or required ongoing-balance condition. Briefly say why it is unavailable.
3. Apply a foreign-ATM bank fee formula to each withdrawal. Apply free-withdrawal allowances and rebate caps separately for each calendar month.
4. Apply a maintenance fee only when its documented waiver condition is not met. Never add a fee that the customer can and will waive.
5. Treat ATM operator fees as separate third-party charges. A zero bank ATM fee is not a promise of a zero operator surcharge. Rebates apply only to eligible posted operator fees and only up to the stated monthly cap.
6. If a conversion markup is documented, calculate it separately as total foreign-currency withdrawal amount times the markup percentage. It is an exchange/conversion cost, not a foreign-ATM withdrawal fee.
7. Compare each planned withdrawal with the documented daily ATM limit. If dates are unknown, do not assume withdrawals are on the same day; say whether one stated withdrawal fits and that combined same-day withdrawals must stay within the limit.
8. Recommend the eligible account with the lowest supported cost. In particular, where eligible zero-bank-fee accounts are otherwise comparable, an account with a documented positive operator-fee rebate is the supported lower-cost choice for operator charges, subject to the rebate cap and variable surcharge amount.

## Required customer-facing answer

A completed recommendation must include all applicable items below:

- the exact official recommended account class and a direct conclusion that it is the supported lowest-cost eligible option;
- its Rho-Bank foreign-ATM withdrawal fee;
- its eligible ATM-operator-fee rebate cap per month and the maximum cap across the stated trip (`monthly cap × trip months`);
- that operator surcharges are set by third parties, vary by ATM, and amounts above the cap or otherwise ineligible charges remain payable;
- its maintenance fee, the balance required to waive it, and whether the customer has confirmed that condition;
- its daily ATM withdrawal limit and whether the stated individual withdrawal fits it;
- every documented currency-conversion markup and its approximate amount on the customer's stated total withdrawals, explicitly separated from ATM fees;
- why a materially better-looking account is unavailable when relevant; and
- an invitation to select the exact official account class if the customer wants to proceed.

For unknown operator surcharges, say that the known bank-fee total is a stated amount and that eligible operator fees can be rebated **up to** the stated cap. Do not describe a maximum rebate as guaranteed savings or present the known subtotal as an exact final total.

A request such as “Are you sure [account] is best?” is a request for advice, not account-opening authorization. Answer it directly and do not open an account.

## Calculation helper

Use `scripts/compare_atm_costs.py` for repeated arithmetic. It reads one JSON object from standard input and emits one JSON object on standard output. Populate it only with live task facts and documented product terms.

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

`months` is a nonempty list of calendar months. Every withdrawal needs `amount`. To calculate an exact operator-fee result, give `operator_fee` for every withdrawal; otherwise omit it for all withdrawals. Do not mix known and unknown operator fees. `daily_totals`, when supplied, has one list per month.

The result reports bank foreign-ATM fees, maintenance fees, maximum trip rebate, conversion cost, daily-limit warnings, and product errors. Read top-level and per-product `errors` before relying on it. If `operator_fees_known` is false, `total_known_cost` excludes third-party operator charges and must not be called a final total.

### Runnable call example

Run `scripts/compare_atm_costs.py` in the Skill runtime with a current JSON object matching the schema, then use the result to formulate the customer-facing comparison. Do not hardcode a prior customer's identity, selection, or result.

## Validation before responding

Confirm that:

- withdrawal count, trip length, and total withdrawal amount match the live request;
- per-withdrawal fees, monthly allowances, and monthly rebate caps use the correct cadence;
- any rebate does not exceed eligible operator charges or its monthly cap;
- maintenance-fee treatment matches confirmed waiver facts;
- ineligible products are not recommended as actionable;
- conversion markup is disclosed separately when documented;
- each stated withdrawal fits the applicable daily limit, or a limit issue is clearly disclosed; and
- no fabricated operator surcharge or exact total involving unknown operator fees is claimed.

## If the customer explicitly elects to open an account

Do not open an account from a recommendation request, a question about whether an account is best, or an ambiguous preference. First obtain explicit confirmation to open the exact official account class.

Before any account-opening action, use normal banking tools and the current opening procedure to verify customer identity and authority; verify age; check the number of personal checking accounts; verify no checking account was closed for cause in the preceding six months; check account-specific eligibility, opening funding, and ongoing-balance commitments; disclose fees and limits; and confirm the chosen official account class. Retrieve current account information where needed for these checks. Only after every prerequisite is verified may the documented opening tool be called. If any prerequisite cannot be verified, do not open the account and explain what is missing.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.
