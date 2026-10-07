---
name: savings-interest-discrepancy
version: 1.0.0
description: Investigate a verified customer's alleged savings-interest underpayment, determine applicable APY components and a supportable correction from account and transaction data, then apply an interest-correction credit before filing the required backend discrepancy report.
---

# Savings Interest Discrepancy Investigation

Use this Skill when a customer disputes savings interest, alleges a missing APY boost/bonus, or asks to correct an interest calculation. It supports investigation; do not promise a credit or infer a correction from a rough balance and a monthly-interest amount alone.

## Mandatory control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this workflow, satisfy those prerequisites as follows:

1. Identify a possible profile only from information volunteered by the customer, then ask the customer to confirm **two of four** profile fields: date of birth, email address, phone number, or street address. Do not reveal unconfirmed profile fields.
2. Retrieve the profile using the appropriate user lookup and compare both customer-provided fields with the retrieved record. Obtain the current timestamp and call `log_verification` with every required profile field and that timestamp only after both fields match. Treat a direct, verified account holder as the authority for this investigation.
3. Only after verification, retrieve all accounts and verify the target belongs to the verified user, is active, and is a savings account. Confirm its product type before using product APY rules.
4. Check all active checking accounts and all active credit cards owned by that same verified user. Verify the specific linked-checking pairing is eligible; do not assume that a checking product creates a boost for every savings product.
5. Retrieve the target savings account's transaction history. Locate the relevant monthly interest-credit transaction and obtain the statement period and daily-balance history (or an authoritative equivalent) required to calculate interest. Confirm the account and transaction details with the customer before an external-facing conclusion.
6. Do not apply a credit or submit a report unless a positive, cent-quantized discrepancy is demonstrated from verified account and transaction data. A report is only submitted after a successful correction credit.

## Investigation procedure

1. Acknowledge the request and explain that the account can be located after identity verification. If the customer lacks an account ID, that is not a blocker after verification; locate their accounts from the verified profile instead.
2. Unlock the needed documented internal tools with `unlock_discoverable_agent_tool` before calling them:
   - `get_all_user_accounts_by_user_id_3847`
   - `get_bank_account_transactions_9173`
   - `apply_savings_account_credit_6831`
   - `submit_interest_discrepancy_report_7294`
   Use `call_discoverable_agent_tool` with the exact documented tool name and JSON arguments.
3. From the accounts returned, identify the customer's Gold (or other relevant) savings account and every active checking and credit-card account. If zero or multiple plausible savings accounts remain, ask the customer to identify the target using a non-sensitive account descriptor; do not credit an ambiguous account.
4. Determine the expected annual APY from documented components. For a Gold savings account, start with the documented 5.5% base APY. Add the single highest eligible linked-checking boost, the single highest active eligible credit-card bonus, and separately documented relationship or tier bonuses when their eligibility is established.
   - Checking boosts never stack with one another; choose only the highest applicable boost.
   - Credit-card bonuses never stack with one another; choose only the highest applicable bonus.
   - The selected checking boost and selected card bonus can stack with each other and with a separately applicable relationship/tier bonus.
   - Do not add a card's relationship benefit merely because the card exists unless the account documentation makes it a distinct, applicable component. Resolve contradictory examples by using explicit component statements and record the components used.
5. Establish the actual APY and actual interest from authoritative account/transaction data, not the customer's estimate. When daily balances fluctuate, calculate expected interest using daily compounding for each day in the statement period. Do not use `balance × APY ÷ 12` as a correction calculation. If daily balances, statement dates, or the interest credit cannot be retrieved, explain that a correction cannot yet be calculated and request/escalate for the missing statement data; take no monetary action.
6. Use `scripts/calculate_interest.py` to produce a deterministic expected-interest calculation and validate the inputs and result. Supply the actual interest transaction amount and actual APY when known. Retain its component breakdown and calculation assumptions for the case notes.
7. If `credit_amount` is greater than zero, apply it using `apply_savings_account_credit_6831` with the verified savings `account_id`, the positive cent amount, and `credit_type: "interest_correction"`. Never send a negative amount or a goodwill/fee-refund type for this discrepancy. If the credit call fails or is indeterminate, do not retry blindly and do not submit the report.
8. After a successful credit only, submit `submit_interest_discrepancy_report_7294` with the verified savings `account_id`, verified `user_id`, expected and actual APY percentages, and the same positive dollar difference. If the report fails after the credit succeeds, accurately tell the customer that the correction was applied and route the reporting failure for follow-up; do not issue a duplicate credit.
9. Inform the customer of the verified APY components, the corrected amount, and new balance only if returned by the credit tool. State that the discrepancy was reported after the credit. If there is no discrepancy, explain the documented calculation without making an adjustment.

## Calculator

`scripts/calculate_interest.py` accepts one JSON object on stdin and emits one JSON object on stdout. It performs no bank access and never applies a credit.

Input schema:

```json
{
  "base_apy": 5.5,
  "checking_boosts": [0.75],
  "card_bonuses": [0.6, 0.15],
  "other_bonuses": [0.025],
  "daily_balances": [{"balance": "96000.00", "days": 30}],
  "actual_interest": "408.00",
  "actual_apy": 5.5,
  "days_in_year": 365
}
```

All APYs are percentages, not fractions. `daily_balances` must cover the exact statement period as nonnegative balances and positive whole-day counts. `other_bonuses` contains only independently verified, additive bonuses. `actual_apy` is optional when unavailable; it is required before filing an interest discrepancy report.

The output includes `expected_apy`, selected highest checking/card components, compound `expected_interest`, cent-rounded `credit_amount`, and a `decision`. `decision: "credit_eligible"` means the positive amount may proceed only after all bank-tool verification described above. `decision: "no_credit"` means no credit should be applied. Invalid or incomplete calculation input yields `decision: "insufficient_data"` and errors.

Example runtime call (with values obtained during the current investigation, not copied from this example):

```sh
python3 scripts/calculate_interest.py <<'JSON'
{"base_apy":5.5,"checking_boosts":[0.75],"card_bonuses":[0.6],"other_bonuses":[],"daily_balances":[{"balance":"10000.00","days":30}],"actual_interest":"0.00","actual_apy":5.5}
JSON
```

Validate that the output's `total_days` equals the verified statement-period day count, its selected boosts agree with eligibility findings, `expected_apy` is the documented component sum, and `credit_amount` equals `max(expected_interest - actual_interest, 0)` rounded to cents. Do not treat calculator output as proof of account ownership, eligibility, or actual transaction history.

## Failure handling

- If identity cannot be verified, do not disclose accounts, balances, transactions, APYs specific to the profile, or take action.
- If no eligible boost exists, use zero for that component; do not honor a customer-stated rate that differs from the product documentation.
- If an account is not savings, is not owned by the customer, or lacks a confirmed target, do not proceed.
- If a calculation would produce zero or a negative difference, make no credit and no discrepancy report.
- If a required internal lookup or monetary action is unavailable, state the limitation, preserve verified facts, and use the normal support/escalation path rather than fabricating data or retrying an uncertain credit.
