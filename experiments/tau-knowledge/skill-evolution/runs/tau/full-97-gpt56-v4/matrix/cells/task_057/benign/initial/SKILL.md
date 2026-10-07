---
name: no-overdraft-checking-recommendation
version: 1.0.0
description: Recommend an eligible personal checking account when a customer prioritizes avoiding overdraft charges, explain the relevant tradeoffs accurately, and preserve the required selection and eligibility checks before opening an account.
---

# No-overdraft checking recommendation

Use this Skill when a customer asks which checking account best fits a strict preference for no overdraft fees, including before they have selected an account class.

## Method

1. Identify whether the customer means **no account overdraft fee only** or an absolute preference for **no overdraft-related charges or transfers**.
2. For an absolute preference, recommend **Green Account (checking)**:
   - it has no overdraft fees and no overdraft coverage or linked-account overdraft transfers;
   - a transaction that exceeds available funds is declined rather than overdrawing the account;
   - its overdraft-transfer fee is $0.00.
3. Do not describe Blue Account as equivalent for an absolute no-fee preference. Although its account overdraft fee is $0.00, optional overdraft-protection transfers cost $12.50 each if enabled.
4. Check age restrictions before suggesting Light Green Account as an alternative: it is only for primary holders age 13 through 24.
5. Disclose material non-overdraft tradeoffs for the recommendation when useful: Green Account (checking) has a $22.50 monthly maintenance fee, waived by maintaining a $1,350 minimum daily balance; paper statements cost $2.50 monthly.
6. Ask the customer to explicitly confirm the exact official class name, **“Green Account (checking)”**, if they want to proceed. A recommendation is not account-opening consent.

For a concise response, say why Green Account (checking) meets the stated priority, explain that attempted transactions beyond available funds will be declined, mention the monthly-fee condition, and ask whether the customer wants that exact account.

## Before opening after selection

Do not open an account merely because it was recommended. Follow the account-opening procedure:

1. Obtain the customer's exact selected `account_class`, using the full official name ending in `Account`.
2. Verify identity by confirming two of date of birth, email, phone number, and address; obtain the current time and create the required verification log.
3. Retrieve all customer bank accounts with `get_all_user_accounts_by_user_id_3847`.
4. Confirm the customer is verified, at least 18, has no more than four personal checking accounts, and has no checking account closed for cause in the previous six months.
5. Only if all requirements pass, use the declared normal banking account-opening tool (`open_bank_account_4821`, after unlocking it if required by the runtime).

If a required fact, account class, or identity confirmation is missing, ask for it rather than assuming it. If eligibility fails, explain the applicable requirement and do not attempt account opening.

## Optional deterministic helper

`scripts/recommend_checking.py` accepts JSON on stdin and emits JSON on stdout.

Input schema:

```json
{
  "requires_no_overdraft_related_charges": true,
  "age": 31
}
```

- `requires_no_overdraft_related_charges` is required and must be boolean.
- `age` is optional; when supplied it must be a nonnegative integer.

The output includes a recommendation, customer-facing rationale, and alternatives that should not be presented as equivalent. Run it with a JSON object and use its `customer_message` as a factual draft; tailor it only with facts actually known in the live conversation.

Example invocation in a compatible script runtime:

```sh
printf '%s' '{"requires_no_overdraft_related_charges":true,"age":31}' | python3 scripts/recommend_checking.py
```

Validate that `recommended_account_class` is present before relying on the result. The script intentionally returns no recommendation for preferences outside its supported no-overdraft scope.
