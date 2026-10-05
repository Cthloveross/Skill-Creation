---
name: personal-checking-account-guidance
version: 1.0.0
description: Recommend a personal checking account when overdraft costs or overdraft behavior matters, then safely complete (or pause) a personal checking opening request after identity verification and eligibility checks.
---

# Personal Checking Account Guidance and Opening

Use this Skill when a customer wants a personal checking account, wants an account recommendation, or wants to open an additional personal checking account.

## Product guidance for overdraft-sensitive customers

First distinguish between an **overdraft fee**, an **overdraft-protection transfer fee**, and whether an attempted transaction is declined instead of being covered. Do not describe a $0 overdraft fee as meaning that all overdraft-related services are free or that every transaction will be approved.

For a customer whose priority is avoiding overdraft fees and avoiding overdraft coverage, recommend **Green Account (checking)** as the best-supported fit in the available product information:

- Transactions that would make the available balance negative are declined at authorization.
- There are no automatic overdraft-protection transfers.
- The overdraft-protection transfer fee is $0.00.
- A separate description notes that a buffer of up to $5 may be considered for minor final-amount differences. Explain that authorization behavior can depend on available balance and final settlement; the customer should keep sufficient funds available.

Give a short, accurate comparison if helpful:

- **Blue Account** has a $0.00 overdraft fee, but optional overdraft-protection transfers cost $12.50 per transfer if enabled. It is not the cleanest recommendation when the customer wants no overdraft-related charges.
- **Light Blue Account** has $0.00 monthly maintenance, overdraft, and overdraft-protection transfer fees. Available information does not establish the same decline-at-authorization behavior as Green Account (checking).
- **Green Fee-Free Account** has a $0.00 overdraft fee, but has a $22.50 monthly maintenance fee unless its $150 minimum-daily-balance waiver condition is met.

Do not open an account merely because the customer asks for a recommendation. Ask the customer to explicitly select a full official account class after receiving the recommendation. Preserve punctuation and qualifiers in the class name (for example, `Green Account (checking)`).

## Required opening workflow

An account may be opened only after every prerequisite below is satisfied:

1. **Identify, then verify the customer.** A name or email lookup identifies a record but is not identity verification. Ask the customer to confirm at least two of: date of birth, email, phone number, and address. Compare them with the retrieved customer record.
2. Obtain the current time with `get_current_time` and call `log_verification` only after two fields have been correctly confirmed. Supply all fields required by that tool using the retrieved record and the current timestamp.
3. Retrieve all bank accounts. Unlock `get_all_user_accounts_by_user_id_3847` through `unlock_discoverable_agent_tool`, then call it through `call_discoverable_agent_tool` with the verified customer `user_id`.
4. Confirm that the customer is at least 18 on the opening date.
5. Confirm the customer currently has **fewer than four** personal checking accounts. This ensures that opening the additional account does not exceed the four-account maximum.
6. Confirm there has been no checking account closed for cause during the preceding six calendar months. If the account response does not expose enough status, closure date, or cause information to make this determination, do not treat it as a pass and do not open the account. Explain the outstanding eligibility confirmation and follow the available authorized internal process.
7. Confirm the customer has explicitly selected a full official personal-checking account class. Do not infer a selection from a recommendation or use a shortened product name.
8. Only when all checks pass, unlock `open_bank_account_4821` and call it using the exact schema disclosed when it is unlocked. Do not invent parameters or substitute another account-opening tool.

Use `scripts/assess_opening_eligibility.py` to calculate age, account-count eligibility, the six-calendar-month closure window, and a structured go/no-go decision. It is decision support only: it does not verify an identity, retrieve accounts, confirm a product catalog, or open an account.

## Handling incomplete requests

- If the customer only asks which account fits, provide the recommendation and ask for their explicit product selection plus the two identity confirmations needed for verification.
- If account data or closure-for-cause information is missing, clearly state that the account cannot yet be opened; do not make an unsupported eligibility determination.
- If the customer chooses a product that is not confirmed as an official full account class, ask them to provide or confirm the exact official name before continuing.
- Do not claim the account was opened until the opening tool reports success.

## Runtime script

Run:

```text
python3 scripts/assess_opening_eligibility.py < input.json
```

The script reads one JSON object from stdin and emits one JSON object on stdout. Its input schema is documented in the script. A result of `decision: "eligible"` is still only one prerequisite: the executor must also have actually logged successful identity verification and must use the unlocked opening tool.

## Output validation before opening

Before calling the opening tool, verify all of the following are true:

- `identity_verified` is true because two customer-confirmed fields matched and `log_verification` succeeded.
- The eligibility script returns `decision` of `eligible`.
- `age_years` is at least 18.
- `personal_checking_count` is below 4.
- `recent_for_cause_closures` is 0 and closure history was explicitly confirmed.
- `desired_account_class` is present and was confirmed as an official full account class.
- The customer has explicitly selected that class.

See `references/personal_checking_policy.txt` for the product and policy facts used by this Skill.
