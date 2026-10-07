---
name: savings-interest-discrepancy-resolution
description: Investigate a verified customer's claimed savings-interest underpayment, calculate an evidence-supported correction, apply an authorized savings credit, and file the required backend discrepancy report. Use when a customer reports missing APY boosts, an incorrect tier rate, a missing relationship bonus, or another savings-interest calculation error.
---

# Savings Interest Discrepancy Resolution

Use this workflow only for a savings-interest concern. Do not infer account IDs, statement dates, daily balances, posted interest, APY components, or a correction amount from approximate customer statements.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Required information and safe stopping conditions

Before a credit or report, obtain and retain evidence for all of the following:

1. **Identity and authority:** Confirm two of the four identity fields (date of birth, email, phone number, address) against the customer record. After confirmation, retrieve the current timestamp with `get_current_time` and call `log_verification` with the complete retrieved customer record and timestamp.
2. **Ownership and account identity:** The specific savings `account_id`, confirmation that it belongs to the verified user, that it is a savings account, and its product class/status.
3. **Actual interest:** The exact posted `interest_credit` transaction amount and date for the affected statement cycle.
4. **Calculation period and balances:** Statement start/end dates plus daily end-of-day balances, or enough authoritative transaction/balance data to reconstruct them. Apply the applicable tier separately for each day.
5. **Eligibility evidence:** Active qualifying checking accounts, active cards, direct deposit where applicable, same-profile linkage, and relationship eligibility.
6. **Rate evidence:** The product's base/tier APY and each eligible additive component, including the exact linked-checking boost for that product/pairing.

If any item is unavailable, do not apply a credit and do not submit a discrepancy report. Explain exactly what is needed, such as the account identifier and statement/interest-credit details. Approximate balances and approximate interest amounts are not sufficient for a monetary adjustment.

## Tool discovery and evidence collection

After identity verification, unlock and use only the relevant internal tools:

- `get_all_user_accounts_by_user_id_3847` with the verified `user_id` to retrieve checking and savings accounts. Use this to identify the savings account and eligible checking products.
- `get_bank_account_transactions_9173` with each affected savings `account_id` to locate posted `interest_credit` entries and reconstruct qualifying activity.
- `apply_savings_account_credit_6831` only after a positive, evidence-supported correction has been calculated.
- `submit_interest_discrepancy_report_7294` only after the correction credit succeeds.

Unlock each tool with `unlock_discoverable_agent_tool` before calling it through `call_discoverable_agent_tool`. The agent must not use a customer-provided approximate amount as a tool parameter.

## APY determination

Determine an APY independently for every affected day.

1. Select the savings product's documented base APY or the daily balance's documented tier.
   - Silver: 2.5% below $10,000 and 4.0% at or above $10,000.
   - Silver Plus: 3.0% below $15,000 and 4.5% at or above $15,000; add 0.25% only for an active direct-deposit period.
   - Platinum: 6.5%.
   - Diamond Elite: 7.5%.
2. Determine qualifying linked-checking boosts from the account pairing documentation and the checking-account documentation. If more than one active qualifying checking account exists, use **only the highest** applicable boost; checking boosts never stack with one another.
3. Determine all active same-profile credit-card bonuses using the savings-product card schedule. If more than one card is eligible, use **only the highest** card bonus; credit-card bonuses never stack with one another.
4. Add any documented, independently satisfied relationship bonus. A qualifying checking boost, the highest card bonus, and a relationship bonus may stack with the selected tier/base APY.
5. Do not treat an undocumented card, pairing, placeholder rate, inactive product, or mere ownership as qualifying. Preserve the rate sources and eligibility determination in the case notes/report rationale.

## Calculation method

Use `scripts/interest_math.py` for deterministic daily compounding from authoritative daily balances and APYs. It accepts APY percentages, derives a daily rate as `(1 + APY/100) ** (1/365) - 1`, compounds each day's balance, and rounds only the final total and correction to cents. If the bank's retrieved statement exposes an authoritative product-specific day-count convention, use that convention instead and document it.

Example invocation through the skill runtime:

```json
{
  "daily_entries": [
    {"date": "YYYY-MM-DD", "balance": 1000.00, "expected_apy": 4.5}
  ],
  "actual_interest": 3.75
}
```

The script returns `expected_interest`, `actual_interest`, `amount_difference`, and validation errors. Supply the real cycle data at runtime; this example is not a correction instruction.

A reportable correction requires `amount_difference > 0.00` after cent rounding. If the result is zero or negative, do not credit or report an underpayment. Explain the outcome and retain the calculation.

## Required action order for a confirmed underpayment

1. Reconfirm all mandatory-control prerequisites, particularly verified identity, ownership, savings status, the exact account ID, and positive calculated discrepancy.
2. Call `apply_savings_account_credit_6831` with:
   - `account_id`: confirmed affected savings account ID
   - `amount`: calculated positive dollar difference
   - `credit_type`: `interest_correction`
3. Confirm the credit tool reported success. Do **not** report before this succeeds, and do not retry an outcome reported as unknown.
4. Call `submit_interest_discrepancy_report_7294` with:
   - `account_id`: the same confirmed savings account ID
   - `user_id`: verified user ID
   - `expected_apy`: the documented applicable APY percentage for the reported discrepancy (use separate cases/reports if APY changed across the cycle)
   - `actual_apy`: the evidenced APY actually applied; do not fabricate it from an approximate interest amount
   - `amount_difference`: the positive credited correction amount
5. Record the tool results, rate components, period, interest-credit transaction, and calculation rationale. Tell the customer that the credit corrects the current discrepancy and the report requests backend investigation.

For multiple savings accounts, investigate and correct each account separately. Never combine accounts into one credit or report.

## Failure handling

- If identity cannot be verified, do not access account-level details, apply credits, or file reports; request two identity fields.
- If account lookup, transaction history, statement data, or a required rate/eligibility source is unavailable, stop without a financial action and state the missing evidence.
- If a credit fails or has an unknown outcome, do not submit the report and do not repeat the credit. Escalate or obtain operational guidance as appropriate.
- If the report fails after a confirmed credit, do not duplicate the credit; preserve the successful credit reference and escalate the reporting failure.
