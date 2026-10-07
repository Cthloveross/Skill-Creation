---
name: travel-checking-account-opening
description: Recommend and open an eligible personal checking account for a customer seeking lower ATM costs, especially for international travel. Use when the customer wants a checking-account comparison or asks to open a checking account; verifies identity, documents eligibility, separates bank fees from third-party charges, and performs the opening only after the exact account class is confirmed.
---

# Travel Checking Recommendation and Opening

## Scope and safe-use rule

Use this Skill for personal checking recommendations and opening requests. It supports a recommendation but does not itself open an account. The executor must use the normal banking tools for all banking actions.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

Do not treat a profile lookup as identity verification. Do not open an account based solely on a recommendation, a partial product name, or the customer's statement that they are eligible.

## Inputs to gather

Collect or confirm:

- The authenticated customer's identity and authority to open an account for themself.
- Requested account type (this Skill is for `checking`).
- Exact desired official `account_class`, including the ending `Account` where applicable.
- For travel-cost comparisons: trip duration in months, anticipated withdrawals per month, amount per withdrawal, whether withdrawals will be foreign and/or out-of-network, and the expected minimum daily balance.
- Whether the comparison is limited to Rho-Bank fees or must include third-party ATM operator surcharges. If operator fees are unknown, explicitly keep them outside the quantified total.
- Any product-specific eligibility facts, such as age or opening-deposit requirements.

## Identity and authority verification

1. Locate the candidate profile with an identifier supplied by the customer, such as their name or email, using the appropriate profile lookup tool.
2. Ask the customer to provide or confirm at least two of these four fields: date of birth, email, phone number, and address. Compare them to the returned profile. A name alone is not one of the two required fields.
3. Confirm the requester is the account holder or otherwise has authority to request the opening. Do not proceed for an unverified third party.
4. After two profile fields match, get the current time and call `log_verification` with every required field from the matched profile and that timestamp.
5. If fewer than two fields match, profiles conflict, or authority is unclear, stop and request the missing verification; do not disclose additional profile data or take the banking action.

## Eligibility check for a personal checking account

After identity verification and before an opening action:

1. Unlock and call `get_all_user_accounts_by_user_id_3847` with the authenticated `user_id`.
2. Inspect returned account records, including account type, account class, status, balances, and relevant dates or closure metadata.
3. Confirm all of the following:
   - The customer is verified.
   - The customer is at least 18 years old.
   - The customer has fewer than four existing personal checking accounts, so the new account remains within the four-account limit.
   - No checking account was closed for cause during the preceding six months.
   - The selected product's own requirements are met.
4. Do not infer a closure reason or closure date from missing data. If the account response does not establish the closed-for-cause requirement, do not open the account. Explain that eligibility cannot yet be verified and use the institution's appropriate internal resolution or escalation path.
5. If any requirement fails, do not call the opening tool. State the specific failed requirement without exposing unrelated account information.

## Cost-comparison method

Use `references/travel_checking_products.md` only for documented product facts. Do not invent a fee, waiver, rebate, or eligibility rule when the documentation is silent.

1. Determine which fees actually apply to the requested usage. Foreign-ATM fees and out-of-network fees may be separate fees; include both only when the product documentation says both apply to that transaction type.
2. Calculate scheduled Rho-Bank charges over the stated period:
   - monthly maintenance fees, considering only a waiver the customer can meet;
   - each applicable ATM fee;
   - known monthly withdrawal allowances and monthly rebates.
3. Keep third-party ATM operator fees separate. These charges may be unknown and are not controlled by Rho-Bank. Do not call an option the guaranteed lowest *total* cost when operator surcharges are unknown.
4. Check each requested withdrawal against the documented daily ATM limit. If more than one withdrawal may occur in a 24-hour period, obtain the maximum daily withdrawal plan before saying the limit will be met.
5. The helper may calculate documented bank-fee totals. It does not determine product eligibility, decide whether overlapping fee types both apply, or authorize an account opening.

### Calculation helper

`scripts/compare_travel_atm_costs.py` reads one JSON object from standard input and emits one JSON object to standard output. It performs no banking action.

Input schema:

```json
{
  "months": 3,
  "withdrawals_per_month": 4,
  "withdrawal_amount": "200.00",
  "candidates": [
    {
      "name": "Example Account",
      "monthly_maintenance_fee": "10.00",
      "maintenance_waived": false,
      "daily_atm_limit": "500.00",
      "atm_fee_components": [
        {"kind": "percent_min", "rate": "0.03", "minimum": "5.00"}
      ]
    }
  ]
}
```

Each candidate has a name, nonnegative monthly maintenance fee, `maintenance_waived` boolean, optional daily ATM limit, and zero or more fee components. Supported component kinds are:

- `flat`: `amount` per withdrawal.
- `percent_min`: `rate` multiplied by the withdrawal amount, subject to `minimum` per withdrawal.
- `percent_max`: `rate` multiplied by the withdrawal amount, subject to `maximum` per withdrawal.
- `allowance_flat`: `free_per_month` withdrawals followed by `amount` per withdrawal in that month.

The result has `valid`, `results`, and, on invalid input, `errors`. Each valid candidate result reports its maintenance total, ATM-fee total, scheduled bank-fee total, and warnings. Amounts are decimal strings rounded to cents. The output excludes third-party operator charges and does not model rebates; model a rebate manually only after its eligibility and cap are established.

## Opening procedure

Only after verification, eligibility, product requirements, and exact account selection are complete:

1. Restate the exact official account class and obtain the customer's affirmative confirmation. For example, do not convert a shorthand product reference into an account class without confirmation.
2. Unlock `open_bank_account_4821`.
3. Call it with the authenticated customer ID, `account_type` set to `checking`, and the exact confirmed `account_class`.
4. Report only the returned account details and the relevant known fees, limits, balance conditions, and third-party-fee caveat. Do not fabricate an account number, opening deposit, activation status, or success result.

## Important decision outcomes

- **Unknown operator surcharge:** provide the scheduled Rho-Bank-fee comparison and say that final total cost may differ because operator fees are unknown.
- **Known balance-waiver condition not met:** include the maintenance fee; do not assume the waiver.
- **Withdrawal exceeds a daily limit:** explain that the planned withdrawal cannot be supported by that option without changing the plan.
- **Product has an unmet age, opening-deposit, or other documented requirement:** exclude it from eligible recommendations and do not open it.
- **Customer has not selected the exact official account class:** ask for confirmation before the opening action.
- **Eligibility record incomplete or negative:** stop before opening; do not work around the missing eligibility evidence.

## Completion checklist

Before finalizing, ensure the interaction record supports: two-field identity verification and a verification log; authority; account retrieval; all four checking eligibility requirements; product eligibility; exact account-class confirmation; and the opening tool result. If no tool call was appropriate, clearly state what prerequisite remains instead of implying an account was opened.
