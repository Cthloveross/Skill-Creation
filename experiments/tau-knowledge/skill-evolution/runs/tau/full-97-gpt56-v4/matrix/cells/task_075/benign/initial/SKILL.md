---
name: international-atm-checking-selection-and-opening
description: Compare available personal checking accounts for a customer's expected foreign ATM use, disclose bank versus third-party costs, recommend the lowest eligible cost option, and complete account opening only after required identity and eligibility checks. Use for checking-account selection/opening requests involving ATM fees or travel.
---

# International ATM Checking Selection and Opening

Use this Skill when a customer wants a new personal checking account and cost of foreign or out-of-network ATM withdrawals is important. It supports a transparent recommendation and the controlled opening workflow.

## Inputs and assumptions

Collect or use information already supplied in the conversation:

- expected ATM withdrawals per month and trip duration (or a single monthly period),
- whether withdrawals are foreign, out-of-network, or both,
- known account eligibility constraints and balance/opening-deposit constraints,
- ability to meet any fee-waiver balance, and
- whether the customer has stated a desired account class or accepts the recommendation.

Do **not** treat ATM-operator surcharges as known unless the customer provides an amount. Bank fees and operator surcharges are distinct. A bank's waiver condition is only counted if the customer says they can meet it for every applicable statement cycle.

The product facts available in `references/checking_atm_catalog.md` are a limited catalog, not a substitute for an account-specific disclosure. Do not infer undocumented fees, eligibility, rebates, or limits.

## Selection workflow

1. Identify feasible accounts. Exclude an account when the customer cannot satisfy a required opening deposit or a condition necessary to receive the quoted benefits. Keep a monthly fee only when its waiver condition cannot be met.
2. Calculate the Rho-Bank ATM and maintenance cost for the stated period. Do not include unknown third-party surcharges in a numeric total. If an account rebates operator fees, describe the cap separately and never promise a rebate for an unknown or ineligible charge.
3. Use `scripts/compare_atm_costs.py` for repeatable calculations when account parameters are known. It accepts only supplied figures and reports bank fees, maintenance fees, and a deterministic total.
4. Recommend the feasible account with the smallest deterministic total. State the key assumptions, the relevant fee rule, and ties or unknown operator-fee effects. Mention daily ATM withdrawal limits if the planned withdrawal amount or frequency may exceed one.
5. Ask a focused follow-up only for information needed to compare feasibility or calculate a cost. If enough information exists, make the recommendation rather than continuing to question the customer.

For a customer who also asks to open an account, explain the recommendation and then move to the opening workflow. The recommendation alone does not open an account.

## Personal checking opening workflow

Follow every item below before opening:

1. Identify the customer using a user ID, exact customer name, or email and use the corresponding normal customer-information tool. Never guess identity data.
2. Verify the customer by having them confirm at least two of the four identity fields: date of birth, email, phone number, and address. Compare against the retrieved customer record.
3. Obtain the current timestamp with `get_current_time`, then call `log_verification` with the complete retrieved customer record and that timestamp. Only do this after the two-field confirmation succeeds.
4. Confirm all opening eligibility requirements: customer is verified, at least 18, has no more than four personal checking accounts, and has no checking account closed for cause within the past six months. Ask for or use only supported information; do not claim an unavailable check was performed.
5. Confirm the desired `account_class`. It must be the full official personal-checking name ending in `Account`. If the customer has clearly asked to open the account you recommended, confirm that exact official name before opening when there is any ambiguity.
6. Unlock the specialized agent tool named `open_bank_account_4821`, then call it using exactly the argument schema it exposes. Use it only after the preceding verification, eligibility, and account-class checks. Report the actual result, not an assumed success.

If verification, eligibility, account choice, or a required tool field is missing, do not open the account. Tell the customer exactly what is needed next. Do not transfer merely because ordinary information is missing. Do not use scripts as a substitute for a bank action.

## Customer-facing response standard

Keep the explanation brief but include: recommended account, deterministic bank cost over the stated period, any unavoidable maintenance fee, operator-surcharge caveat, and relevant balance assumption. For an opening request, state whether the account was opened or what prerequisite remains. Do not claim operator fees will be waived unless the actual account rule and cap support it.

## Calculator

Run `scripts/compare_atm_costs.py` by sending JSON on stdin. It emits JSON on stdout.

Example input schema (illustrative values only):

```json
{
  "months": 2,
  "withdrawals_per_month": 4,
  "accounts": [
    {
      "name": "Example Account",
      "monthly_maintenance_fee": "10.00",
      "maintenance_fee_waived": true,
      "free_foreign_withdrawals_per_month": 1,
      "foreign_withdrawal_fee_after_free": "3.00"
    }
  ]
}
```

Fields:

- `months`: nonnegative whole number.
- `withdrawals_per_month`: nonnegative whole number; the calculation assumes this amount occurs in each month.
- `accounts`: nonempty list. Each account has `name`, `monthly_maintenance_fee`, `maintenance_fee_waived`, `free_foreign_withdrawals_per_month`, and `foreign_withdrawal_fee_after_free`.
- Monetary amounts may be JSON numbers or decimal strings and must be nonnegative.

Output contains one `results` item per account with `maintenance_fees`, `bank_atm_fees`, `deterministic_total`, and `charged_withdrawals_per_month`, all monetary amounts represented as two-decimal strings. `lowest_deterministic_total` lists all tied account names. The result excludes third-party ATM charges, rebates, currency conversion, and any fee not represented by input fields.

Validate that the period and withdrawal count match the customer statement, that ineligible accounts were excluded before comparison, and that every quoted total explicitly excludes unknown ATM operator charges.
