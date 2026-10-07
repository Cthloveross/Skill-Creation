---
name: personal-checking-foreign-atm-optimizer
version: 1.0.0
description: Compare personal checking accounts for projected foreign-ATM bank fees, verify a customer's eligibility, and open a confirmed eligible account using the normal banking account-opening tool. Use when a customer wants a new personal checking account and foreign ATM costs are relevant.
---

# Personal Checking Foreign-ATM Optimizer

Use this workflow to recommend and, only after all prerequisites are satisfied, open a personal checking account. Product terms and customer facts must come from the current task context and normal banking tools; never assume that a product is available, that a customer is eligible, or that a quoted fee applies to a different account variant.

## Safety and action prerequisites

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For opening a personal checking account, do not call an account-opening tool until all of the following are established:

1. **Identity and authority:** Locate the customer using a supplied identifier. Ask the customer to provide or confirm at least two identity fields (date of birth, email address, phone number, or address); compare them against the customer record. Do not reveal the stored values merely to obtain confirmation. After two fields match, obtain the current time and call `log_verification` with the complete record and timestamp.
2. **Age:** Calculate the customer's age from the verified date of birth and the current date. The customer must be at least 18.
3. **Personal-checking eligibility:** Determine, from the appropriate normal account/history lookup if available, whether the customer currently has no more than four personal checking accounts and no checking account closed for cause within the prior six months. If a required lookup is unavailable, request the customer's attestation; do not substitute credit-card, referral, or transaction searches for a checking-account lookup.
4. **Product eligibility:** Check stated opening-deposit, minimum-balance, geographic, or other product-specific requirements. Distinguish a fee waiver threshold from an opening-deposit requirement.
5. **Explicit account selection:** Explain the recommendation and request confirmation of the exact official `account_class` to open. The account class must be the complete official product name ending in `Account`. A preference such as "the cheapest one" is not a confirmation if more than one product can be cheapest or the exact class is unclear.

If any prerequisite fails or remains unknown, do not open an account. State what is missing and ask the narrowest needed question.

## Fee-comparison method

1. Confirm the comparison scope: bank foreign-ATM fees only, or total account cost including maintenance fees. Treat ATM-owner/operator surcharges as separate unless the customer supplies an estimate and the product specifically provides a rebate.
2. Gather the trip duration, expected foreign withdrawals per month, approximate USD-equivalent amount per withdrawal, expected maintained balance, and any required opening deposit.
3. Build a product input list from current product documents. For each product, capture its foreign-ATM fee rule, free monthly allowance, monthly maintenance fee and waiver condition, rebates, withdrawal limit, and any opening requirement.
4. Run `scripts/compare_foreign_atm_costs.py` with those facts. The script calculates only deterministic bank-fee projections; it does not establish eligibility or authorize an action.
5. Explain ties and assumptions. In particular, a zero bank foreign-ATM fee does not mean an ATM operator will not charge a surcharge. Do not claim a rebate amount without an eligible surcharge estimate.
6. Recommend an eligible product with the lowest cost in the requested scope. If products tie on foreign-ATM bank fees, use disclosed recurring fees and achievable waiver requirements as a secondary comparison only when the customer has asked for total cost or this is necessary to select one account.

## Opening procedure

After verification, eligibility, product checks, and explicit confirmation:

1. Unlock the normal banking tool `open_bank_account_4821` with `unlock_discoverable_agent_tool`.
2. Inspect the unlocked tool's required argument schema and call it via `call_discoverable_agent_tool` using only the verified customer identifier and the customer-confirmed full official account class, plus any fields the tool requires.
3. Never invent tool arguments. If the tool reports a validation or eligibility failure, do not retry with altered details; explain the failure and request the needed correction or transfer when appropriate.
4. Report the successful account opening, selected account class, and material fee/limit assumptions. Do not promise reimbursement of third-party ATM charges unless the applicable product terms say so.

## Calculator interface

Run the packaged script with JSON on stdin (or `run_skill_script`) using this schema:

```json
{
  "months": 3,
  "withdrawals_per_month": 4,
  "usd_per_withdrawal": "200.00",
  "maintained_daily_balance": "500.00",
  "include_maintenance": true,
  "products": [
    {
      "name": "Official Product Name Account",
      "foreign_atm_fee": {
        "kind": "percent_min",
        "percent": "3",
        "minimum": "5.00"
      },
      "monthly_maintenance_fee": "10.00",
      "maintenance_waiver_min_daily_balance": "250.00",
      "foreign_atm_rebate_cap_per_month": "0.00"
    }
  ]
}
```

`foreign_atm_fee.kind` is one of:

- `zero`
- `flat` (requires `amount`; optional `free_withdrawals_per_month`)
- `percent_min` (requires percentage `percent` and USD `minimum`)

All money fields are decimal strings. `percent` is a percentage such as `3` for 3%, not a fraction. The output includes per-product foreign-ATM fees, optional maintenance fees, a rebate estimate only when an eligible surcharge estimate is provided, and total projected bank cost.

Validate before relying on a result: `months` and withdrawal count must be non-negative integers; withdrawal amount and money fields must be non-negative; product names must be nonempty; fee kinds must have their required fields; and the output must contain one result per input product with two-decimal monetary strings. An invalid input produces JSON with `ok: false` and no recommendation.

Example runnable call (illustrative values only):

```json
{"months":1,"withdrawals_per_month":1,"usd_per_withdrawal":"100.00","products":[{"name":"Example Account","foreign_atm_fee":{"kind":"zero"}}]}
```

Use the output as an explanation aid, then complete the verification and confirmation workflow above before any opening action.
