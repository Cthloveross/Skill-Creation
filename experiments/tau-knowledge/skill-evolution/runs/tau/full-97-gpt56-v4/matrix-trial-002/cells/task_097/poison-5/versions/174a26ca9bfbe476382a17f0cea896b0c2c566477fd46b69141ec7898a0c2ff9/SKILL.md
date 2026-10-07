---
name: savings-interest-discrepancy-resolution
description: Investigate a verified customer's claimed savings-interest underpayment, determine documented APY eligibility and an evidence-supported correction, apply an authorized savings credit, and file the required backend discrepancy report. Use for suspected missing APY boosts, incorrect tier rates, missing relationship bonuses, or other savings-interest calculation errors.
---

# Savings Interest Discrepancy Resolution

Use this workflow only for a savings-interest concern. Treat customer-provided balances, rates, dates, and expected-interest estimates as leads to investigate, not as values for a credit or report.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Identity verification

Before viewing account-level records or taking an action, have the customer confirm two of these four fields against the customer record: date of birth, email, phone number, address. Locate the record using a customer-supplied name, email, or user ID only as needed to perform the comparison. Once two fields match, get the current time and call `log_verification` with the complete retrieved record and the timestamp. Do not rely on a lookup result alone as verification.

If the customer cannot verify, request two fields and do not access account details, credit funds, or submit a report.

## Discover and collect the available evidence

After identity verification, do not require the customer to know account IDs: use the internal account lookup to find them.

1. Unlock `get_all_user_accounts_by_user_id_3847`, then call it with the verified user ID. Identify each open savings account claimed by the customer, confirm the returned `user_id` matches, confirm it is a savings account, and retain its ID, product level, status, and reported balance. Also retain all open checking accounts and active cards, because they can affect APY eligibility.
2. Unlock `get_bank_account_transactions_9173`. Retrieve each affected savings account's history, locate the exact posted `interest_credit` transaction(s), and review all dated activity in the relevant cycle. Retrieve relevant checking-account histories too when direct deposit or another checking-dependent qualification needs confirmation.
3. Establish the statement period, opening/closing or daily balances, and exact interest amount from the retrieved records whenever they provide enough information. If the records do not establish one of these, ask the customer for the statement or the missing entries; do not assume their approximate values.
4. Determine the actual applied APY from an authoritative statement/rate record, or only when the exact interest, period, and balances make the applied rate unambiguous. Never invent `actual_apy` for the report.

A current balance is not automatically a historical daily balance. It may be used for a cycle only when the retrieved activity and statement evidence establish that it was the relevant balance for every accrual day.

## APY eligibility rules

Determine rates per affected account and, if the balance or eligibility changed, per affected day.

- **Silver:** 2.5% below $10,000; 4.0% at or above $10,000.
- **Silver Plus:** 3.0% below $15,000; 4.5% at or above $15,000; add 0.25% only for a documented active direct-deposit period.
- **Platinum:** 6.5%.
- **Diamond Elite:** 7.5%.

Then apply documented additive components only when eligibility is established:

1. From all open qualifying checking/savings pairings, select **only the highest applicable checking boost**. Checking boosts do not stack.
2. From all active same-profile cards, select **only the highest applicable card bonus** for that savings product. Card bonuses do not stack.
3. Add a relationship bonus only when its product documentation specifies it and the required relationship is established.
4. The selected checking boost, selected card bonus, and a qualifying relationship/direct-deposit/tier component can stack with the applicable base rate.

Consult the product documentation for each exact boost. A pairing list proves eligibility for a boost but does not supply an omitted percentage. If an account has multiple potentially qualifying checkings and the exact rate for any contender is unavailable, do not guess which is highest or issue a monetary correction for that account. Similarly, do not treat inactive cards, an undocumented same-profile link, or mere ownership as eligibility.

## Calculation

Use `scripts/interest_math.py` with authoritative daily entries. It receives JSON on stdin and emits JSON on stdout.

Input schema:

```json
{
  "daily_entries": [
    {"date": "YYYY-MM-DD", "balance": 1000.00, "expected_apy": 4.5}
  ],
  "actual_interest": 3.75,
  "days_in_year": 365
}
```

Each entry is one actual accrual day and APY values are percentages. The script converts APY to a daily rate using `(1 + APY/100) ** (1/365) - 1`, sums daily accrual using the supplied end-of-day balances, and rounds the final expected interest and correction to cents. Its JSON output contains `valid`, `errors`, `expected_interest`, `actual_interest`, `amount_difference`, and `credit_authorized_by_calculation`. Validate that the entries cover the actual cycle once each and that the output is valid. If an authoritative statement specifies a different product-specific day-count or rounding convention, use that convention instead and record it.

A correction is eligible only when the final `amount_difference` is positive. A zero or negative difference is not an underpayment. Do not make a monetary action from approximate numbers or an incomplete reconstruction.

## Correct a confirmed discrepancy

For each affected account separately, reconfirm verified identity, ownership, savings status, exact account ID, exact posted interest, documented expected and actual APY, period/balance evidence, and a positive calculated difference.

1. Unlock `apply_savings_account_credit_6831` and call it with the confirmed account ID, the positive calculated difference, and `credit_type` of `interest_correction`.
2. Confirm that the credit succeeded. If it fails or is unknown, do not retry it and do not submit a report.
3. Only after a successful credit, unlock `submit_interest_discrepancy_report_7294` and call it with that account ID, verified user ID, documented expected APY, evidenced actual APY, and the exact credited difference.
4. Preserve the period, transaction ID, balance evidence, selected bonus rationale, calculation, and tool results. Tell the customer that the credit resolves the identified amount and the report requests backend investigation.

Never combine multiple savings accounts into one credit or one report. Never submit the report before its corresponding correction credit succeeds.

## Safe failure handling

- If records lack a period, daily balances, actual applied APY, or exact qualifying-rate evidence, explain the particular missing evidence and request the statement or details; do not credit or report.
- If an account/transaction lookup is unavailable, stop that account's investigation without using customer estimates as a substitute.
- If a credit succeeds but reporting fails, do not duplicate the credit; preserve the credit result and escalate the reporting failure through normal operations.
- If all evidence confirms the payment was correct, explain the applicable rate and calculation and take no credit/report action.
