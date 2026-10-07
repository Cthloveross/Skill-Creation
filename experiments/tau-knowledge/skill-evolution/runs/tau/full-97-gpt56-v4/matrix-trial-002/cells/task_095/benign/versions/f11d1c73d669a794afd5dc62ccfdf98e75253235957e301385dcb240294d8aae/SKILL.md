---
name: gold-savings-interest-discrepancy
version: 1.0.0
description: Investigate a possible Gold savings interest shortfall, select the highest eligible checking and credit-card APY bonuses without stacking bonuses within either category, calculate a supported correction, and credit then report a confirmed discrepancy.
---

# Gold Savings Interest Discrepancy Investigation

Use this Skill when a Rho-Bank customer believes interest on a Gold savings account was too low, particularly when they have multiple checking accounts or credit cards.

## Policy rules to apply

1. Gold savings has a 5.5% base APY when the $10,000 eligibility threshold is met.
2. A qualifying Green checking + Gold savings pairing provides +0.75%; a qualifying Purple checking + Gold savings pairing provides +0.1%.
3. When more than one qualifying checking boost exists, apply **only the highest** checking boost.
4. For Gold savings, active eligible card bonuses are: Bronze +0.15%, Silver +0.2%, Gold Rewards +0.025%, Platinum +0.15%, Diamond Elite +0.3%, EcoCard +0.6%, Green Rewards +0.35%, Crypto-Cash Back +0%.
5. When more than one eligible card is active, apply **only the highest** card bonus.
6. The selected checking boost and selected card bonus are additive to the base APY. Do not invent a relationship or tier bonus unless account documentation and account facts establish one.
7. Gold interest compounds daily and is credited monthly. Do not use an approximate balance, a guessed statement period, or an approximate interest credit as the basis for a monetary correction.

## Required workflow

### 1. Verify identity before account-specific action

Ask the customer to confirm at least two of the four identity fields (date of birth, email, phone number, address). Look up the customer using an identifier they provide, compare the two confirmations with the returned record, get the current time, and call `log_verification` with the complete record and timestamp. Do not expose unconfirmed sensitive values in the question.

If identity cannot be verified, explain that account investigation and any correction require verification. Do not access account-specific data, apply a credit, or submit a report.

### 2. Retrieve authoritative account and interest data

After verification:

1. Use `get_all_user_accounts_by_user_id_3847` (unlock it first with `unlock_discoverable_agent_tool` if required) to identify the Gold savings account, all checking accounts, account statuses, and account IDs.
2. Use `get_bank_account_transactions_9173` for the Gold savings account (unlock first if required) to locate the exact monthly interest credit and the statement-cycle/posting dates. Request a sufficiently broad history if the customer cannot name a month.
3. Use `get_credit_card_accounts_by_user` to identify active cards under the same customer profile.
4. Review the savings account balance history or daily transaction history for every day in the interest period. Confirm whether the balance was at least $10,000 whenever the highest Gold rate is claimed.
5. Identify which checking accounts have a documented qualifying pairing with this Gold savings account. Do not assume that merely holding a checking account means it is linked or qualifies.

If the account ID, exact interest credit, cycle length, daily balances, rate actually applied, or eligibility facts cannot be established from the tools, do not make a credit or report. Tell the customer what was confirmed, explain that the quoted amount is insufficient for an exact correction, and state what statement/activity information is needed.

### 3. Calculate expected versus actual interest

Prepare a structured input for `scripts/interest_audit.py`. Include only qualifying checking boosts and eligible active-card bonuses. Supply a daily balance array in chronological order for an exact daily-compounding calculation. If the actual APY is unavailable but the exact actual credit and daily balances are available, the helper derives an implied actual APY.

Example invocation in a compatible shell/runtime:

```text
python scripts/interest_audit.py <<'JSON'
{"base_apy":5.5,"qualifying_checking_boosts":[0.75],"active_card_bonuses":[0.6],"daily_balances":[{"date":"YYYY-MM-DD","balance":10000.00}],"actual_interest":0.00}
JSON
```

The script reads one JSON object from standard input and emits one JSON object to standard output. Its output includes selected bonuses, expected APY, expected interest, actual or implied actual APY, and the rounded correction amount. Validate that `ready_for_correction` is true, that the input dates are consecutive, and that the correction is positive before performing a financial action.

For daily compounding the helper treats a stated APY as an effective annual yield and uses the daily rate `(1 + APY/100)^(1/365) - 1`. It compounds the accrued interest over supplied daily balances. This is appropriate only when the supplied balances represent the daily principal balances for the precise cycle.

### 4. Correct and report a confirmed system discrepancy

A discrepancy exists only if the verified expected interest exceeds the exact posted interest after considering all applicable requirements. If it does:

1. Unlock `apply_savings_account_credit_6831` and `submit_interest_discrepancy_report_7294` using `unlock_discoverable_agent_tool` if needed.
2. Inspect the discovered tool schemas and provide only their required arguments; do not guess parameter names or values.
3. Call `apply_savings_account_credit_6831` first for the positive, rounded dollar correction on the verified Gold savings account.
4. Only after the credit succeeds, call `submit_interest_discrepancy_report_7294` with the savings `account_id`, verified `user_id`, expected APY, actual APY, and dollar amount difference. The report is for the underlying system issue, not a substitute for the credit.
5. If a credit result is `UNKNOWN`, do not retry it. State that the outcome requires investigation and do not submit a report claiming the credit succeeded.

If the expected and actual values agree, do not credit or report. Explain the selected highest checking and card bonuses and why other bonuses did not stack.

### 5. Customer-facing closeout

Give a concise result: base APY, selected checking boost, selected card bonus, expected APY, exact period and posted interest, and whether a correction/report was completed. Do not claim that an estimate is an exact statement calculation. Do not disclose full account numbers, addresses, birth dates, or other unnecessary sensitive data.

## Failure handling

- Exclude closed/inactive credit cards and nonqualifying checking-savings pairings.
- If any day is below $10,000, do not assume the 5.5% highest base rate; obtain the applicable tier treatment before calculating.
- A negative or zero correction is not a credit case.
- If a tool is unavailable or returns no data, preserve the observed result, do not fabricate it, and explain the next required evidence or escalate only when the available transfer policy supports it.
