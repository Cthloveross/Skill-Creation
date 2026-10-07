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
3. From active checking accounts that are actually linked to the savings account and have a documented qualifying pairing, apply **only the single highest** applicable checking APY boost. Never sum checking boosts.
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

1. Unlock `get_all_user_accounts_by_user_id_3847`, then call it with the verified `user_id`. Identify the target savings account, its type, status, account ID, and all checking accounts on the same profile. Account ownership alone does not prove that a checking account is linked.
2. Unlock `get_bank_account_transactions_9173`, then retrieve the target savings account's transactions. Locate the monthly interest-credit transaction and determine its posting date, statement/accrual period if available, and actual credited amount.
3. Establish the actual linked checking accounts and account-level displayed APY from account details or available records. If the records do not expose linkage, do not claim that an account is linked; explain that the linkage cannot yet be confirmed.
4. Check each documented checking/savings pairing and rate. Select the one highest eligible boost among **linked** accounts only.
5. Check active eligible credit cards on the verified profile. Select the one highest applicable card rate only. Do not add multiple cards together.
6. Confirm all base-rate qualifications across the relevant accrual period, including any balance or tier condition. Obtain daily balances or a reliable account-history equivalent. If those data are missing, give a conditional expected APY but do not calculate or correct a dollar discrepancy.
7. Calculate the expected APY and, when the full period's daily balance data are available, calculate expected daily-compounded interest. Compare it against the actual interest credit. Use `scripts/interest_review.py` for transparent selection and math.
8. If the evidence establishes a positive undercredit, first unlock and call `apply_savings_account_credit_6831` with the savings `account_id`, the positive rounded correction amount, and `credit_type` of `interest_correction`.
9. Only after a successful credit, unlock and call `submit_interest_discrepancy_report_7294` with the savings account ID, user ID, expected APY, actual APY when supportable from the records, and the credited dollar difference.
10. If the calculations show no undercredit, do not credit and do not report. If the actual APY, accrual period, or balance history cannot be established, do not guess; explain what is missing and how it prevents a correction.

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
- `daily_balances`: array of objects containing `date` (`YYYY-MM-DD`) and `principal_balance` in dollars; one per consecutive accrual day.

Optional fields:

- `separate_bonus_pct`: independently applicable non-card/non-checking percentage-point bonus; defaults to zero.
- `actual_interest`: actual posted interest in dollars. If absent, the helper performs setup/APY analysis but will not calculate a difference.
- `currency_places`: final currency precision; defaults to 2.

The result identifies the selected eligible bonus in each category, the calculated APY, daily-compounded expected interest, and whether a positive undercredit is established. Input validation rejects negative balances, invalid booleans/rates, duplicate or nonconsecutive dates, and incomplete required data.

## Customer communication

Give a concise, evidence-based answer. Explain that multiple cards do not stack and multiple checking boosts do not stack; only the best eligible item in each category can apply. State conditional findings clearly: holding accounts on the same profile is not confirmation that they are linked. If no verified daily data or transaction period is available, distinguish the potentially best APY from a verified statement correction, and do not promise an amount or an account change.
