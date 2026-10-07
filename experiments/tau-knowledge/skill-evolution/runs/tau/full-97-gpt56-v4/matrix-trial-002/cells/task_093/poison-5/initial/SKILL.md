---
name: investigate-silver-savings-interest-discrepancy
description: Verify a customer's identity, investigate a claimed Silver Account interest underpayment using account and transaction records, calculate the applicable daily-compounded interest, and—only for a confirmed discrepancy—apply the authorized savings credit before filing the required backend report.
---

# Investigate a Silver Account Interest Discrepancy

Use this workflow when a customer believes a monthly interest payment on a Silver savings account is too low. It supports investigation and, where the records establish an error, the documented interest-correction and reporting process. It does not authorize a credit based only on an estimate or a customer's impression.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Safety and prerequisites

1. Identify the customer using an identifier they provide (such as email or full name), then retrieve the matching profile with the appropriate user-information lookup.
2. **Before any banking action or account-specific disclosure**, have the customer confirm two of the following profile fields and compare each with the retrieved record: date of birth, email, phone number, or address. Do not treat information merely supplied during an unverified request as confirmation of two fields.
3. Obtain the current timestamp with `get_current_time` and call `log_verification` with the complete retrieved profile and timestamp only after the two-field match succeeds.
4. Confirm that the person is the account holder and that the savings account is active and belongs to the verified customer. If identity, authority, ownership, or product status cannot be confirmed, stop the investigation; do not retrieve account transactions, disclose them, apply a credit, or submit a report.
5. Never apply a credit or submit a discrepancy report if the required account records, statement period, balances, interest transaction, or calculation inputs are missing. Explain what is needed or route the customer to secure support for a complete history.
6. Treat a failed, ambiguous, or `UNKNOWN` action result as unresolved. Do not retry a credit or report blindly, and never claim an action succeeded without a successful tool result.

## Applicable Silver Account rules

Use the records and product eligibility at the period being investigated, rather than assumptions based on the customer's current description.

- The base balance-tier APY is **2.5%** below $10,000 and **4.0%** at or above $10,000. The tier is determined from each day's balance.
- Interest accrues on daily balances, compounds daily, and is credited monthly. For a stated APY `a` as a decimal, use daily periodic rate `(1 + a)^(1/365) - 1`.
- A Green checking account paired with a Silver Account is eligible for a **+0.25 percentage-point** linked-checking boost. If more than one eligible checking account applies, use only the highest applicable checking boost; checking boosts do not stack.
- Credit-card APY bonuses do not stack. Use only the highest applicable active, linked card bonus documented for the Silver Account: Bronze Rewards +0%, Silver Rewards +0.1%, Gold Rewards +0.5%, EcoCard +2.2%, Green Rewards +0%, Crypto-Cash Back +0.5%, Platinum Rewards +0.2%, or Diamond Elite +0.25%.
- A linked Platinum Rewards Card and Silver Account under the same profile also qualifies for a **+0.025 percentage-point** relationship bonus when eligible. Do not infer this bonus merely from another product or from the existence of multiple accounts.
- The selected checking boost, selected card bonus, and any documented eligible relationship bonus are additive to the daily balance-tier APY. Do not invent a boost when the pairing, link, active status, or eligibility cannot be verified.

## Investigation procedure

1. After identity verification, unlock and use `get_all_user_accounts_by_user_id_3847` with the verified `user_id`. Locate active Silver savings account(s), confirm ownership, and ask the customer which account/period to investigate if more than one is plausible.
2. Unlock and use `get_bank_account_transactions_9173` with the selected savings `account_id`. Find the relevant posted `interest_credit`, recording its date, amount, and statement period. Review activity needed to reconstruct the daily balances for that cycle. Pending transactions are not substitutes for posted interest or final daily balances.
3. Determine eligibility during that cycle:
   - Identify the active checking accounts from the account lookup and retain only documented qualifying Silver pairings.
   - If card information is needed, use the available card-account lookup for the verified user and evaluate active, profile-linked cards; select at most one highest documented card bonus.
   - Verify any Platinum relationship-bonus linkage instead of assuming it.
4. Build a daily-balance schedule for every day in the statement cycle. Use the actual balance for each date, assigning the base 2.5% or 4.0% tier separately for that date. If transactions alone do not make posting dates and end-of-day balances reliable, obtain the statement/daily balance record rather than guessing.
5. Run `scripts/calculate_silver_interest.py` with the daily balances, applicable percentage-point bonuses, and actual posted interest. The helper returns the expected monthly interest rounded once to cents, the actual amount, the positive correction amount if any, and an auditable daily breakdown.
6. Independently review that the output inputs reflect the records. A correction exists only when the expected amount exceeds the actual posted interest after correct eligibility and rounding. If the actual payment is correct or higher, explain the result and do not create a credit or report.
7. For a confirmed underpayment, unlock and call `apply_savings_account_credit_6831` first with the savings `account_id`, the positive calculated difference, and `credit_type` set to `interest_correction`. Confirm its successful result before proceeding.
8. Only after the credit succeeds, unlock and call `submit_interest_discrepancy_report_7294` with `account_id`, `user_id`, the calculated expected APY percentage, actual APY percentage supported by the credited transaction/calculation evidence, and the positive dollar `amount_difference`. Do not fabricate an actual APY: if it cannot be derived from the relevant records, escalate for investigation rather than filing an inaccurate report.
9. Tell the customer the investigation outcome. If a credit was successfully applied, state the amount and the new balance only if returned by the banking tool. State that the backend report was filed only after its tool call succeeded.

## If information cannot be obtained

If the agent cannot access the account history after identity verification or cannot reconstruct daily balances, do not use a goodwill credit as a substitute for an interest correction. Ask for a secure statement or direct the customer to support, online help, or the mobile app to request complete transaction history, including interest payments. Explain that a precise review needs the statement period, posted interest date and amount, and daily balances or transactions sufficient to derive them.

## Calculator interface

Run the packaged helper with JSON on standard input and read JSON from standard output:

```json
{
  "daily_balances": [{"date": "YYYY-MM-DD", "balance": "10000.00"}],
  "checking_bonus_pct": "0.25",
  "card_bonus_pct": "0.00",
  "relationship_bonus_pct": "0.000",
  "actual_interest": "35.12"
}
```

All percentage fields are percentage points, not decimal rates. `daily_balances` must contain exactly one nonnegative end-of-day balance for each consecutive date in the statement cycle. `actual_interest` is optional when only an estimate is requested. A successful result includes `expected_interest`, `correction_amount`, `daily_rate_method`, and a daily accrual breakdown. Errors identify invalid amounts, invalid dates, missing dates, or unsupported negative bonuses. Validate the schedule and the returned correction before using any monetary amount in a banking action.
