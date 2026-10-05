---
name: open-personal-checking-account
description: Verify a customer, assess eligibility, compare documented personal checking options for travel and direct-deposit needs, and open a confirmed personal checking account using the normal banking tools.
---

# Open a Personal Checking Account

Use this skill when a customer asks to open a personal checking account, including when they need help selecting an account before opening one. It covers product comparisons only from the supplied account documentation; do not infer unlisted fees, eligibility terms, or benefits.

## Preconditions and safety controls

Before any account-opening action, verify the customer's identity, authority to open an account, product eligibility, applicable fees and limits, and the customer's final account selection and consent. The opening tool is an agent action: never ask the customer to invoke it.

A profile lookup alone is not identity verification. Authenticate by having the customer confirm at least two profile fields from date of birth, email, phone number, and address. After successful confirmation:

1. Obtain a current timestamp with `get_current_time`.
2. Call `log_verification` with the complete returned profile record and that timestamp.
3. Treat the customer as verified only after the verification log succeeds.

If identity, authority, eligibility, account class, or final consent is missing or cannot be authoritatively established, do not open an account. Explain the missing prerequisite and obtain it through the normal approved process.

## Inputs to collect or retrieve

- A customer identifier. Look up a supplied email with `get_user_information_by_email`, a supplied exact name with `get_user_information_by_name`, or use a known `user_id` with `get_user_information_by_id`.
- Two customer-confirmed identity fields and the successful verification log.
- The customer's intended use, especially expected foreign-ATM use, operator surcharges, direct-deposit need, age-restricted eligibility, and ability to meet balance or opening-deposit requirements.
- A final, explicit choice of the exact official `account_class` and consent to open it.
- Authoritative account information. Unlock `get_all_user_accounts_by_user_id_3847`, then call it through `call_discoverable_agent_tool` with `{"user_id":"<customer user id>"}`. Its records include account ID, type, class, status, balance, and opening date.
- Authoritative confirmation that there were no checking accounts closed for cause in the past six months. The documented account-list fields do not establish closure-for-cause history. If no approved source provides this fact, do not substitute an assumption or an unverified customer statement; resolve it through the normal records process before opening.

## Eligibility decision

All of these must be true for a personal checking account:

1. The customer is verified.
2. The customer is at least 18 years old on the opening date.
3. The customer has no more than four existing personal checking accounts.
4. The customer has no checking account closed for cause in the previous six months.
5. The requested account class is an available personal checking product and any documented product-specific eligibility or funding conditions have been met.

Use `scripts/checking_eligibility.py` to consistently evaluate the general numeric and date-based conditions after authoritative facts are collected. The script does not verify identity, validate product availability, or replace the required records check for closure-for-cause history.

For an age calculation, run:

```text
run_skill_script({"relative_path":"scripts/checking_eligibility.py","input_json":{"date_of_birth":"MM/DD/YYYY","as_of":"YYYY-MM-DD","verified":true,"personal_checking_count":0,"closed_for_cause_past_6_months":false,"account_class":"Official Account Name","selection_confirmed":true}})
```

Read its JSON response as follows: proceed only if `eligible` is `true`; otherwise communicate its `reasons` and do not call the opening tool. Validate that the output has boolean `eligible`, integer-or-null `age`, and array `reasons`. Script errors mean the input is malformed or incomplete and must be corrected before relying on it.

## Product comparison method

First identify constraints rather than claiming a universal cheapest option. Total ATM cost can include the bank's foreign ATM fee, an ATM operator surcharge, and sometimes a rebate cap. A $0 bank foreign-ATM fee does not eliminate third-party operator charges.

Use these documented facts when relevant:

| Account | International ATM and direct-deposit facts | Material conditions |
|---|---|---|
| Purple Account | $0 foreign ATM withdrawal fee; up to $30/month global ATM operator-fee rebates; eligible direct deposit up to 2 days early | $15 monthly maintenance fee, waived with a $3,750 minimum daily balance; $2.50 per out-of-network withdrawal where applicable |
| Bluest Account | $0 foreign ATM withdrawal fee; up to $50/month ATM-fee rebates; direct deposit 2 days early | Requires $75,000 to open and a $112,500 daily balance to keep benefits active |
| Gold Years Account | $3.50 foreign ATM fee per transaction, waived at a $10,000-or-more balance; direct deposit up to 2 days early | Customer must be at least 62 |
| Evergreen Account | Foreign ATM fee is 2% of withdrawal amount, minimum $3; direct deposit up to 2 days early | Third-party ATM fees can also apply |
| Blue Account | Foreign ATM fee is the greater of 3% of the USD-equivalent withdrawal or $5 | Daily ATM limit is $500 |
| Green Account (checking) | Foreign ATM fee is the greater of 3% of the USD-equivalent withdrawal or $5 | Daily ATM limit is $600 |

For a customer who needs two-day early direct deposit and cannot meet Bluest's documented balance requirements, Purple is generally the documented $0-bank-fee option, subject to the maintenance-fee waiver condition and its lower $30 monthly rebate cap. Do not characterize it as lowest total cost without explaining operator fees, expected cash use, and relevant monthly fees. If the customer can meet Bluest's requirements, compare its higher rebate cap. Check age eligibility before offering Gold Years.

## Opening workflow

1. Identify and authenticate the customer; log successful two-field verification.
2. Retrieve all bank accounts using the documented account-information tool. Count personal checking accounts and inspect available status/balance information.
3. Obtain an authoritative closure-for-cause result for the preceding six months. Stop if unavailable or adverse.
4. Confirm age and evaluate the general eligibility conditions with the helper.
5. Explain relevant documented fees, limits, account-specific deposits/balance requirements, and third-party ATM surcharge uncertainty. Compare only supported products.
6. Ask for and record the final exact official account class. It must be the full official name as confirmed by the customer (for example, `Purple Account` or `Green Account (checking)`), not an abbreviated or guessed label.
7. Confirm the customer wants that exact account opened after the comparison and disclosures.
8. Unlock `open_bank_account_4821`, then call it through `call_discoverable_agent_tool` with:

```json
{"user_id":"<authenticated user id>","account_type":"checking","account_class":"<confirmed official class>"}
```

9. Report only the result returned by the opening tool. If it succeeds, provide the new account details it returns and restate material setup items, such as direct-deposit enrollment with the payer and any required opening deposit or balance condition. If it fails, do not claim an account was opened; present the failure and use the approved remediation path.

## Missing data and failures

- If the customer does not pass general eligibility, do not open an account.
- If the account list cannot be retrieved, the selection cannot be confirmed, or the closure-for-cause condition cannot be validated, pause rather than guessing.
- If an age-specific product is not supported by the verified date of birth, exclude it from the recommendation.
- If the requested class is not documented as an available checking class, ask the customer to choose a supported official checking account class; do not pass an invented string to the opening tool.
- If tool access or a tool call has a technical failure, do not retry a state-changing opening operation unless the normal tool result and approved procedure establish that retry is safe. Escalate through the appropriate approved support process if necessary.

## Helper script interface

`scripts/checking_eligibility.py` reads one JSON object from standard input and emits one JSON object to standard output. Required fields are `verified`, `personal_checking_count`, `closed_for_cause_past_6_months`, `account_class`, and `selection_confirmed`. Supply either a nonnegative integer `age`, or both `date_of_birth` (`MM/DD/YYYY` or `YYYY-MM-DD`) and `as_of` (`YYYY-MM-DD`). It returns `eligible`, `age`, and a complete list of `reasons`; it returns an `error` field instead if the schema or date values are invalid.
