---
name: savings-interest-discrepancy-review
version: 1.1.0
description: Safely investigate a verified customer's claim that monthly savings interest was underpaid, calculate only a documented correction, apply it, and then file the required backend discrepancy report.
---

# Savings Interest Discrepancy Review

Use this Skill for a claimed interest underpayment on a savings account, including Silver, Silver Plus, Platinum, and Diamond Elite. The result may be a correction and report, an explanation that the credit was correct, or an evidence-required outcome. A customer estimate alone is never a basis for a credit.

## Required banking tools

Use normal banking tools for all account access and changes. Unlock and use the displayed schema for:

- `get_all_user_accounts_by_user_id_3847`
- `get_bank_account_transactions_9173`
- `apply_savings_account_credit_6831`
- `submit_interest_discrepancy_report_7294`

The calculator in this package does not access the bank or authorize an action.

## 1. Authenticate before reviewing or changing accounts

1. Resolve the profile from an identifier the customer provides.
2. Ask the customer to confirm **two of these four** profile fields: email, date of birth, phone number, and address. A name, an account label, a lookup result, or a customer-provided balance does not count as one of the four fields.
3. Match the two responses to the profile, obtain the current time, and call `log_verification` with the complete returned profile and timestamp.
4. If this cannot be completed, do not disclose account activity, calculate an account-specific outcome, apply a credit, or file a report. Explain that two profile fields are required.

## 2. Obtain and assess bank-side evidence

After verification, call `get_all_user_accounts_by_user_id_3847`. For every account at issue, verify all of the following from its result: ownership by the verified user, `class` is savings, product type, actual account ID, and an open/eligible status. Do not substitute a customer-supplied product name or account number.

Call `get_bank_account_transactions_9173` for each verified savings account. Locate the posted monthly interest credit and review all returned balance-changing activity around it. Establish from bank records:

- the exact interest-credit amount and posting date;
- the statement-cycle start and end dates;
- balances and activity needed to determine the applicable rate for every day or rate segment; and
- whether a correction for the same cycle was already posted.

A monthly credit's date by itself does not prove its statement-cycle dates, daily balances, or actual applied APY. Likewise, a current balance does not prove the balance for the prior cycle. If the bank-side data does establish a complete constant-balance/rate cycle, document why (for example, full activity confirms no in-cycle balance changes); then a single segment can be calculated. If it does not, request the missing statement-cycle record or complete activity. Do not use an estimate, a rounded recollection, or a guessed calendar month to fill a gap.

## 3. Establish expected and actual APY, using the terms in force for the cycle

Preserve the evidence for every component and apply it to the relevant days only.

- **Silver:** 2.5% or 4.0% base tier; the documented higher-tier threshold is $10,000.
- **Silver Plus:** 3.0% Tier 1 or 4.5% Tier 2; Tier 2 requires at least $15,000. A 0.025% relationship bonus applies only when its eligibility criteria were met.
- **Platinum:** 6.5% documented base APY.
- **Diamond Elite:** 7.5% documented base APY.
- For any product with tiering, split the calculation when the verified daily balance crosses a tier threshold.
- A checking boost applies only to a documented checking/savings pairing that was active and linked under the same profile in that cycle. Multiple checking boosts do **not** stack: use only the highest applicable boost.
- Credit-card APY bonuses also do **not** stack: use only the highest eligible card bonus for that savings product. The selected card bonus may stack with the selected checking boost and a separately documented relationship or tier component.
- Never infer an absent boost percentage from a checking/card name, current products, the customer's expected payment, or another product's terms. If the exact component or its cycle eligibility is not documented, the expected APY is not established.

Get the actual APY from the statement, account record, or other bank evidence that identifies the rate used. Do not reverse-engineer an `actual_apy` for a required report merely from a rounded monthly payment.

## 4. Calculate and decide

Calculate the expected interest over the exact cycle with the institution's evidenced daily-rate convention and daily compounding method. For a constant-rate segment, use `scripts/calculate_daily_interest.py`; run it once per verified segment and sum unrounded segment amounts before applying the bank's documented posting rounding rule. Do not assume that APY divided by 365, 360, or 12 is the bank's daily calculation convention unless the applicable account record or terms establishes it.

Before a correction, confirm all of these:

1. verified identity, ownership, savings product, and account ID;
2. exact cycle, posted interest, and balance/activity evidence;
3. documented expected APY components and supported actual APY;
4. expected interest minus posted interest is positive after the documented currency rounding; and
5. no prior correction already covers that cycle.

If a condition fails, do not use `goodwill_credit` as a substitute and do not file a speculative report. State what is unavailable and that no underpayment has been verified.

## 5. Correct, then report

For each account that independently passes every check:

1. Call `apply_savings_account_credit_6831` with the verified `account_id`, the positive exact difference, and `credit_type: "interest_correction"`.
2. Confirm success. If the result is failed, timed out, or ambiguous, do not retry blindly and do not submit a report; inspect status/history first.
3. Only after a successful credit, call `submit_interest_discrepancy_report_7294` with the same account ID and user ID, supported expected and actual APY percentages, and the same amount difference.
4. Tell the customer only the successful credit amount and a new balance returned by the credit or a subsequent lookup. Do not claim a balance that was not returned.

For an unresolved account, explain that an exact cycle, interest entry, daily balances/activity, or applicable rate component is missing. If the customer asks how to send records, ask for the statement containing the interest entry or a complete activity record for the relevant statement cycle; do not claim that an undocumented upload, secure-message, or statement-download feature is available.

## Calculator interface

Run `scripts/calculate_daily_interest.py` with one JSON object on stdin; it writes one JSON object to stdout and performs no bank action.

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

`daily_rate` is a decimal daily fraction, not a percentage. `days` must contain every consecutive verified date in a constant-rate segment. Use `round_daily_interest_to_cents: true` only when bank evidence establishes daily cent rounding. `actual_interest` is optional. A result with `ok: false`, missing dates, non-positive `difference_rounded_to_cents`, or an unsupported rate assumption must not be used for a banking action.
