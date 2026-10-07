---
name: investigate-savings-interest-discrepancy
description: Investigate a verified customer's suspected savings-interest error, determine APY components without stacking card or checking bonuses, calculate a supportable correction from statement-period data, and—only when authorized and fully evidenced—apply a savings interest correction before filing the required backend discrepancy report.
---

# Investigate Savings Interest Discrepancies

Use this Skill when a customer says a savings-account interest credit, APY tier, linked-checking boost, credit-card bonus, direct-deposit bonus, or relationship bonus was missing or incorrect.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For this workflow, do not apply a credit or submit a report until identity and authority are verified, the savings account is owned by the customer, the account is active and is actually a savings account, the statement-period interest credit is identified, and a positive, reproducible discrepancy has been calculated.

## Required information and tools

Request or retrieve, as appropriate:

- Two matching identity fields, then the customer profile and the current timestamp.
- The disputed savings account(s), their status, account class, balance, and opening date.
- All active checking accounts and active credit cards under the same profile.
- The statement period, exact interest-credit posting date and amount, and daily balances or enough transaction history to reconstruct them.
- Whether checking accounts were linked during the disputed period, whether Silver Plus direct deposit was active, and evidence for any relationship-bonus eligibility.

The documented internal tools are discoverable. Unlock a tool before calling it:

1. `get_all_user_accounts_by_user_id_3847` for checking and savings account details.
2. `get_bank_account_transactions_9173` for each disputed savings account's transaction history.
3. `apply_savings_account_credit_6831` to make an eligible, positive savings interest correction.
4. `submit_interest_discrepancy_report_7294` to report a verified system interest discrepancy.

Use the ordinary profile and card lookup tools available in the runtime as needed. After confirming two of four identity fields (date of birth, email, phone number, address), call `log_verification` with the retrieved full profile and current timestamp before account-specific handling.

## Investigation procedure

1. **Verify identity, authority, and ownership.** Obtain two matching identity fields from the customer, retrieve the customer profile, get the current time, and log verification. Confirm the customer is the account holder. Do not treat a name or email lookup alone as authority for a monetary adjustment.

2. **Discover the accounts.** Retrieve all accounts for the verified user. Identify every disputed active savings account and all active checking accounts. Retrieve active credit-card accounts separately. Do not rely on approximate account names, balances, or customer estimates.

3. **Get transaction evidence.** Retrieve transaction history for each disputed savings account. Locate posted `interest_credit` transactions and record exact amount and posting date. Determine the relevant statement period. Inspect transactions and balances for changes that affect daily accrual. Pending credits/debits do not establish a posted interest amount.

4. **Establish the applicable APY for each day or homogeneous interval.** Consult the documentation for the exact savings product and linked checking products.

   - Use the savings account's balance tier for that day's balance; do not use a higher tier below its threshold.
   - A qualifying checking/savings pairing is required before any linked-checking boost applies.
   - When several eligible active checking accounts are linked, use **only the highest applicable checking boost**. Checking boosts do not stack with each other.
   - When several eligible active cards are held under the same profile, use **only the highest applicable credit-card bonus** for that savings product. Card bonuses do not stack with each other.
   - The selected checking boost and selected card bonus may stack with the base/tier APY and other independently documented bonuses.
   - Add direct-deposit or relationship bonuses only when the documentation's eligibility conditions are affirmatively evidenced for the disputed period. In particular, do not assume a relationship bonus merely because the customer has multiple products when the required criteria are not available.
   - Check savings-product maintenance/eligibility requirements and checking-product eligibility that could affect a claimed benefit. For example, a linked checking product with an age requirement must have been eligible during the relevant period.

   Provide the selected components and excluded lower components in the case record. The helper `scripts/select_apy.py` can perform deterministic highest-only selection after the investigator supplies documented eligible values.

5. **Calculate the expected credit.** Divide the period into intervals whenever balance, tier, linkage, card status, or bonus eligibility changes. For each interval, use a documented daily rate and daily compounding convention. `scripts/calculate_daily_interest.py` calculates interval interest from daily balances or a constant balance. Sum unrounded interval interest and round only the final monetary result to cents unless the bank's system documentation specifies a different rounding rule.

6. **Compare expected and actual.** Compare the calculated statement-period expected interest to the posted `interest_credit`. Preserve the exact actual amount, the expected APY, actual/effective APY if reliably derivable, method, source facts, period, and rounding convention. Do not infer actual APY from an estimated payment or an unspecified period.

7. **Resolve only a verified discrepancy.** If expected interest exceeds actual posted interest by a positive amount and the discrepancy is attributable to a qualifying system error, first apply a savings credit with:
   - `account_id`: verified savings account ID
   - `amount`: positive calculated difference, rounded to cents
   - `credit_type`: `interest_correction`

   Confirm the credit succeeded. Only after the successful credit, submit `submit_interest_discrepancy_report_7294` with the verified account ID, user ID, expected APY percentage, actual APY percentage, and dollar amount difference. The report supports backend investigation; it does not replace the credit.

8. **Communicate the result.** Explain the statement period reviewed, actual and expected credits, the selected highest card/checking components, and whether a correction/report was completed. Do not expose unrelated account or card details.

## Insufficient evidence and failures

Do not apply a credit, submit a report, or claim the interest was wrong if any of these are unavailable: verified identity/authority, owned active savings account, exact posted interest credit, relevant period, enough daily balance/activity data, confirmed linkage, or documented eligibility for claimed bonuses.

If records show no positive discrepancy, explain the calculation and that no correction is authorized. If an account lookup or transaction lookup is unavailable, tell the customer what cannot be verified and request the statement dates and exact posted credits; do not substitute estimates. If a customer explicitly requests a human agent after this limitation or demands escalation due to frustration, use `transfer_to_human_agents` with the applicable customer-frustration or human-request reason and a concise factual summary.

Never retry an action with an unknown outcome. If a credit or report outcome is unknown, preserve the details and escalate rather than risking a duplicate monetary action.

## Helper scripts

Both scripts read one JSON object from standard input and emit one JSON object to standard output. They make no banking changes.

### APY selection

```sh
python3 scripts/select_apy.py <<'JSON'
{"base_apy_percent": 4.5, "credit_card_bonuses_percent": [0.4, 0.15], "checking_boosts_percent": [0.35], "other_documented_bonuses_percent": [0.25]}
JSON
```

Inputs are documented, applicable values for one interval only. The result reports the highest card and checking values, exclusions, and total APY percentage. Empty lists mean no documented applicable bonus.

### Daily-interest calculation

```sh
python3 scripts/calculate_daily_interest.py <<'JSON'
{"apy_percent": 4.5, "day_count": 30, "constant_daily_balance": 10000, "apy_convention": "effective_annual"}
JSON
```

Supply either `constant_daily_balance` with `day_count`, or `daily_balances` as a nonempty numeric list containing one end-of-day balance per day. `apy_convention` is `effective_annual` (default, daily rate is `(1 + APY)^(1/365)-1`) or `nominal_annual` (daily rate is `APY/365`). Select the convention supported by the product/system documentation and record it. For several intervals, run the calculation per interval and sum `unrounded_interest` before final rounding.
