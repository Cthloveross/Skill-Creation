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
3. Establish the statement period, opening/closing or daily balances, and exact interest amount from the retrieved records whenever they provide enough information. Do not ask the customer for account IDs that the verified account lookup can supply.
4. Determine the actual applied APY from an authoritative statement/rate record, or only when the exact interest, period, and balances make the applied rate unambiguous. Never invent `actual_apy` for the report.

A current balance is not automatically a historical daily balance. It may be used for a cycle only when the retrieved activity and statement evidence establish that it was the relevant balance for every accrual day. In particular, a monthly interest credit dated at the end of a calendar month, a complete account history showing no balance-changing activity in that month, and an authoritative account balance can establish a constant-balance monthly case. Record that inference and the exact dates. If the posted credit exactly reconciles to one documented rate under the bank's evidenced monthly convention, that reconciliation can establish the actual applied rate; it is not a reason to substitute a customer estimate. If this evidence is absent, ask for the statement or the missing entries and do not act.

## APY eligibility rules

Determine rates per affected account and, if the balance or eligibility changed, per affected day.

- **Silver:** 2.5% below $10,000; 4.0% at or above $10,000.
- **Silver Plus:** 3.0% below $15,000; 4.5% at or above $15,000; add 0.25% only for a documented active direct-deposit period.
- **Platinum:** 6.5%.
- **Diamond Elite:** 7.5%.

Use these documented card schedules (percentage points); among cards in a schedule, choose only the highest active same-profile value:

| Savings product | Card bonus schedule |
| --- | --- |
| Silver | Bronze 0; Silver 0.1; Gold 0.5; Eco 2.2; Green 0; Crypto-Cash Back 0.5; Platinum Rewards 0.2; Diamond Elite 0.25 |
| Platinum | Bronze 0; Silver 0; Gold 0.15; Platinum Rewards 0.25; Diamond Elite 0.35; Eco 0; Green 0; Crypto-Cash Back 0 |
| Diamond Elite | Bronze 0; Silver 0; Gold 0; Platinum Rewards 0.1; Diamond Elite 0.5; Eco 0; Green 0; Crypto-Cash Back 0.15 |
| Silver Plus | Bronze 0.15; Silver 0.15; Gold 0.2; Platinum Rewards 0.15; Diamond Elite 0.4; Eco 0.45; Green 0.1; Crypto-Cash Back 0 |

Known documented checking boosts are Bluest-to-Silver 0.45, Green-to-Silver 0.25, Gold Years-to-Silver 0.6, Blue-to-Silver Plus 0.35, Blue-to-Platinum 0.8, and Evergreen-to-Diamond Elite 0.15 percentage points. Other qualifying pairings may exist, but do not assign a percentage unless its documentation supplies one.

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

Each entry is one actual accrual day and APY values are percentages. The script converts APY to a daily rate using `(1 + APY/100) ** (1/365) - 1`, carries accrued interest forward for daily compounding while applying each supplied end-of-day principal balance, and rounds the final expected interest and correction to cents. Its JSON output contains `valid`, `errors`, `expected_interest`, `actual_interest`, `amount_difference`, and `credit_authorized_by_calculation`. Validate that the entries cover the actual cycle once each, are consecutive calendar days, and that the output is valid. If an authoritative statement specifies a different product-specific day-count or rounding convention, use that convention instead and record it.

A correction is eligible only when the final `amount_difference` is positive. A zero or negative difference is not an underpayment. Do not make a monetary action from approximate numbers or an incomplete reconstruction.

For an evidenced constant-balance monthly case where the bank's actual monthly convention is established from the posted payment, calculate the expected and actual interest using that same evidenced convention rather than treating a customer approximation as a statement. Document why that convention and the balance apply. Otherwise use the daily-entry calculation above (or an authoritative statement convention).

When an omitted component prevents determination of a complete expected APY, do not guess it or issue a partial correction. The discrepancy-report fields require the APY the customer should have received, so seek the missing documentation before a financial action.

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

## Customer-facing completion

State what was verified or reviewed without exposing unnecessary full account identifiers. When evidence is incomplete, name the exact statement fields needed (cycle start/end dates, opening balance or daily activity, and the posted interest-credit entry) and confirm that no credit or report has been submitted. If the customer says they will obtain the statements, acknowledge that plan and invite them to return with the details; do not imply that an adjustment is pending or already approved.
