---
name: open-personal-checking-account
description: Authenticate a customer, verify personal-checking eligibility, compare documented checking products when needed, and open the customer's confirmed checking account with the normal banking tool.
---

# Open a Personal Checking Account

Use this skill for a request to open a personal checking account, including a request for help choosing an account first. Use only product terms, fees, limits, and eligibility rules supplied in the current task documentation.

## Required prerequisites

Before opening an account, establish and retain these facts:

1. **Identity and authority:** Identify the customer and authenticate them under the available verification process. A customer requesting an account for themselves establishes the purpose; do not act for an unverified third party.
2. **Age:** The customer must be at least 18 on the opening date.
3. **Checking-account limit:** The customer must not exceed four personal checking accounts.
4. **Closure history:** The customer must have no checking account closed for cause in the past six months.
5. **Selection and consent:** The customer must confirm the exact desired personal checking `account_class` and consent to opening it.
6. **Product-specific conditions:** Explain and check any documented account-specific age, deposit, balance, or other requirements that are conditions for the requested product.

Do not invent stricter requirements than the supplied procedure. When the task's approved clarification history already establishes a prerequisite, retain and use that established fact rather than asking the same question again. If a required fact is absent, ambiguous, or adverse, pause the opening and obtain or resolve it through the approved workflow.

## Identity verification

Look up a customer using the available approved lookup tool (by supplied email, exact name, or user ID). A lookup result alone is not authentication.

When the runtime provides `log_verification`, authenticate by obtaining confirmation of two profile fields from date of birth, email, phone number, and address. Then:

1. Obtain the current timestamp with `get_current_time`.
2. Call `log_verification` with the complete returned customer profile and that timestamp.
3. Treat identity as verified only after the verification log succeeds.

If the current task's public history explicitly states that verification was already completed, preserve that status and do not duplicate the process unless the runtime requires a fresh verification.

## Product comparison

First identify the customer's needs (such as travel, foreign ATM withdrawals, expected ATM operator surcharges, direct-deposit timing, and feasible balances). Explain that total ATM cost can include the bank fee, third-party operator surcharge, and any rebate cap; a $0 bank ATM fee does not eliminate third-party charges.

Use these documented comparisons when applicable:

| Account | Relevant travel/direct-deposit features | Material condition |
|---|---|---|
| Purple Account | $0 foreign ATM withdrawal fee, up to $30/month global ATM-fee rebates, eligible direct deposit up to 2 days early | $15 monthly fee waived by a $3,750 minimum daily balance; $2.50 out-of-network withdrawal fee where applicable |
| Bluest Account | $0 foreign ATM withdrawal fee, up to $50/month ATM-fee rebates, direct deposit 2 days early | $75,000 opening deposit and $112,500 daily balance to retain benefits |
| Gold Years Account | $3.50 foreign ATM fee per withdrawal, waived at a $10,000-or-more balance; direct deposit up to 2 days early | Available only to customers at least 62 |
| Evergreen Account | Foreign ATM fee of 2%, $3 minimum, per withdrawal; direct deposit up to 2 days early | Third-party ATM fees may also apply |
| Blue Account | Foreign ATM fee is the greater of 3% of the USD equivalent or $5 | $500 daily ATM withdrawal limit |
| Green Account (checking) | Foreign ATM fee is the greater of 3% of the USD equivalent or $5 | $600 daily ATM withdrawal limit |

For a customer requiring two-day early direct deposit who cannot meet Bluest's stated balance requirements, Purple Account is a documented $0-bank-foreign-ATM-fee option. Disclose Purple's monthly fee/waiver condition, its $30 rebate cap, and possible operator fees. Do not claim an unsupported universal lowest-cost outcome.

## Opening workflow

1. Identify and authenticate the customer, and record successful verification when the runtime supplies that process.
2. Confirm the customer is 18 or older. Use the supplied date of birth and current opening date where available.
3. Check the personal-checking count and closure-for-cause requirement. Use approved account records if they are available and required by the runtime; otherwise obtain the required affirmative customer confirmations. Do not silently assume either fact.
4. Discuss only relevant documented product options and material fees, limits, and funding/balance conditions.
5. Obtain a final, explicit selection and consent. Capture the complete official account class exactly as selected, such as `Purple Account` or `Green Account (checking)`.
6. Evaluate the general conditions with `scripts/checking_eligibility.py` when using the script is supported. Do not proceed if its `eligible` output is false.
7. Open the account immediately once all prerequisites and consent are established. Use the normal banking action:

```text
open_bank_account_4821(
  user_id=<authenticated customer user ID>,
  account_type="checking",
  account_class=<exact confirmed official class>
)
```

If specialized tools must be unlocked in the runtime, unlock `open_bank_account_4821` and invoke it through the runtime's discoverable-agent-tool mechanism using the same three arguments. This is an agent action; never ask the customer to call the banking tool.

8. Wait for the tool result and preserve its association with the opening call. State that the account was opened only after a successful result. Provide returned account details when available and restate material account conditions or direct-deposit setup steps.

## Failures and incomplete information

- If identity, age, account-limit status, closure history, exact selection, consent, or product eligibility is not established, do not open the account.
- If the opening result fails, is declined, or is unavailable, do not claim success. Explain the returned issue and follow the approved remediation or escalation path.
- Do not retry a state-changing opening request unless the tool result and approved procedure explicitly establish that retry is safe.
- Do not replace an official account class with an abbreviation or invented product name.

## Eligibility helper

`scripts/checking_eligibility.py` reads one JSON object from stdin and writes one JSON object to stdout.

Required input fields:

```json
{
  "verified": true,
  "personal_checking_count": 0,
  "closed_for_cause_past_6_months": false,
  "account_class": "Official Account Name",
  "selection_confirmed": true,
  "date_of_birth": "MM/DD/YYYY",
  "as_of": "YYYY-MM-DD"
}
```

Instead of `date_of_birth` and `as_of`, callers may provide a nonnegative integer `age`. Success output is:

```json
{"eligible": true, "age": 30, "reasons": []}
```

On malformed input it emits `eligible: false`, `age: null`, an `error` value of `invalid_input`, and explanatory reasons. Proceed only when `eligible` is `true`. The helper evaluates supplied general facts; it does not authenticate the customer, prove product availability, or perform the bank action.
