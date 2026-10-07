---
name: savings-interest-discrepancy-reconciliation
description: Investigate a suspected underpayment of interest on a Rho-Bank savings account, determine the applicable APY without stacking card or checking bonuses, calculate a supportable correction from account-period data, and complete the required credit-then-report workflow. Use for Bronze or Gold Plus savings interest questions and adapt only when product documentation provides equivalent rates and eligibility rules.
---

# Savings-interest discrepancy reconciliation

## Purpose and boundaries

Use this Skill when a customer questions a posted savings interest credit or asks for an interest correction. It distinguishes a **rate review** from an **exact monetary correction**. Do not issue a credit, submit a discrepancy report, or state that the posted interest was wrong until the account, statement period, applicable APY, and daily-balance calculation are supported by records.

Interest compounds daily and is credited monthly for the products covered here. Approximate balances, a customer's recollection, or a single current balance can help explain the issue but cannot establish an exact correction.

## Required authentication and account discovery

1. Obtain and compare two of the four identity fields (date of birth, email, phone number, address) with the profile. Do not disclose protected account details while doing so.
2. After two fields match, call `get_current_time` and `log_verification` with the complete required verification record.
3. Unlock and use `get_all_user_accounts_by_user_id_3847` to identify the customer's active savings and checking accounts. Confirm that the target is a savings account under the verified customer's profile.
4. Use `get_credit_card_accounts_by_user` to identify active credit cards under that same profile.
5. Unlock and use `get_bank_account_transactions_9173` for each target savings account. Identify the relevant **posted** `interest_credit`, its amount and date, and all posted activity covering the calculation period. Pending entries are not proof of an interest payment.

If authentication, ownership, the target account type, or the relevant posted interest credit cannot be confirmed, do not make an adjustment.

## Determine the correct APY

Use only active accounts under the same profile and only documented qualifying checking–savings pairings. Add the base APY, the single highest eligible checking boost, and the single highest eligible card bonus:

`expected APY = base APY + max(eligible checking boosts, or 0) + max(eligible card bonuses, or 0)`

Checking boosts do not stack with other checking boosts. Credit-card bonuses do not stack with other card bonuses. The selected checking boost and selected card bonus do stack with the base APY and with one another.

Consult `references/covered_product_rates.md` for the documented product-specific rates in this package. For an account type or benefit not covered there, retrieve the applicable product documentation instead of extrapolating a rate.

Record the candidates considered, why each candidate qualifies or does not qualify, and the highest selected value in the case notes. A customer merely saying they have a checking account or card is insufficient; confirm status and ownership through account records.

## Exact calculation workflow

1. Establish the statement/interest period from the posted interest entry and the prior cycle boundary.
2. Obtain a complete daily eligible-balance schedule for every day in that period from the account ledger, statement data, or a complete transaction reconstruction that supports the daily balances. Also obtain the account's disclosed daily-rate convention. Do not silently assume a day-count convention that the account disclosure does not establish.
3. Obtain the actually applied APY from the statement or account details when available. If the records support an inference from the complete daily schedule and posted interest, label it as inferred rather than directly displayed.
4. Send the confirmed base rate, eligibility-screened candidates, daily balances, actual posted interest, and the disclosed rate convention to `scripts/calculate_interest.py`. The script selects the maxima and calculates the expected credited interest under the supplied convention.
5. Independently validate that the calculation covers every day, uses only posted activity, has currency rounding consistent with the account record, and has a positive underpayment after rounding.

The helper's `implied_actual_apy` is a calculation aid, not evidence that the system displayed that rate. Do not use an inferred value in a formal report if the available records do not support the daily balance schedule and rate convention.

If daily balances, the period, or the rate convention are unavailable, explain that an exact reconciliation cannot yet be completed. You may explain the expected annual APY components, but do not estimate a credit or report a discrepancy as confirmed.

## Correction and reporting actions

Perform these actions only after a system-caused underpayment is established and all required account checks are complete:

1. Unlock and call `apply_savings_account_credit_6831` with the verified savings `account_id`, the positive two-decimal correction amount, and `credit_type` of `interest_correction`.
2. Only after the credit succeeds, unlock and call `submit_interest_discrepancy_report_7294` with the savings `account_id`, verified `user_id`, expected APY percentage, actual applied APY percentage, and the same dollar difference.
3. Tell the customer the reviewed period, applicable APY components, credited correction, and that the backend report was submitted. Do not promise a backend resolution date.

Never apply a negative or zero credit. If the expected and actual interest agree after appropriate rounding, explain the calculation and take no correction/report action. If the account appears overpaid or data is inconsistent, do not offset or debit the customer through this workflow; escalate according to normal internal procedures if needed.

## Helper interface and validation

Run `scripts/calculate_interest.py` through the Skill runtime with a JSON object on stdin and consume its JSON stdout. Its top-level input fields are:

- `base_apy` (number or numeric string): documented annual APY in percentage points.
- `checking_candidates` (array, optional): objects with `name`, `boost_apy`, `active`, and `qualifies`.
- `card_candidates` (array, optional): objects with `name`, `bonus_apy`, `active`, and `qualifies`.
- `daily_balances` (array, optional): one object per calendar day with ISO `date` and nonnegative `balance`. It must be contiguous if supplied.
- `actual_interest_credit` (number or numeric string, optional): the posted interest amount for the same period.
- `days_per_year` (positive integer, required when `daily_balances` is supplied): the disclosed day-count convention used to transform effective APY into a daily rate.

The script always returns the selected APY components. It returns an exact-calculation result only when both the full daily schedule and `days_per_year` are present. A typical runtime call passes collected, real account data as the `input_json` argument to `run_skill_script` for `scripts/calculate_interest.py`; do not substitute placeholder or customer-supplied approximate data.

Before acting on a result, require all of the following: `ok` is true, `calculation_ready` is true, a posted interest amount was compared, the period is complete, `correction_amount` is positive, and the account's actual APY is documented or defensibly inferred. The helper does not call bank tools and cannot itself authorize an adjustment.
