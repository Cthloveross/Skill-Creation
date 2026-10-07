---
name: savings-interest-discrepancy-review
version: 1.0.0
description: Investigate a verified customer's claimed underpayment of monthly savings interest, calculate a documented correction from account activity and applicable APY rules, and—only when verified—apply an interest-correction credit before filing the required backend discrepancy report.
---

# Savings Interest Discrepancy Review

Use this Skill when a customer says that interest on one or more savings accounts was calculated incorrectly. It supports investigation of Silver, Silver Plus, Platinum, and Diamond Elite accounts, but the workflow is reusable for any savings product whose APY terms and account history can be verified.

## Safety and authorization rules

- Do **not** apply a credit from estimates, rounded customer recollections, current balances alone, or an apparent gap between two quoted amounts.
- A savings interest correction is authorized only after confirming identity and ownership, confirming the account is a savings account, locating the exact posted interest transaction, determining the relevant statement cycle and daily balance activity, and calculating a positive discrepancy.
- A credit amount must be positive and must be the verified dollar difference. Never use a negative or zero amount.
- For an interest discrepancy, the corrective credit must succeed **before** the discrepancy report is submitted.
- Do not repeat an action if its result is unknown, timed out, or ambiguous. First inspect the account history or obtain the action status.
- Do not claim a new balance unless the successful credit response or a subsequent account lookup provides it.

## Required runtime tools

The executor must use the normal banking tools, not this package's calculator, to access or alter banking data. Unlock the following documented agent tools before use:

1. `get_all_user_accounts_by_user_id_3847`
2. `get_bank_account_transactions_9173`
3. `apply_savings_account_credit_6831`
4. `submit_interest_discrepancy_report_7294`

Use each unlocked tool's displayed schema. Do not invent parameters beyond its schema. The credit tool requires `account_id`, a positive `amount`, and `credit_type: "interest_correction"`. The reporting tool requires `account_id`, `user_id`, `expected_apy`, `actual_apy`, and `amount_difference`.

## End-to-end procedure

### 1. Verify the customer before account disclosure or an account change

1. Resolve the customer's profile with a supplied identifier using the appropriate user lookup tool.
2. Obtain confirmation of at least two of the four identity fields: date of birth, email, phone number, and address. A lookup result alone is not identity verification.
3. Get the current time and call `log_verification` after successful confirmation, supplying the complete verified profile fields and timestamp required by that tool.
4. If two fields cannot be confirmed, explain that identity verification is required and do not retrieve detailed account activity or apply a credit.

### 2. Retrieve the bank-side evidence

1. Use `get_all_user_accounts_by_user_id_3847` for the verified user.
2. For every savings account the customer raises, confirm that it belongs to the verified user, is a savings account, and identify its actual account ID and product type from the returned records. Do not rely on a customer-supplied account label or balance.
3. Query `get_bank_account_transactions_9173` for each verified savings account using its actual ID and the tool's supported date/filter fields.
4. Locate the separate, posted monthly interest-credit transaction and its exact amount. Establish the statement-cycle dates from the statement/account history and reconstruct the daily end-of-day balances and all activity relevant to that cycle.
5. If the customer cannot provide a statement, perform this bank-side review after verification. If the tool data still cannot establish the exact cycle, actual interest, or daily balances, do not credit or report. Explain precisely which records are unavailable and invite the customer to return when a statement is available.

### 3. Determine the APY that should have applied

Use terms that applied during the actual cycle, not only current holdings. Preserve evidence for every component.

- **Silver:** base tier is 2.5% or 4.0%; the documented higher-tier threshold is $10,000. Credit-card and qualifying checking bonuses can apply, but only the highest eligible bonus within each respective card/checking category applies. The documented relationship bonus is 0.025% only when its actual eligibility criteria are met.
- **Silver Plus:** tier 1 is 3.0% and tier 2 is 4.5%; tier 2 requires at least $15,000. The documented relationship bonus is 0.025% only when eligible. Apply only the highest eligible card and checking bonuses within their categories.
- **Platinum:** documented base APY is 6.5%; verify the applicable account conditions and any documented qualifying bonuses for the cycle.
- **Diamond Elite:** documented base APY is 7.5%; verify the applicable account conditions and any documented qualifying bonuses for the cycle.
- Qualifying checking/savings pairings are product-specific. Only use a checking boost if the pairing is documented and the checking account was active and linked in the same profile during the cycle. Multiple checking boosts never stack: choose the highest applicable one.
- Multiple credit-card APY bonuses never stack: choose the highest applicable one. A selected card bonus may stack with a selected checking boost and a separately qualified relationship or tier component.
- Do not infer an undocumented boost percentage from the checking account name, from an estimated payment, or from another product. If an exact component cannot be verified from applicable product documentation or account records, the expected APY is not established.

Determine the actual APY from the statement, account record, or transaction evidence where available. Do not substitute an approximate effective rate for the actual APY in a required report. If the report's `actual_apy` cannot be supported, continue evidence collection rather than filing a speculative report.

### 4. Calculate and validate the correction

Calculate interest over the exact cycle using the verified daily balances, the documented daily-compounding convention, and the APY applicable to each day. A tier crossing or eligibility change during the cycle may require separate daily segments.

`scripts/calculate_daily_interest.py` can calculate one segment when the system's daily rate and daily balances are known. It is a calculation aid, not a source of account data or an authorization decision. Run one calculation per constant-rate segment, then sum the unrounded segment results in the institutionally documented way before applying the account's required currency rounding. Compare that expected amount with the exact posted interest credit.

Before an action, check all of the following:

- account ownership and savings product are confirmed;
- posted interest amount, cycle, and daily balances are exact;
- expected APY and each bonus/tier assumption are documented for that cycle;
- actual APY is supportable for the report;
- `expected_interest - actual_posted_interest`, after required rounding, is greater than $0.00; and
- the amount is not already covered by a prior interest-correction transaction for that same cycle.

If any check fails, do not use a goodwill credit as a substitute. Explain that no verified correction can be applied yet.

### 5. Apply then report

For each independently verified underpayment:

1. Call `apply_savings_account_credit_6831` with the verified savings `account_id`, the positive verified correction, and `credit_type` set to `interest_correction`.
2. Confirm the result is successful. If it fails or is unknown, do not submit a report and do not retry blindly.
3. After the credit succeeds, call `submit_interest_discrepancy_report_7294` with the same account ID, verified user ID, supported expected and actual APY percentages, and the same dollar difference.
4. Record which accounts were corrected/reported and which could not be resolved. For a successful correction, tell the customer the credited amount and the returned or subsequently verified balance. For unresolved accounts, name the missing evidence without asserting that the customer was underpaid.

## Customer-facing completion language

Use factual, account-specific wording. For example: "I reviewed the posted interest and account activity for the statement cycle. I applied a verified interest correction of $[amount] to [account] and submitted the underlying calculation issue for investigation." If evidence is incomplete: "I can review the activity on our side after verification, but I cannot apply an interest correction until I can match an exact statement cycle, posted interest entry, and balances to the applicable APY terms. I have not applied a credit based on estimates."

## Calculator interface

Run `scripts/calculate_daily_interest.py` with JSON on stdin. It emits JSON only on stdout.

Input schema:

```json
{
  "daily_rate": "0.00012345",
  "days": [
    {"date": "YYYY-MM-DD", "end_of_day_balance": "1000.00"}
  ],
  "actual_interest": "12.34",
  "round_daily_interest_to_cents": false
}
```

- `daily_rate` is a decimal fraction, not a percent (for example, `0.0001` means 0.01% per day). Supply the bank's documented or account-record daily rate; do not assume a rate-conversion convention the evidence does not establish.
- `days` must be chronological and contain the full cycle's verified daily end-of-day balances for a constant-rate segment.
- `actual_interest` is optional. When supplied, output includes the expected-minus-actual difference.
- Set `round_daily_interest_to_cents` only if the applicable product/account record confirms that daily accrual is rounded to cents. Otherwise leave it false and round only according to the bank's confirmed posting rule.

A valid result has `ok: true`. The executor must reject `ok: false`, a non-positive `difference_rounded_to_cents`, missing cycle days, or unsupported rate assumptions as a basis for a banking action.
