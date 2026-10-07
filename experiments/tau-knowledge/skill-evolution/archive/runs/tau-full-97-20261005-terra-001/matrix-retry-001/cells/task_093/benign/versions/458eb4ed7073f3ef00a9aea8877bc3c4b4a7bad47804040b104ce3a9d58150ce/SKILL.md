---
name: investigate-silver-savings-interest-discrepancy
description: Verify a customer and investigate a suspected Silver Account interest underpayment. Use when an agent must retrieve the savings account and posted interest transaction, establish documented APY eligibility and daily balances, calculate a confirmed discrepancy, then credit before reporting it.
---

# Investigate a Silver Account interest discrepancy

Use this Skill when a customer believes monthly Silver Account interest is too low. Do not infer a discrepancy from a current balance, a customer impression, or a posted credit alone.

## Policy facts

- Silver APY is 2.5% below a $10,000 daily balance and 4.0% at or above it. Interest compounds daily and is credited monthly.
- A qualifying, linked Green Account checking account provides a 0.25% Silver boost; qualifying linked Bluest checking provides 0.45%. Use a boost only when the specific pairing, link, active status, and documented percentage are established.
- Only the highest eligible checking boost and highest eligible card bonus apply within their respective categories. A confirmed relationship bonus may stack with those categories.
- Silver's relationship bonus is 0.025%, but eligibility must be established; holding multiple products alone is not sufficient proof.
- A correction is authorized only for a calculated positive underpayment. The correction credit must succeed before an interest discrepancy report is submitted.

## Workflow

1. **Identify and verify before account investigation.**
   - Identify the customer using customer-provided information.
   - Ask the customer to confirm two of date of birth, email, phone number, and address. Compare the answers to the customer record; do not present profile values as answers for the customer.
   - Obtain the current time and call `log_verification` after successful matching, supplying every required record field and timestamp.
   - If verification fails or ownership is disputed, do not disclose account details or make changes. Escalate as an ownership dispute.

2. **Retrieve accounts after verification.**
   - Unlock and call `get_all_user_accounts_by_user_id_3847` through `call_discoverable_agent_tool` with the verified user's ID.
   - Select only an active savings account that the returned account data establishes as Silver. If several accounts plausibly match, ask the customer which one is in question.
   - Review active checking accounts and establish whether any documented qualifying checking account is actually linked to the selected savings account. Do not equate being under the same profile with a confirmed link.
   - When relevant, retrieve credit card accounts with `get_credit_card_accounts_by_user`; use only active, documented applicable card bonuses.

3. **Retrieve the interest payment.**
   - Unlock and call `get_bank_account_transactions_9173` for the selected savings account.
   - Find the relevant posted, positive `interest_credit`, recording its cycle/date and amount. A pending item is not final evidence of paid interest.
   - Establish every daily balance in the relevant statement cycle from a reliable ledger or statement. Transaction history that does not establish complete daily balances is insufficient. Request a statement or balance history when needed.

4. **Calculate only from evidenced inputs.**
   - Run `scripts/analyze_silver_interest.py` using the schema below after full daily balances, posted interest, and bonus eligibility are established.
   - Only `ready_for_correction` supports an interest correction. Retain calculator output and source records as the workpaper.
   - If daily balances, statement cycle, link status, APY components, or posted interest cannot be established, explain that no discrepancy can yet be confirmed. Do not credit or report.

5. **Correct, then report.**
   - For `ready_for_correction`, unlock and call `apply_savings_account_credit_6831` with the selected savings account ID, the positive calculator `amount_difference`, and `credit_type: "interest_correction"`.
   - Confirm the credit succeeded before proceeding. If it fails, do not submit a report as though the customer has been made whole.
   - Then unlock and call `submit_interest_discrepancy_report_7294` with the verified user ID, selected savings account ID, calculator `report_expected_apy`, documented applied APY or `actual_apy_inferred`, and positive `amount_difference`.
   - Tell the customer the credit was applied and the report requests backend investigation; do not claim the underlying system issue is already resolved.

## Missing data, errors, and human transfer

- A tool/service failure preventing a required step is a `technical_system_error` transfer reason. Include the attempted operation and error in the summary.
- Missing daily balances or unconfirmed checking-savings linkage do not establish an error and do not authorize a credit or report.
- If the customer asks for human help obtaining ordinary account records or further review after the available investigation cannot establish the required evidence, transfer successfully with **`reason: "other"`**. This is not `specialized_department_required`: ordinary account-record access is not an outside-scope specialty such as mortgage, investments, or business banking.
- For that `other` transfer, provide a detailed factual summary containing: selected savings account identifier (if known); posted interest date and amount (if known); that complete daily balance evidence is missing; whether checking-savings linkage is unconfirmed; and that no correction credit or discrepancy report was made because a calculation could not be supported.
- Use another transfer code only when its higher-priority policy definition actually applies.

## Calculator interface

Run `scripts/analyze_silver_interest.py` with one JSON object on stdin. It emits one JSON object on stdout and performs no banking action.

```json
{
  "daily_balances_complete": true,
  "daily_balances": [{"date": "YYYY-MM-DD", "balance": 0}],
  "actual_interest_credit": 0,
  "tier_threshold": 10000,
  "low_tier_apy": 2.5,
  "high_tier_apy": 4.0,
  "checking_candidates": [
    {"name": "product", "active": true, "linked": true, "qualifying": true, "boost_apy": 0}
  ],
  "card_candidates": [
    {"name": "product", "active": true, "applicable": true, "bonus_apy": 0}
  ],
  "relationship": {"eligible": false, "bonus_apy": 0.025}
}
```

Daily balances must be nonnegative, dated once per consecutive day, and represent the entire statement cycle. The output status is `ready_for_correction`, `no_underpayment`, `insufficient_data`, or `invalid_input`. Only `ready_for_correction` permits the credit/report sequence. The calculator uses daily rate `(1 + APY/100)^(1/365) - 1`, compounds daily, and rounds money only at final payment and correction stages.
