---
name: silver-savings-interest-review
description: Review a suspected Silver Account monthly interest discrepancy. Use when a customer questions a low interest credit and the executor must gather statement evidence, determine applicable tier and APY bonuses, calculate daily-compounded expected interest, and—only when fully substantiated—correct and report a system error.
---

# Silver Savings Interest Review

## Purpose and governing facts

Silver Account interest is accrued daily and credited monthly. The base APY is 2.5% for a daily balance below $10,000 and 4.0% for a daily balance at or above $10,000. A different tier may therefore apply on different days.

Applicable additions must be established, not assumed:

- A qualifying, linked Green checking account and Silver savings account pairing provides a +0.25 percentage-point APY boost.
- A qualifying linked Bluest checking account provides a +0.45 percentage-point Silver boost.
- If multiple eligible checking boosts exist, use only the highest one; never add checking boosts together.
- The eligible relationship bonus is +0.025 percentage point.
- Credit-card APY bonuses, when documented and eligible, stack with the selected checking boost and relationship bonus, but only the highest card bonus applies.
- Linked-account eligibility requires common ownership/tax ID and both accounts to be open and in good standing.

Do not invent a boost amount for a checking/savings pairing whose account documentation is unavailable. Do not presume that an account is linked merely because the customer holds both products.

## Conversation path

### If the customer has online banking but has not supplied the figures

Give the customer this first, focused set of steps:

1. Sign in to online or mobile banking and open the **Silver Account**.
2. In account details, note the APY currently displayed and whether the account indicates that a checking relationship is linked.
3. Open **Activity** and find the newest transaction labeled **interest credit**. Record its posting date, amount, and whether it is posted (not pending).
4. Open or download the statement covering that credit. Record the statement start and end dates and the daily balances. If daily balances are not shown, retain the opening balance plus every posted deposit and withdrawal in the period.
5. Check the balance history for days below versus at/above $10,000, because the rate changes at that threshold.

Ask for the recorded figures rather than account credentials, a full account number, or unrelated personal information. Explain that an amount cannot be reliably judged from the current balance alone. The customer may request complete posted and pending history, including interest payments and transfer details, from support if statements are inaccessible.

For the current complaint, it is appropriate to mention that a linked, eligible Green checking account could add 0.25 percentage point to Silver APY, but do not state that it was applied until linkage and account status are confirmed.

### If the executor will inspect account data

Before disclosing account-specific information or using account data for this request, verify ownership according to the runtime's identity procedure: obtain and match two of date of birth, email, phone number, and address; obtain the current timestamp; then create the verification audit record. A name alone and an assertion of online-banking access are not sufficient verification.

After verification:

1. Unlock and use `get_all_user_accounts_by_user_id_3847` with the verified user ID. Select the customer-owned Silver savings account and confirm it is open/active. Review all active checking accounts and relevant products.
2. Unlock and use `get_bank_account_transactions_9173` for that Silver account. Locate posted `interest_credit` records; transaction results are reverse chronological. Do not treat a pending interest credit as paid interest.
3. Obtain the matching statement period and daily balances. Transaction history alone may not establish every daily closing balance unless a period opening balance and all in-period activity are also known.
4. Establish each APY component from documented, current eligibility: daily base tier, one highest eligible linked-checking boost, at most one highest eligible card bonus, and any confirmed relationship bonus.
5. Calculate the expected interest with `scripts/silver_interest_review.py`, retaining the inputs and result for the case record.

A low monthly credit can be correct when balances spent time below $10,000, when a deposit arrived late in the cycle, or when an expected boost was not actually eligible. Clearly distinguish these explanations from a system error.

## Calculation method

Use `scripts/silver_interest_review.py` for repeatable calculations. It accepts JSON on stdin and emits JSON on stdout. It has two operations:

- `find_interest_credits`: filters supplied transaction objects to posted interest-credit candidates.
- `calculate`: calculates daily accruals from a complete contiguous list of daily balances and finalized, eligible bonus values.

Example calculation input (values are illustrative only; replace every value with runtime evidence):

```json
{
  "operation": "calculate",
  "daily_balances": [
    {"date": "2025-01-01", "balance": "9000.00"},
    {"date": "2025-01-02", "balance": "10000.00"}
  ],
  "checking_boosts_pct": ["0.25"],
  "credit_card_bonuses_pct": [],
  "relationship_bonus_pct": "0.025",
  "daily_rate_method": "effective_apy_daily",
  "actual_interest_credit": "1.23"
}
```

The script adds the selected bonus percentages to the base APY for each day, selects the maximum supplied checking and card bonus rather than summing them, and totals the daily accruals. `effective_apy_daily` derives a daily rate as `(1 + APY/100)^(1/365) - 1`, consistent with interpreting APY as an effective annual yield. If the institution's statement explicitly documents a different daily-periodic-rate convention, pass `nominal_apy_div_365` and record that source. Do not silently choose a convention contrary to the statement.

The calculation requires every calendar day in the review period. It rejects gaps, duplicate dates, invalid amounts, and negative bonus inputs. It rounds only the final expected credit to cents for comparison and reports the unrounded total separately.

Example transaction-filter input:

```json
{
  "operation": "find_interest_credits",
  "transactions": [
    {"date": "01/31/2025", "amount": 12.34, "type": "interest_credit", "status": "posted"}
  ]
}
```

Validate that the returned credit date belongs to the statement being reviewed, that it is posted, and that calculation days exactly cover that statement period. A result with `ok: false`, warnings about missing evidence, or no posted interest credit is not sufficient to issue a correction.

## Remediation controls

Only act when all of the following are true:

- identity and ownership have been verified and logged;
- the target is a Silver savings account;
- the relevant posted interest credit and statement/daily-balance evidence are identified;
- eligibility and APY components are documented;
- the computed discrepancy is positive after the institution's permitted rounding treatment; and
- the actual applied APY is known from reliable account or statement evidence, rather than guessed from a single monthly credit.

If these conditions are met, unlock and use `apply_savings_account_credit_6831` with the Silver account ID, the positive substantiated difference, and `credit_type: "interest_correction"`. Then, **after the credit succeeds**, unlock and submit `submit_interest_discrepancy_report_7294` with the account ID, user ID, supported expected and actual APYs, and the same amount difference.

Do not apply a goodwill credit merely because calculation inputs are missing. Do not submit a report with guessed APY values. Where the period contains multiple tiers, report the specifically affected tier/component only if its expected and actual APYs can be stated accurately; otherwise collect additional statement or system evidence first.

If no discrepancy is established, explain the tier-by-day result and applicable eligibility finding, and offer support or secure messaging for a formal statement/history request.
