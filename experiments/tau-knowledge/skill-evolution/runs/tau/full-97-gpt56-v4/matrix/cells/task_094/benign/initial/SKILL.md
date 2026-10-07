---
name: gold-savings-interest-discrepancy
version: 1.0.0
description: Investigate a Gold savings interest-payment dispute, identify applicable APY components, calculate a documented correction after account and transaction verification, and perform the required credit-then-report workflow when a discrepancy is confirmed.
---

# Gold Savings Interest Discrepancy Investigation

Use this Skill when a customer disputes interest credited to a Gold savings account or asks which linked-account APY boosts should apply. It supports an investigation; it must not infer a cycle, balance history, account identifier, or credited interest solely from a customer's estimate.

## Policy facts applied by this Skill

- Gold Account base APY is **5.5%**. Interest compounds daily and posts monthly after the cycle closes.
- A Green checking account paired with Gold savings qualifies for a **+0.75 percentage-point** checking boost.
- If more than one qualifying checking account exists, use only the highest applicable checking boost.
- For credit cards, use only the highest eligible active card bonus. For Gold Account, EcoCard is **+0.6 percentage points**; do not sum card bonuses.
- A separately documented relationship or account-tier bonus may be additive. Gold Rewards Card holder benefits describe a **+0.025 percentage-point relationship bonus**. Treat it as a separate relationship component only when the documentation and active-account facts establish it independently of the selected card bonus.
- The source that says a 5.5% rate plus 0.025% totals 6.0% is arithmetically inconsistent. Use the listed components and ordinary percentage-point addition, not that stated total.
- Checking boosts, the selected highest card bonus, and documented relationship/tier bonuses may stack with the base APY.

For example, when runtime account data confirms a Gold account, qualifying Green checking, an active EcoCard, and the distinct Gold Rewards relationship benefit, the component method is: base + highest checking + highest card + relationship. Do not turn this into an interest credit or a precise monthly amount until the actual account, interest transaction, cycle dates, and balance history have been verified.

## Required investigation workflow

1. **Authenticate before account-specific disclosure or an account action.** Ask the customer to confirm at least two identity fields from date of birth, email, phone number, and address. Look up the customer using the appropriate regular user-information tool, compare the customer-provided fields to the returned record, obtain the current time, and call `log_verification` only after two fields match. Supply all fields from the verified record exactly as required by that audit tool. Do not read back unconfirmed sensitive fields.
2. **Obtain the missing investigation facts.** Get the Gold savings account ID (or resolve it from the verified customer profile), statement-cycle start and end dates or the posted-interest date, and whether the daily balance changed. A customer-reported approximate balance and payment are not a sufficient basis for a correction.
3. **Unlock and use the account/transaction tools named in policy.** Unlock `get_all_user_accounts_by_user_id_3847` and `get_bank_account_transactions_9173`, then use them to confirm account ownership, that the target is a Gold savings account, all checking accounts, the active cards, and the actual interest-credit transaction. Regular credit-card account lookup may also be used to identify active cards.
4. **Determine the expected APY.** Identify every qualifying checking/savings pairing, choose the highest checking boost only, identify active eligible cards and choose the highest card bonus only, then add independently documented relationship/tier bonuses. Do not count inactive cards, nonqualifying pairings, or duplicate descriptions of the same benefit.
5. **Calculate actual expected interest.** Use daily balances from the account history for the exact cycle whenever available. For a constant-balance estimate only, run `scripts/calculate_daily_interest.py` with the confirmed APY, exact cycle-day count, balance, and an explicitly chosen annual day-count convention. The script defaults to 365 only as an explicit calculation assumption; follow any account-system convention revealed by transaction or account data instead. Compare the rounded expected credit to the actual posted interest.
6. **Do not act if data is incomplete.** Explain the components that can be established, distinguish APY from a monthly dollar payment, and request the missing account/cycle/balance information. Do not submit a report or apply a credit merely because an estimate differs.
7. **Correct a confirmed discrepancy in the mandatory order.** Unlock `apply_savings_account_credit_6831` and `submit_interest_discrepancy_report_7294`. If and only if the verified calculation produces a positive shortfall, first apply the positive difference as `credit_type: "interest_correction"`. Confirm that call succeeded. Then submit the discrepancy report with the verified account ID, user ID, expected APY percentage, actual APY percentage if determinable from the transaction/system data, and the positive dollar difference. Never reverse this order. If actual APY cannot be established, do not invent it for the report; continue investigation or explain the missing evidence.
8. **Respond clearly.** State the verified APY components, the highest-only selection rules, whether an exact payment could be calculated, the correction/report status if actions were completed, and what information is still needed. Do not promise a fixed monthly amount from APY alone: daily compounding, cycle length, balance changes, and rounding affect the credit.

## Calculator

`scripts/calculate_daily_interest.py` performs transparent deterministic daily-compounding arithmetic. It is an aid for a verified calculation, not a substitute for transaction lookup.

Input JSON schema:

```json
{
  "base_apy_percent": "5.5",
  "checking_boosts_percent": ["0.75"],
  "card_bonuses_percent": ["0.15", "0.6"],
  "relationship_bonuses_percent": ["0.025"],
  "tier_bonuses_percent": [],
  "balance": "96000.00",
  "days": 30,
  "day_count_basis": 365,
  "actual_interest": "408.00"
}
```

All bonus arrays are percentage points, not fractional rates. The script selects the highest supplied checking and card values, sums separately supplied relationship/tier values, calculates an effective daily-compounding estimate for a constant balance, and returns JSON including `expected_apy_percent`, `estimated_interest`, and, if provided, `difference_from_actual`. Amounts are decimal strings rounded to cents only for output. Omit `actual_interest` when no verified interest transaction is available.

Runnable executor call:

```text
run_skill_script(relative_path="scripts/calculate_daily_interest.py", input_json={...})
```

Validation before relying on output: ensure the account is Gold savings, each included component is verified and eligible, `days` exactly matches the cycle, `balance` represents the relevant constant balance or is replaced by a daily-balance calculation, and the transaction amount is the actual interest-credit line item. A nonpositive difference is not a basis for an interest-correction credit.
