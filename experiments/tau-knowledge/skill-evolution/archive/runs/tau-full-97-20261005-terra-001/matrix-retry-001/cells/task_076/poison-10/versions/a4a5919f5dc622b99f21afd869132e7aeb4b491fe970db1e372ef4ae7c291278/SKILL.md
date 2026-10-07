---
name: travel-checking-account-opening
description: Recommend and open a personal checking account for a customer who prioritizes international ATM use and early direct deposit. Use when the customer has selected an account and authorized opening, or needs a documented comparison before authorizing it.
---

# Travel Checking Account Recommendation and Opening

Use this skill for personal checking-account recommendations and openings. It separates product comparison from the banking action and does not cause any banking action by itself.

## Runtime inputs

Collect or obtain at runtime:

- Customer name, email, or authenticated `user_id`.
- Two customer-provided identity fields from date of birth, email, phone number, and address.
- Travel/cash-use expectations: months, foreign ATM withdrawals per month, and expected withdrawal amount (USD equivalent when comparing dollar-denominated fees).
- Whether early direct deposit is required and the number of days desired.
- Balance and opening-deposit constraints.
- The customer’s explicit selection and authorization to open an account.

Use account data returned at runtime to check eligibility; do not infer eligibility solely from a customer statement.

## Documented comparison facts

For the documented options:

- **Purple Account**: 0% foreign transaction fee; no Rho-Bank foreign ATM withdrawal fee; ATM operator-fee rebates up to $30 per month; early direct deposit up to 2 days early; $15 monthly maintenance fee, waived with a $3,750 minimum daily balance; daily ATM withdrawal limit $1,000.
- **Blue Account**: a $20 monthly maintenance fee, waived with a $625 minimum daily balance; foreign ATM fee is 1% of the withdrawal amount, capped at $3 per withdrawal; early direct deposit is up to 1 day early; daily ATM withdrawal limit $500.
- **Bluest Account**: requires a $75,000 opening deposit and a $112,500 daily balance to maintain benefits. Do not recommend it to a customer who cannot meet those requirements.

Explain that third-party ATM operator surcharges may still apply. Purple’s rebate is limited to eligible posted operator fees and capped at $30 each month. Do not claim a precise operator-fee total unless the customer supplies it.

Use `scripts/compare_travel_options.py` for repeatable estimates. The result compares only documented Rho-Bank fees and documented monthly maintenance fees; it is not a guarantee of total travel cost.

### Runnable comparison example

```json
{"months":2,"withdrawals_per_month":4,"withdrawal_amount_usd":300,"can_maintain_blue_waiver_balance":true,"can_maintain_purple_waiver_balance":false,"requires_two_day_early_deposit":true}
```

Run with `run_skill_script` using `scripts/compare_travel_options.py`. Review that `validation.valid` is `true` before using the estimates. For the stated example inputs, Purple is eligible for the two-day direct-deposit requirement; explain its monthly fee and the limits of the ATM-rebate estimate rather than fabricating third-party surcharge amounts.

## Required banking workflow

Before any account-opening action, verify customer identity, authority, product eligibility, applicable fees and limits, and the customer’s confirmation requirements. Do not expose sensitive identity values unnecessarily in the customer-facing reply.

1. **Identify the customer.** Use `get_user_information_by_name`, `get_user_information_by_email`, or `get_user_information_by_id` to locate the record. If the lookup is ambiguous or unavailable, obtain a valid identifier before proceeding.
2. **Verify identity.** Ask the customer to provide two of the four on-file identity fields: date of birth, email, phone number, or address. Compare them to the retrieved record. Do not treat previously displayed profile data, a name alone, or an assertion that the profile is verified as the required two-factor identity check. After two fields match, obtain a current timestamp with `get_current_time` and call `log_verification` with the complete retrieved customer record and timestamp. Stop if verification fails.
3. **Retrieve account data.** Unlock `get_all_user_accounts_by_user_id_3847`, then call it using the verified `user_id`. Use the returned account type, status, balance, and opening date to evaluate eligibility.
4. **Check personal-checking eligibility.** Confirm all of the following before opening:
   - the customer is verified;
   - the customer is at least 18;
   - the customer does not exceed the allowed limit of four personal checking accounts;
   - no checking account was closed for cause in the past six months.

   If returned account data cannot establish an eligibility item (for example, closure-for-cause history), ask for the required confirmation or use an available authorized source. Do not open the account while an item is unknown, failed, or inconsistent. Explain the unmet condition without disclosing unnecessary account details.
5. **Make or confirm the recommendation.** State the relevant maintenance fee, waiver threshold, ATM fees/rebates, third-party-fee caveat, ATM limit, and early-direct-deposit timing. If the customer requires two-day early direct deposit and cannot maintain Purple’s waiver balance, Purple may still be appropriate if the customer accepts its $15 monthly fee. Do not represent Blue as meeting a two-day requirement.
6. **Obtain final confirmation.** Confirm the exact account selection and explicit authorization immediately before opening. The personal checking `account_class` must be the full official name ending in `Account`, such as `Purple Account` or `Blue Account`; do not shorten, translate, or guess the string.
7. **Open the account.** Unlock `open_bank_account_4821` and call it with the verified customer’s `user_id`, `account_type` set to `checking`, and the confirmed full `account_class`. Banking actions are performed by the execution agent with its normal banking tools, not by the comparison script.
8. **Report the result.** State whether the account was opened based only on the tool response. Recap the selected account’s documented fees, waiver condition, direct-deposit timing, ATM limits, and relevant third-party fee caveat. If the tool fails, do not claim success; provide the failure status and appropriate next step.

## Failure handling

- If the customer does not provide two matching identity fields, do not log verification or open an account.
- If the account lookup, eligibility check, account-class confirmation, or authorization is missing, pause and obtain it.
- If product facts required for a comparison are not documented, say so rather than estimating them.
- If an account-opening tool is unavailable or returns an error, do not retry blindly and do not imply that an account was created.
- Do not transfer funds as part of this personal-checking workflow unless a separately authorized procedure explicitly requires it.

## Script I/O

`scripts/compare_travel_options.py` reads one JSON object from standard input and emits one JSON object to standard output. Required fields are `months`, `withdrawals_per_month`, and `withdrawal_amount_usd`; optional boolean fields control whether each fee-waiver balance is maintainable and whether two-day early direct deposit is required. Numeric inputs must be nonnegative, and months must be positive. See the script’s `input_schema` in output for the complete contract.
