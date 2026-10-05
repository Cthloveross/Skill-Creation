---
name: savings-interest-discrepancy-resolution
description: Investigate a claimed savings-interest underpayment, calculate a supportable per-account correction from statement-period daily balances and documented APY components, then apply an interest-correction credit before filing the required backend discrepancy report. Use for Silver, Silver Plus, Platinum, Diamond Elite, and other savings interest discrepancies.
---

# Savings Interest Discrepancy Resolution

Use this Skill when a customer reports that a savings-account interest credit is missing or incorrect. The workflow is per savings account and per affected statement period. It does not authorize a credit or report based only on approximate balances, approximate interest amounts, or an unsupported APY assumption.

## Mandatory banking preflight

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For this workflow specifically:

1. Verify identity by confirming two of date of birth, email, phone number, and address against the customer record; obtain the current timestamp and create the verification audit record with `log_verification`.
2. Confirm the requester is authorized and owns each target account.
3. Use `get_all_user_accounts_by_user_id_3847` to retrieve accounts. Confirm each target is an active savings account and retain its `account_id`, account class, and balance.
4. Use `get_bank_account_transactions_9173(account_id)` for every target account. Locate the posted `interest_credit` for the claimed period and identify any relevant balance-changing activity.
5. Confirm the statement period, posted interest amount, daily/end-of-day balances (or enough complete activity to reconstruct them), displayed actual APY if available, and all eligibility facts for each claimed correction.
6. Obtain customer confirmation of the final calculated correction amount before making the credit, where the operational process requires confirmation.

Do not apply a credit, submit a report, or infer missing account facts if identity/authority, savings-account ownership, the interest credit, the period balance history, or the applicable APY inputs cannot be verified. Request the missing statement/app details instead.

## Required information

For each affected account collect:

- Savings account name/class, account ID (or obtain it through account lookup), and last four digits for customer-facing confirmation.
- Statement start and end dates.
- The posted interest-credit date, exact amount, and status.
- Daily ending balances for the period, or a complete chronological activity record sufficient to reconstruct them. Interest is calculated daily, so a current or approximate balance alone is insufficient.
- The displayed actual APY/effective rate for the period, if present.
- Account-specific rate eligibility facts: qualifying linked checking accounts, active credit cards, relationship eligibility, direct-deposit eligibility for Silver Plus, and any tier changes.

If the customer cannot supply statement details and the account lookup/transaction tools are available, retrieve them after identity and ownership verification. If the available tools still cannot establish the period data, explain exactly what is needed: account name and last four, statement dates, interest-credit date/amount, displayed APY, and balance/activity history. Do not guess or use approximate opening amounts as daily balances.

## Rate determination

Determine the expected APY independently for each day when balances or eligibility change.

- **Silver:** base tier is 2.5% below $10,000 and 4.0% at or above $10,000. The account may have a qualifying linked-checking boost, the highest eligible Silver card bonus, and an eligible relationship bonus of 0.025%.
- **Silver Plus:** base tier is 3.0% below $15,000 and 4.5% at or above $15,000. Add an active direct-deposit bonus of 0.25%, the highest eligible Silver Plus card bonus, any documented qualifying checking boost, and the eligible relationship bonus of 0.025%.
- **Platinum:** base APY is 6.5%. Add the highest eligible Platinum card bonus and any documented qualifying checking boost or other documented eligible component.
- **Diamond Elite:** base APY is 7.5%. Add the highest eligible Diamond Elite card bonus and any documented qualifying checking boost or other documented eligible component.

Card bonuses never stack with one another: use only the highest applicable active card bonus for the account type. Likewise, multiple checking boosts do not stack: use only the highest qualifying boost for that savings-account type. The selected card/checking bonus may stack with eligible relationship, tier, and direct-deposit components.

Only use a checking boost when the pairing is one of the documented qualifying pairings *and* its exact boost percentage is documented for that savings product. If the percentage is absent, mark it unresolved rather than substituting a value. Relationship eligibility must be verified rather than assumed merely because the customer has multiple products.

## Calculation

Use `scripts/calculate_interest_discrepancy.py` to make the repeated daily-compounding calculation reproducible. Supply a complete daily ledger, APY component values in percentage points, the posted interest amount, and the actual displayed APY if known.

The script treats APY as an effective annual percentage and calculates each daily accrual as:

`daily_balance × ((1 + expected_apy / 100) ** (1 / 365) - 1)`

It sums unrounded daily accruals and rounds only the final expected period interest and correction to cents. The actual posted interest amount must be the amount of the identified `interest_credit`. A positive correction is eligible for an `interest_correction` credit. A zero or negative difference is not a basis for this credit workflow.

The report requires `actual_apy`. Prefer the displayed period APY or a rate explicitly contained in the account/statement data. Do not reverse-engineer an actual APY from one monthly interest amount when balances or rates varied. If it cannot be established, stop and obtain the needed record rather than submit a report with a fabricated rate.

## Execute the correction and report

After all preflight checks pass and the script produces a positive, supportable correction:

1. Unlock and call `apply_savings_account_credit_6831` with the verified savings `account_id`, the positive rounded `correction_amount`, and `credit_type` set exactly to `interest_correction`.
2. Confirm that the credit action succeeded.
3. Only after the successful credit, unlock and call `submit_interest_discrepancy_report_7294` with:
   - `account_id`: verified affected savings account ID
   - `user_id`: verified customer user ID
   - `expected_apy`: the calculated applicable APY percentage for the reportable issue
   - `actual_apy`: the verified actual APY percentage
   - `amount_difference`: the positive correction amount credited
4. Record the resulting confirmation identifiers and clearly tell the customer that the credit resolves the immediate shortfall while the backend report investigates the underlying rate issue.

Run the sequence separately for each affected account. Never submit the backend report before its corresponding successful correction credit. Never use the credit tool for a zero/negative/unverified amount.

## Script interface

Run:

```text
python scripts/calculate_interest_discrepancy.py < input.json
```

The script receives one JSON object on stdin and emits one JSON object on stdout. Required fields are:

```json
{
  "account_type": "Silver",
  "daily_records": [
    {"date": "YYYY-MM-DD", "balance": 0, "base_apy": 0}
  ],
  "actual_interest_credited": 0,
  "actual_apy": 0
}
```

`daily_records` must contain one record per interest-accruing calendar day. `balance` must be nonnegative and `base_apy` is the applicable daily base/tier APY in percentage points. Optional per-record components are `checking_boost_apy`, `card_bonus_apy`, `relationship_bonus_apy`, `direct_deposit_bonus_apy`, and `other_documented_bonus_apy`, all nonnegative percentage points. `card_bonus_apy` and `checking_boost_apy` must already be the respective highest eligible values; the script rejects attempts to provide alternative bonus lists.

For a constant-rate period, supplying the same component values for each daily record is valid. The optional top-level `report_expected_apy` may be supplied only when one verified APY applies to the reported discrepancy. Omit it for variable-rate periods; the script will mark the report APY as requiring an agent decision instead of inventing one.

Validate output before banking actions: `valid` must be true, `status` must be `positive_discrepancy`, `correction_amount` must be greater than zero, and `actual_apy` must be present. Treat any `errors` or `warnings` as a stop condition until resolved.