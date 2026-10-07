---
name: investigate-silver-savings-interest-discrepancy
description: Verify a customer and investigate a suspected Silver Account interest underpayment. Use when an eligible agent must retrieve savings accounts and transactions, calculate Silver APY and daily-compounded interest, then apply an interest-correction credit before filing an internal discrepancy report.
---

# Investigate a Silver Account interest discrepancy

Use this Skill for a customer who believes Silver Account interest was too low. It supports the required order: verify identity and ownership, investigate, calculate, **apply a credit first**, then submit the backend report.

## Policy facts used by this Skill

- Silver base APY is 2.5% below the $10,000 daily balance tier and 4.0% at or above it. Interest accrues and compounds daily and is credited monthly.
- A qualifying linked checking boost, the highest applicable one only, stacks with the highest applicable credit-card bonus and any confirmed relationship bonus.
- For Silver, Green Account checking provides a 0.25% boost and Bluest Account checking provides a 0.45% boost, when the account pairing is qualifying and linked. Do not infer a percentage for another checking type without its product documentation.
- Credit-card bonuses do not stack with one another. Use only the highest applicable active card bonus documented for the customer's Silver Account.
- The Silver relationship bonus is 0.025%, but apply it only when eligibility is affirmatively established. Do not treat merely seeing multiple accounts as conclusive eligibility if the available records do not establish it.
- An interest correction credit is permitted only for a confirmed interest-calculation error and must be a positive amount.

The packaged calculator deliberately accepts all bonus candidates at runtime. This keeps it valid when the customer's products differ from the common Green/Bluest cases.

## Required investigation workflow

1. **Verify identity before disclosing or changing account information.**
   - Obtain two of date of birth, email, phone number, and address from the customer, compare them with the identified customer record, then call `log_verification` with all requested identity fields and the current timestamp.
   - A name lookup alone is not two-factor identity verification. Do not use profile data already displayed to the agent as if the customer confirmed it.
   - If verification fails or ownership is disputed, do not investigate account details or apply a credit. Follow the ownership-dispute escalation procedure.

2. **Retrieve and validate the bank accounts.**
   - Unlock `get_all_user_accounts_by_user_id_3847`, then call it through `call_discoverable_agent_tool` with `{"user_id":"<verified user id>"}`.
   - Select only an active savings account belonging to that verified user whose class/type establishes that it is the Silver Account. If there is more than one plausible account, ask the customer to identify it; do not guess.
   - Review all active checking accounts returned. Confirm that a claimed checking account is both a documented qualifying pairing and linked to the Silver savings account before using its boost. If several qualify, retain only the largest boost.
   - Retrieve credit-card accounts with `get_credit_card_accounts_by_user` when needed. Include only active cards with a documented Silver APY bonus, and retain only the largest such bonus.

3. **Retrieve the transaction history.**
   - Unlock `get_bank_account_transactions_9173`, then call it for the selected savings `account_id`.
   - Locate the relevant **posted** `interest_credit` for the customer’s statement cycle. Pending transactions are not proof of paid interest. Record its date and positive amount.
   - Use the ledger, statement, and account balance information to establish the daily balances for the cycle. If the transaction history cannot reliably establish the cycle’s daily balance history or the relevant cycle, request the statement/balance history. Do not fabricate an expected amount from only a current balance.

4. **Calculate and validate the discrepancy.**
   - Supply complete daily balances, the posted interest amount, tier policy, and only verified bonus eligibility to `scripts/analyze_silver_interest.py`.
   - Inspect its JSON. A `ready_for_correction` result means the calculated, rounded expected interest exceeds the posted credit. `amount_difference` is the permitted positive credit amount.
   - The calculator returns an APY inferred from the credited amount where an actual applied APY is not separately recorded. Review that inference against transaction/statement evidence. When balances crossed the $10,000 tier, it also returns an effective balance-weighted report APY and flags `rate_varies_by_day`; preserve the daily-balance workpaper for backend review.
   - If essential inputs are absent, eligibility is not established, or the calculated difference is zero or negative, do not apply a correction or submit a discrepancy report. Explain what remains needed or that no underpayment was confirmed.

5. **Correct first, then report.**
   - Unlock `apply_savings_account_credit_6831` and call it with the selected savings account, the calculator’s positive `amount_difference`, and `credit_type` set exactly to `interest_correction`.
   - Confirm that the credit call succeeded. If it fails, do **not** submit the discrepancy report as though the customer had been made whole.
   - Only after successful credit, unlock `submit_interest_discrepancy_report_7294` and call it with:
     ```json
     {
       "account_id": "<selected savings account id>",
       "user_id": "<verified user id>",
       "expected_apy": "<calculator report_expected_apy>",
       "actual_apy": "<calculator actual_apy_inferred or verified applied APY>",
       "amount_difference": "<positive credited amount>"
     }
     ```
   - Tell the customer that the correction was applied and that the report requests investigation of the underlying calculation. Do not claim the backend issue is already fixed.

## Tool or data failures

- A tool/service error that prevents required account lookup, transaction retrieval, crediting, or report submission is a `technical_system_error` when transferring to a human agent. Include the verified customer, selected account if known, statement cycle, attempted step, and error in the transfer summary.
- Missing customer documentation is not itself a reason to invent a discrepancy or credit. Ask for the specific statement cycle, interest credit date/amount, and daily/statement balance history if the internal ledger cannot establish them.
- Never submit a report before a successful interest-correction credit for a confirmed underpayment.

## Calculator interface

Run `scripts/analyze_silver_interest.py` with JSON on stdin. It emits one JSON object on stdout.

Required input fields:

```json
{
  "daily_balances_complete": true,
  "daily_balances": [{"date": "YYYY-MM-DD", "balance": 0}],
  "actual_interest_credit": 0,
  "tier_threshold": 10000,
  "low_tier_apy": 2.5,
  "high_tier_apy": 4.0,
  "checking_candidates": [
    {"name": "<checking product>", "active": true, "linked": true, "qualifying": true, "boost_apy": 0}
  ],
  "card_candidates": [
    {"name": "<card product>", "active": true, "applicable": true, "bonus_apy": 0}
  ],
  "relationship": {"eligible": false, "bonus_apy": 0.025}
}
```

`daily_balances` must cover every day in the statement cycle exactly once, with nonnegative balances. The tool chooses the maximum verified checking boost and card bonus, not their sum. It validates dates, numeric values, and full-balance-history confirmation. Output has `status` of `ready_for_correction`, `no_underpayment`, `insufficient_data`, or `invalid_input`; only the first status can support the credit/report sequence.

The calculation uses a 365-day APY conversion: daily rate = `(1 + APY/100)^(1/365) - 1`, with daily compounding and cents rounded only for the final expected paid interest and correction amount. Its output includes components, expected and posted amounts, report APYs, and validation notes so the agent can retain a reviewable workpaper.
