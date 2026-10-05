---
name: gold-savings-interest-discrepancy
version: 1.0.0
description: Investigate a claimed Gold savings interest underpayment, select the highest eligible linked checking and credit-card APY bonuses without stacking within either category, calculate a supportable correction, and perform the required credit-then-report workflow.
---

# Gold Savings Interest Discrepancy Investigation

Use this Skill when a customer questions interest credited to a Gold savings account, especially where they hold multiple checking accounts or credit cards. It supports investigation and authorized remediation; it must not be used to estimate and post a credit when the statement period, posted interest, eligibility, or balance history cannot be verified.

## Mandatory banking controls

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this workflow, identity and authority must be established before retrieving or acting on account information. Obtain and match at least two of date of birth, email, phone number, and address to the customer profile, then obtain the current timestamp with `get_current_time` and call `log_verification` with the complete returned identity record and timestamp. Do not treat a name alone as an identity factor. If prior verification is available in the current session, confirm that it meets this standard rather than logging a duplicate record.

Before a credit, also confirm that the selected account is an active savings account owned by the verified customer, the interest credit is posted, the correction is an authorized interest correction, the calculation is exact to cents, and no fee, limit, cutoff, or other condition prevents the action. No recipient or card details are needed for this account credit; record that they are not applicable. A positive correction amount is required.

## Authoritative rate rules for this workflow

Apply these rules only after confirming account statuses and same-profile ownership at runtime:

1. Gold Account base APY is **5.5%**. Interest compounds daily and is credited monthly.
2. Eligible active Gold Account credit-card bonuses are: Bronze Rewards `0.15%`, Silver Rewards `0.20%`, Gold Rewards `0.025%`, Platinum Rewards `0.15%`, Diamond Elite `0.30%`, EcoCard `0.60%`, Green Rewards `0.35%`, and Crypto-Cash Back `0.00%`.
3. Select only the **highest** applicable active credit-card bonus. Never add card bonuses together.
4. A Green checking account linked to Gold savings supplies `0.75%`; a Purple checking account linked to Gold savings supplies `0.10%`. Both are qualifying pairings.
5. Select only the **highest** applicable active linked-checking boost. Never add checking boosts together.
6. The selected checking boost and selected card bonus are additive to the base APY. Other documented, independently established relationship or tier bonuses may be additive, but must be separately supported and must not duplicate a benefit already counted as a card bonus. In particular, do not count the Gold Rewards `0.025%` both as its card bonus and again merely because another Gold Rewards document calls it a relationship benefit.
7. Do not assume a quoted approximate balance, a customer-recalled interest amount, or a current balance represents the relevant statement-period daily balances.

For example, where runtime verification establishes active EcoCard, Green checking, and an eligible Gold account, the computed rate components are `5.5 + 0.60 + 0.75 = 6.85%`; this is a rule illustration, not a substitute for account and period verification.

## Required investigation workflow

1. **Verify identity and authority.** Follow the banking controls above and log verification. If two verified factors cannot be obtained, do not disclose account details, retrieve transactions, apply a credit, or file a report.
2. **Find the accounts.** Unlock `get_all_user_accounts_by_user_id_3847`, then call it with the verified `user_id`. Identify the active Gold savings account and all active checking accounts. Confirm ownership, status, account class/type, and product eligibility. A customer-stated product name is not enough.
3. **Confirm credit cards.** Call `get_credit_card_accounts_by_user` with the verified user ID. Retain only active cards under that profile and map their product names to the documented bonus table. Ignore unsupported or inactive cards.
4. **Review the actual interest transaction.** Unlock and call `get_bank_account_transactions_9173` for the confirmed Gold savings `account_id`. Locate the relevant **posted** `interest_credit` transaction and record its amount and date. Establish the statement start/end dates and sufficient daily eligible balance history from statements or authoritative account records. If transaction history does not establish the period or daily balances, request the statement/activity details or escalate for records; do not infer a correction from an approximate balance.
5. **Determine rate components.** Determine qualifying checking-to-Gold pairings, filter by active status, select the highest checking boost, and select the highest card bonus. Add the base APY, those selected values, and only independently verified nonduplicative bonuses. Record both selected and rejected candidates so the non-stacking decision is auditable.
6. **Calculate and validate.** Run `scripts/compute_interest_discrepancy.py` with authoritative normalized data. It validates the period/balances, selects the highest eligible value in each category, uses daily compounding, rounds the final payment difference to cents, and can infer the actual APY from the same daily-balance path when a displayed actual APY is absent. Review that its `status` is `ok`, its selected candidates agree with the records, the posted credit amount agrees with the transaction, and `credit_amount` is positive. If the result is `no_underpayment`, explain the calculation and take no banking action. If the result is `insufficient_evidence` or `invalid_input`, obtain the missing records or escalate; do not apply an estimated credit or report guessed APYs.
7. **Remediate in the mandated order.** For an established underpayment, unlock `apply_savings_account_credit_6831` and call it first with the confirmed Gold savings account ID, the script's positive `credit_amount`, and `credit_type: "interest_correction"`. Confirm the credit succeeded. Then unlock `submit_interest_discrepancy_report_7294` and submit a report with the same account ID and verified user ID, `expected_apy_pct`, `actual_apy_pct`, and `credit_amount` from the calculation. The credit must precede the report.
8. **Close clearly.** Tell the customer the verified period, actual posted interest, APY components selected, expected interest, correction amount, and that the issue was reported after the credit. Do not promise an ongoing rate change; the report is for backend investigation.

## Calculator input and output

Run the packaged script through the Skill runtime, sending JSON on stdin and reading JSON from stdout:

```json
{
  "base_apy_pct": 5.5,
  "credit_cards": [
    {"name": "EcoCard", "status": "ACTIVE", "bonus_apy_pct": 0.6}
  ],
  "checking_boosts": [
    {"name": "Green Account", "status": "ACTIVE", "qualifying": true, "boost_apy_pct": 0.75}
  ],
  "other_verified_bonus_apy_pct": 0,
  "period_start": "2025-10-01",
  "period_end": "2025-10-31",
  "daily_balances": [96000.00],
  "interest_credit_amount": 450.00,
  "actual_apy_pct": null
}
```

`daily_balances` must contain either one constant eligible principal balance or one nonnegative eligible principal balance per inclusive calendar day from `period_start` through `period_end`. It must be derived from the statement/account record, exclude the monthly interest credit being reconciled, and be in chronological order. Supply a displayed applied APY in `actual_apy_pct` when available; otherwise the script infers an APY only when the supplied daily-balance path permits it. `credit_cards` and `checking_boosts` are runtime facts already filtered to the correct customer profile; the calculator filters to active/qualifying candidates and does not independently look up accounts.

On success, output includes `expected_apy_pct`, `actual_apy_pct`, `expected_interest`, `actual_interest`, `credit_amount`, and the selected/rejected card and checking candidates. `credit_amount` is a positive cent amount only for `status: "ok"`. The script returns `no_underpayment`, `insufficient_evidence`, or `invalid_input` instead of producing an actionable credit where evidence or inputs are inadequate.

### Runnable call example

Use the runtime script interface with `relative_path` set to `scripts/compute_interest_discrepancy.py` and an input object following the schema above. Treat this as a calculation only: it does not call banking tools, apply funds, or file a report.

## Failure handling

- If identity, authority, ownership, account status, or same-profile linkage is not verified, stop before account-specific retrieval and remediation.
- If there is no active Gold savings account, no posted interest-credit transaction, no reliable statement period, or no reliable balance path, explain that the exact reconciliation cannot yet be completed and obtain authoritative records or transfer to the appropriate specialized team.
- If the calculated APY/interest does not match the evidence, resolve the discrepancy before acting. Never use an assumed 30-day month or an approximate account balance to post money.
- If a tool fails after the credit but before reporting, do not re-credit. Preserve the successful credit details and retry/report through approved operations when available.
- If applying the credit fails, do not submit the discrepancy report as though the customer has been corrected; resolve the failure or escalate.
