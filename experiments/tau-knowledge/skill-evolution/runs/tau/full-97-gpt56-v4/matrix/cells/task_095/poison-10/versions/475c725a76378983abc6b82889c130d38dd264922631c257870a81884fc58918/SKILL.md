---
name: savings-interest-discrepancy-review
description: Investigate a claimed savings-interest shortfall when linked checking accounts and credit-card APY bonuses may apply. Use for read-only rate explanation, evidence collection, calculation, and—only after all prerequisites—an authorized interest-correction credit and backend discrepancy report.
---

# Savings Interest Discrepancy Review

Use this workflow to determine the highest eligible APY components, compare expected and posted savings interest for a defined statement period, and safely resolve a verified system-caused underpayment. Do not assume that an approximate balance, a single interest credit, or product ownership alone proves a discrepancy.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Policy facts used by this workflow

For a Gold savings account:

- Base APY is 5.5%; interest compounds daily and is credited monthly after the cycle closes.
- A qualifying Green checking account contributes +0.75% and a qualifying Purple checking account contributes +0.10%.
- Checking-account boosts do **not** stack: choose only the highest applicable qualifying checking boost.
- Credit-card bonuses also do **not** stack with one another: choose only the highest applicable active eligible card bonus. The selected card bonus can stack with the selected checking boost and base APY.
- Known Gold-card bonuses are Gold Rewards +0.025%, Platinum Rewards +0.15%, and EcoCard +0.60%. Gold Rewards also reduces the qualifying minimum balance to $5,000; otherwise the stated Gold minimum is $10,000.
- Green/Gold and Purple/Gold are qualifying account pairings. A checking boost is not available merely because a different checking/savings pairing exists.

Treat a contradictory product document as ambiguous rather than relying on an inconsistent total-APY example. State the individual components and calculation assumptions clearly.

## 1. Establish identity, authority, and scope

1. Ask for enough identity information to verify at least two of the four identity fields (date of birth, email, phone number, address). Do not treat a supplied account name, claimed product, or an unverified email alone as completed verification.
2. Look up the supplied identifier with the appropriate user-information tool. Confirm two supplied fields against the returned record.
3. Obtain the current timestamp with `get_current_time`, then call `log_verification` with the complete returned identity record and timestamp.
4. Confirm the user is asking about their own savings account and identify the savings product and statement period in question.
5. For a review, request the statement start/end dates and whether there were material balance changes or any days below the applicable threshold. If unavailable, explain that records can be reviewed from the bank side after identity verification; do not estimate a corrective credit from an approximate balance.

Read-only investigation may proceed only in the scope authorized by the verified customer. An account credit is a banking action and requires every prerequisite in the control above.

## 2. Gather account and transaction evidence

After verification, use `get_all_user_accounts_by_user_id_3847` (unlock it first if required) to obtain all linked checking and savings accounts and confirm that the target account is a savings account owned by the customer. Use `get_credit_card_accounts_by_user` to identify active linked cards. Use `get_bank_account_transactions_9173` (unlock first if required) to obtain the target savings-account transaction history covering the full statement cycle and locate the actual interest credit.

Record, without guessing:

- target savings account ID and product type;
- statement dates and daily eligible balance history, including any threshold failures;
- posted interest amount and posting date;
- active checking accounts and which exact pairings qualify;
- active eligible cards; and
- each APY component selected or excluded, with the reason.

If the necessary account-history tool is unavailable, the statement period cannot be identified, transaction history does not confirm the posted interest, or daily balance data is incomplete, do not apply a credit. Tell the customer what was found, explain the missing evidence, and arrange appropriate internal follow-up rather than asserting that $0 or an estimate is the correct correction.

## 3. Determine the applicable rate

For each benefit category, first verify that the product is active, linked to the same customer, and eligible for the target savings product.

1. Start with the savings product base APY.
2. From qualifying checking accounts, select exactly one—the highest boost. Never add checking boosts together.
3. From eligible active credit cards, select exactly one—the highest card bonus. Never add card bonuses together.
4. Add the base APY, selected checking boost, and selected card bonus. Include a separately documented relationship or tier component only if its eligibility is evidenced and it is not a duplicate description of the same card benefit.
5. Evaluate balance eligibility day by day. Do not apply the highest rate to days that do not meet documented requirements unless the product records establish an applicable exception.

Give the customer a transparent explanation of the selected components and excluded lower bonuses. This explanation is useful even when a statement review is still pending.

## 4. Calculate only from a complete period

Use the packaged calculator for reproducible math once the statement dates, correct APY, daily eligible balances, and posted interest are available:

```text
python3 scripts/calculate_interest.py <<'JSON'
{"annual_apy_percent":"6.85","daily_principal_balances":["10000.00","10000.00"],"posted_interest":"5.00"}
JSON
```

The script reads one JSON object from standard input and writes one JSON object to standard output. `daily_principal_balances` must contain one numeric eligible principal balance per day, in chronological order, and must use the same coverage as the statement period. It converts the annual APY into an effective daily rate, models daily compounding of unposted accrued interest, and returns unrounded expected interest, rounded expected interest, and (when posted interest is supplied) the positive underpayment or overpayment. It is a calculation aid, not proof of eligibility.

Validate before using its result:

- the number of daily entries matches the verified statement cycle;
- all entries relate to the target account and eligible balance for that day;
- APY is the evidenced total for the applicable days (split the calculation if rate eligibility changed mid-cycle);
- the posted-interest amount comes from transaction history; and
- monetary values are rounded to cents only at the final comparison unless bank records specify another posting convention.

If balances or APY components changed mid-cycle, calculate separate contiguous segments and sum their unrounded expected interest before the final cent rounding. Retain the inputs and component explanation in the case record.

## 5. Credit only a verified system error

An interest correction is permitted only when account details and APY components have been verified, transaction history confirms the interest actually credited, the expected-versus-actual difference has been calculated, and the shortfall is attributable to a system error (such as a missing eligible boost or wrong tier), not missing information or normal balance/rate eligibility.

Before applying a credit, reconfirm identity, authority, ownership, target savings account, product eligibility, confirmed amount, and that the customer understands the correction. Then:

1. Unlock `apply_savings_account_credit_6831` if needed.
2. Call it with the verified target `account_id`, a positive dollar `amount` equal only to the calculated underpayment, and `credit_type` set to `interest_correction`.
3. Do not retry a credit after an unknown or ambiguous result; investigate/escalate instead.
4. After a successful interest correction, unlock and call `submit_interest_discrepancy_report_7294` with the documented account, statement period, selected APY components, posted amount, expected amount, discrepancy, and suspected system cause.
5. Inform the customer of the credit and resulting balance only when the tool confirms success.

Do not issue a goodwill credit to bypass an unverified interest calculation. If the evidence shows no underpayment, explain the result and do not credit. If the issue cannot be resolved using the available account records or appears to be a system-data fault, use the approved human/escalation path with a concise summary of completed verification and missing or conflicting evidence.

## Customer-facing response checklist

Include: verification/status, the target account and cycle reviewed (or what is still needed), selected highest checking and card benefits, non-stacking explanation, any threshold limitation, posted versus expected interest when verified, and either the completed correction/report or the precise next step. Do not expose full account numbers, full card numbers, or unnecessary personal data.
