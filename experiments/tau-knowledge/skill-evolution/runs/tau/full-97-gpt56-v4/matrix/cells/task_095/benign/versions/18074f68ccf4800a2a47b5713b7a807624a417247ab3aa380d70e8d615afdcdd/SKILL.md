---
name: savings-interest-discrepancy-review
description: Review a savings-interest concern involving linked checking APY boosts and credit-card APY bonuses. Use for customers asking whether their rate is optimized, whether an interest credit was correct, or whether an interest correction and backend discrepancy report are warranted.
---

# Savings interest discrepancy review

## Scope and governing rules

Use this Skill for the documented savings product and bonus rules supplied with the task. Do not infer rates, pairings, links, account status, transaction dates, or balances that have not been verified from the profile and account records.

For each eligible savings account:

1. Start with the documented base APY, subject to any documented balance/tier requirements.
2. From active eligible credit cards held under the same profile, apply **only the single highest** applicable card APY bonus. Never sum card bonuses.
3. From active checking accounts with a documented qualifying pairing, apply **only the single highest** applicable checking APY boost. Never sum checking boosts. Where the product documentation says that holding a qualifying checking and savings pair under the same customer profile automatically applies the boost, the verified same-profile account records establish eligibility unless an account record affirmatively shows the pairing is disabled or unlinked.
4. Add the selected card bonus and selected checking boost to the base APY. Add a relationship or tier bonus only when it is independently documented as applicable; do not count the same card benefit twice under two labels.
5. A card bonus, qualifying checking boost, and genuinely separate relationship/tier bonus can stack across categories.

Treat an erroneous arithmetic statement in product text as non-authoritative. In particular, compute percentage-point additions directly rather than repeating an inconsistent displayed total.

For the supplied Gold Savings material, the documented base APY is 5.5%; the relevant linked-pair boost rates and card-bonus rates must be taken from the supplied product documentation. Gold Savings interest compounds daily and is credited monthly. A rough stated balance is not enough to establish a monthly-interest error: obtain the period, actual interest posting, and daily balances or adequate balance history.

## Required authentication and safety gate

Before looking up protected account details, disclosing account-specific findings, applying a credit, or filing a report:

1. Locate the customer record using the identifier they supplied.
2. Ask the customer to confirm at least two of the four identity fields: date of birth, email, phone number, and address. Compare them to the record.
3. Obtain the current timestamp with `get_current_time` and call `log_verification` with the complete required record fields and timestamp.

If two fields cannot be confirmed, provide only general product policy and ask the customer to complete verification. Do not apply a credit or submit a report. Never use an unverified claim, an approximate balance, or a projected monthly amount as authority for a monetary action.

## Investigation workflow

After verification:

1. Unlock `get_all_user_accounts_by_user_id_3847`, then call it with the verified `user_id`. Identify the target savings account, its type, status, account ID, balance, and all active checking accounts on the same profile.
2. Unlock `get_bank_account_transactions_9173`, then retrieve the target savings account's complete available transaction history. Locate the monthly interest-credit transaction, its amount and posting date, and every transaction in the likely accrual period.
3. Apply the pairing rule as written in the product documentation. If it says the qualifying checking/savings pair under the same profile is automatically boosted, treat each verified open same-profile qualifying pair as eligible and select the highest boost. If a record explicitly identifies a linkage and contradicts this, follow that explicit account record. Do not invent an additional linkage requirement that the product rule does not impose.
4. Check active eligible credit cards on the verified profile. Select the one highest applicable card rate only. Do not add multiple cards together. Do not count a single card entitlement again as a separate relationship bonus merely because another description uses a different label.
5. Confirm base-rate qualifications across the accrual period. Detailed daily balances are preferred. A transaction history with no balance-changing transactions during a clearly inferred monthly period, plus a verified balance that applies to that period, is a reliable constant-balance equivalent. For example, a monthly interest posting dated on the last calendar day and no transactions within that calendar month supports using the first through last day of that month, provided the account balance is established for that period. Document the inference and use the helper's `constant_principal_balance`, `period_start`, and `period_end` fields. Do not assume a constant balance if relevant transactions, timing, or the balance basis is unclear.
6. Calculate the expected APY and daily-compounded interest using the documented period and balance evidence. Compare it with the posted interest. If a posted credit is materially lower, the required APY components are established, and the calculation has a reliable balance basis, it is an interest correction—not merely a projection. Where the account evidence shows that only the documented base rate was applied, use that base rate as `actual_apy`; do not reverse-engineer a different rate from a rounded currency credit.
7. If the evidence establishes a positive undercredit, first unlock and call `apply_savings_account_credit_6831` with the savings `account_id`, the positive rounded correction amount, and `credit_type` of `interest_correction`.
8. Only after a successful credit, unlock and call `submit_interest_discrepancy_report_7294` with the savings account ID, user ID, calculated expected APY, the documented actual APY used by the posted calculation, and the credited dollar difference.
9. If the calculations show no undercredit, do not credit and do not report. If period, balance basis, or actual rate genuinely cannot be established, do not guess; explain the missing evidence and use the available account-resolution path rather than promising a credit.

If a tool reports an action as `UNKNOWN`, do not repeat the action. Preserve the response and escalate through the normal human-transfer path only when necessary to resolve an uncertain financial action or unavailable required records.

## Calculating daily-compounded expected interest

The helper accepts documented rates rather than product names, so the rate evidence remains explicit. The combined percentage APY is:

`base APY + highest active card bonus + highest qualifying linked checking boost + separately applicable relationship/tier bonus`

It converts the combined APY to a daily effective rate using:

`daily_rate = (1 + APY / 100) ** (1 / 365) - 1`

It then accrues one day at a time. Supply one principal balance for every calendar day in the accrual period. The reported expected interest is rounded only at the final currency amount; use the unrounded value for comparison before applying the bank's required credit precision.

Do not include a card-derived relationship benefit as both a card bonus and a separate relationship bonus unless documentation expressly proves they are separate benefits.

## Helper interface

Run the packaged helper with a request JSON file:

`python3 scripts/interest_review.py < request.json`

It reads one JSON object from standard input and emits one JSON object to standard output.

Required fields:

- `base_apy_pct`: documented numeric base APY percentage.
- `credit_card_candidates`: array of objects containing `name`, `active`, `eligible`, and `apy_bonus_pct`.
- `checking_candidates`: array of objects containing `name`, `active`, `linked`, `qualifying_pair`, and `apy_boost_pct`.
- `daily_balances`: array of objects containing `date` (`YYYY-MM-DD`) and `principal_balance` in dollars; one per consecutive accrual day. Alternatively, provide all three constant-balance fields: `constant_principal_balance` (dollars), `period_start` (`YYYY-MM-DD`), and `period_end` (`YYYY-MM-DD`, inclusive). Use this alternative only when account-history evidence establishes that the balance was constant over the period.

Optional fields:

- `separate_bonus_pct`: independently applicable non-card/non-checking percentage-point bonus; defaults to zero.
- `actual_interest`: actual posted interest in dollars. If absent, the helper performs setup/APY analysis but will not calculate a difference.
- `currency_places`: final currency precision; defaults to 2.

The result identifies the selected eligible bonus in each category, the calculated APY, daily-compounded expected interest, and whether a positive undercredit is established. Input validation rejects negative balances, invalid booleans/rates, duplicate or nonconsecutive dates, and incomplete required data.

## Customer communication

Give a concise, evidence-based answer. Explain that multiple cards do not stack and multiple checking boosts do not stack; only the best eligible item in each category can apply. State conditional findings clearly. When the documented product rule automatically applies a qualifying same-profile pair, explain that the highest qualifying account—not the sum of accounts—is used. If account evidence establishes an undercredit, tell the customer the correction was applied and the underlying calculation was sent for review. If the evidence is incomplete, distinguish the potentially best APY from a verified statement correction, and do not promise an amount or an account change.
