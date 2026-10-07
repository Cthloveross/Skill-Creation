---
name: investigate-silver-savings-interest
version: 1.0.0
description: Investigate a reported Rho-Bank Silver Account interest shortfall. Use when a customer believes monthly Silver savings interest is low and the agent must securely verify identity, retrieve accounts and transactions, determine applicable APY components, calculate a supported correction, and (only when proven) credit and report an error.
---

# Investigate Silver Account Interest

## Scope and prerequisites

Use this Skill for an alleged interest-calculation issue on a **Silver savings account**. Do not promise a credit or report a system error until account ownership, the actual interest credit, applicable eligibility, and the amount difference have been verified.

Before accessing or disclosing non-public account activity, verify the customer by confirming two of date of birth, email, phone number, and address against the customer record. Obtain the fields from the customer rather than reading them aloud. After two fields match, obtain the current timestamp and call `log_verification` with all required record fields and the timestamp. A name alone is not verification.

The internal tools needed for this workflow are discoverable. Unlock each tool before its first call:

- `get_all_user_accounts_by_user_id_3847`
- `get_bank_account_transactions_9173`
- `apply_savings_account_credit_6831` (only after a proven eligible discrepancy)
- `submit_interest_discrepancy_report_7294` (only after its correction credit succeeds)

Never repeat a financial operation whose result is unknown. If a credit call returns an error or unclear result, do not retry; inspect account activity or escalate according to normal operations.

## Product rules to apply

For the Silver savings product:

- The base annual rate is **2.5%** below $10,000 and **4.0%** at or above $10,000. Select the tier separately for every day from that day’s balance.
- The higher tier begins at $10,000. The $1,000 minimum concerns the maintenance-fee requirement; it does not replace the documented daily interest tiers.
- Interest accrues on daily balance, compounds daily, and is credited monthly. The cycle interest is the sum of daily accruals.
- A qualifying linked Green checking account adds **0.25 percentage points** to Silver APY. Green + Silver is a qualifying pair only when the accounts are linked under the same customer profile/ownership and tax ID. Do not infer linkage merely because both accounts exist.
- A documented eligible relationship bonus adds **0.025 percentage points**.
- If active linked credit cards have Silver APY bonuses, use only the single highest applicable card bonus; card bonuses never add together. A card bonus may stack with a linked-checking boost and relationship bonus.
- Actual Silver card bonuses must come from the applicable product documentation. Do not invent a card rate. If card data or linkage/eligibility cannot be established, exclude that unproven component and explain what must be confirmed.

The expected annual APY for a particular day is the applicable base tier plus every proven non-card bonus and the highest proven card bonus. All components are percentage points.

## Workflow

1. **Clarify and verify identity.** Confirm the product, the approximate affected cycle if known, and whether the customer says their checking and savings are linked. Ask for two identity fields if not already verified. Resolve the user record, compare supplied values, log verification, and use only the verified `user_id`.
2. **Retrieve accounts.** Unlock/call `get_all_user_accounts_by_user_id_3847` with the verified user ID. Identify an open Silver savings account. Also identify an open Green checking account and any other relevant products. If no qualifying Silver account is found, explain that the requested investigation cannot proceed on that profile.
3. **Retrieve interest evidence.** Unlock/call `get_bank_account_transactions_9173` for the Silver account. Transactions are reverse chronological. Locate posted `interest_credit` entries, their dates, amounts, and any relevant fees or correction credits. Select the customer’s reported cycle, or the most recent posted interest credit if no cycle is known, and state which cycle was reviewed.
4. **Establish APY components.** Verify, rather than assume, same-profile linkage and eligibility for Green + Silver. Check applicable card information and card policy only when it is available and relevant. Determine whether the relationship bonus is documented as eligible. Record every included and excluded component with its reason.
5. **Obtain daily balances.** A transaction list alone may not show end-of-day balances, statement boundaries, holds, or the opening balance. Use available supported records to reconstruct daily balances only if they are complete. Otherwise explain that an exact recalculation requires a statement or complete daily balance history and direct the customer to recent transactions in mobile/online banking or to support for complete history. Do not estimate a correction from an approximate balance.
6. **Calculate and compare.** Run `scripts/calculate_silver_interest.py` with complete daily balances and the proven components. Provide the APY used by each day/tier, expected cycle interest, posted interest, and unrounded difference. Use the institution’s documented/operational daily-rate convention if available; pass it explicitly to the script. Round only the final customer-facing credit amount to cents. A small difference caused solely by disclosed rounding should not be treated as a system error.
7. **Correct only a proven error.** If expected interest materially exceeds the posted interest due to a documented issue (missing qualifying boost, wrong tier, missing relationship bonus, or another established calculation error), unlock/call `apply_savings_account_credit_6831` first with the Silver `account_id`, a positive cent-rounded amount, and `credit_type: "interest_correction"`. Confirm success before proceeding. Then unlock/call `submit_interest_discrepancy_report_7294` with the savings account ID, user ID, expected APY percentage applicable to the discrepancy, actual APY percentage applied, and the dollar amount difference. The report is submitted **after** the correction credit.
8. **Close clearly.** Tell the customer what cycle and posted credit were reviewed, the determined APY components, whether a correction was applied, and the next action. If no discrepancy can be proven, explain the missing evidence and how to find the interest credit and relevant balances. Do not disclose account information before verification.

## Unsupported or incomplete cases

- Do not apply a goodwill credit merely because interest feels low; interest correction authority requires a verified calculation error.
- Do not submit an interest discrepancy report without first successfully applying the correction credit.
- If the account data, linkage status, daily balances, statement cycle, or actual credit cannot be confirmed, do not fabricate an expected amount or APY. Offer the customer the specific information to obtain: interest-credit date/amount, statement period, daily/end-of-day balances, and linked-account status.
- If the customer requests a human after an otherwise unavailable investigation, transfer with the applicable human-transfer reason and summarize the verified facts and missing evidence.

## Calculator

`scripts/calculate_silver_interest.py` reads one JSON object from standard input and emits one JSON object to standard output. It performs no account access and makes no banking action.

Input schema:

```json
{
  "daily_balances": [{"date": "YYYY-MM-DD", "balance": 10000.00}],
  "linked_checking_bonus_pct": 0.25,
  "relationship_bonus_pct": 0.025,
  "card_bonus_pcts": [0.2],
  "daily_rate_method": "apy_divided_by_365"
}
```

`daily_balances` must contain one nonnegative balance for every calendar day of the chosen interest cycle, in chronological order with no duplicates. Omit an unproven bonus or pass zero. The script selects the maximum nonnegative card bonus. `daily_rate_method` is either `apy_divided_by_365` (nominal annual percentage divided by 365) or `effective_apy` (the daily rate whose 365-day compounding produces the APY). Use the bank’s operational convention when known; do not choose a method merely to create a discrepancy.

Output includes daily detail, expected interest without final rounding, a cent-rounded expected amount, component values, and validation errors. Reject output with `ok: false`; resolve the input evidence before deciding on a correction.

Example runtime call (with real case data substituted):

```text
python3 scripts/calculate_silver_interest.py <<'JSON'
{"daily_balances":[{"date":"YYYY-MM-DD","balance":0}],"linked_checking_bonus_pct":0,"relationship_bonus_pct":0,"card_bonus_pcts":[],"daily_rate_method":"apy_divided_by_365"}
JSON
```
