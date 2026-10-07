---
name: investigate-silver-savings-interest-discrepancy
description: Investigate a verified customer's concern that a Silver savings account monthly interest credit is too low. Use when account and transaction tools are available to verify ownership, reconstruct the relevant cycle, calculate daily-compounded interest using documented Silver rates and eligible bonuses, and, only for a confirmed undercredit, apply an interest correction before filing the required backend discrepancy report.
---

# Investigate a Silver Account interest discrepancy

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Do not apply a credit merely because the customer believes interest is low. A correction is authorized only after an incorrect posted interest payment and the dollar shortfall have been confirmed.

## Tool access and verification

1. Establish identity using at least two matching profile fields (date of birth, email, phone number, or address). Retrieve the profile with an appropriate user-information tool if needed.
2. Obtain the current time using `get_current_time`, then call `log_verification` after successful two-field verification. Supply the complete profile fields returned by the profile lookup and the returned current timestamp.
3. Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified `user_id`. Confirm that the selected account is owned by this customer, is active, and is a savings account whose type/class identifies it as Silver. Do not use an account identifier supplied by a customer without this ownership check.
4. Unlock and call `get_bank_account_transactions_9173` for that account. Find the relevant **posted** `interest_credit` transaction and record its date, positive amount, and monthly cycle being reviewed. Pending entries do not establish an actual paid amount.
5. Unlock and call `get_credit_card_accounts_by_user` to identify active, profile-linked cards. Account lookup also identifies active checking accounts. Retain only products that are active and under the verified customer's profile.

If the cycle, daily balances, or posted interest credit cannot be determined from the available records, explain the missing evidence and provide the customer the transaction-history options (online/mobile banking or assistance from support). Do not estimate a credit or submit a discrepancy report.

## Silver APY rules

For every calendar day in the reviewed interest cycle:

- The base Silver APY is **2.5%** for a balance below $10,000 and **4.0%** for a balance of $10,000 or more.
- Qualifying linked checking accounts for Silver are Bluest (+0.45%), Green (+0.25%), and Gold Years (+0.60%). If several qualify, use **only the highest** boost; checking boosts never stack.
- Use only the largest applicable credit-card bonus; card bonuses never stack. Supported Silver bonuses are: Bronze Rewards +0.0%, Silver Rewards +0.1%, Gold Rewards +0.5%, EcoCard +2.2%, Green Rewards +0.0%, Crypto-Cash Back +0.5%, Platinum Rewards +0.2%, and Diamond Elite +0.25%.
- A Silver Account and Platinum Rewards Card linked in the same profile receive the documented +0.025% relationship bonus. Do not assume an undocumented relationship bonus is eligible.
- The selected checking boost, selected card bonus, and documented relationship bonus stack with the daily base tier.

Interest accrues on the daily balance with daily compounding and is credited monthly. Apply the tier separately to each day; do not apply one higher-tier rate to an entire cycle when the balance crossed $10,000.

## Calculation helper

Use `scripts/calculate_silver_interest.py` after obtaining a complete, date-ordered daily balance series. It takes JSON on stdin and emits JSON on stdout; it does not access banking systems or take banking actions.

Input schema:

```json
{
  "daily_balances": [{"date": "YYYY-MM-DD", "balance": 0}],
  "checking_accounts": ["active checking product name"],
  "credit_cards": ["active linked card product name"],
  "platinum_relationship_eligible": false,
  "actual_interest": 0,
  "actual_apy": 0
}
```

`daily_balances` is required, must be consecutive dates, and each balance must be nonnegative. Product lists are optional. `actual_interest` is the selected posted interest-credit amount; omit it until identified. `actual_apy` is optional and must be supported by account/system evidence, not guessed from a customer's impression.

A runnable invocation using a runtime-supplied JSON file is:

```sh
python3 scripts/calculate_silver_interest.py < cycle-input.json
```

The helper derives a daily periodic rate as `(1 + APY/100)^(1/365) - 1`, compounds the accrued interest daily, rounds only the final cycle interest to cents, and emits the selected components, per-day rates/accruals, expected interest, and—when an actual interest amount is supplied—the cent-rounded difference. Validate before acting that:

- the output's dates and number of days match the statement cycle;
- every daily balance was reconstructed from account records rather than inferred from the current balance alone;
- selected product names and their active/profile-linked status match the tool results;
- `actual_interest` matches the posted `interest_credit`; and
- `credit_recommended` is true and `credit_amount` is greater than zero.

A zero or negative difference means no undercredit was established; do not apply a credit or report an interest discrepancy on that basis.

## Corrective action sequence

For a confirmed positive discrepancy only:

1. Reconfirm the verified customer, account ownership, Silver eligibility, relevant transaction, calculation, and the positive credit amount. The `amount` must be a positive dollar amount.
2. Unlock `apply_savings_account_credit_6831` and call it with the confirmed savings `account_id`, the helper's `credit_amount`, and `credit_type` set exactly to `interest_correction`.
3. Only after the credit succeeds, unlock `submit_interest_discrepancy_report_7294` and submit the `account_id`, verified `user_id`, evidence-supported expected and actual APYs, and the confirmed dollar `amount_difference`.
4. If daily expected APYs vary because the balance changes tiers, preserve the helper's daily calculation. Do not invent a single APY for the report. Obtain the rate detail needed to represent the discrepancy correctly, or escalate the backend-report formatting issue through normal internal support after the customer correction; the credit still must precede any submitted report.
5. Tell the customer the reviewed period, the confirmed correction amount, that it was credited, and that a backend investigation was submitted. Provide the new balance only when returned by an authoritative banking result; do not calculate or claim one from incomplete transaction history.

Never reverse this order: an interest discrepancy report follows a successful interest correction, not the other way around.
