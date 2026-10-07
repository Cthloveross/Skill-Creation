---
name: gold-savings-interest-discrepancy
version: 1.0.0
description: Investigate a Gold Savings interest-credit concern, determine the additive APY components while enforcing highest-only checking and credit-card selections, and, after verification and exact reconciliation, correct and report a confirmed discrepancy.
---

# Gold Savings Interest Discrepancy Investigation

Use this Skill when a customer questions an interest credit on a Gold Savings Account and may hold qualifying checking accounts and/or credit cards. It is designed for a banking-agent runtime with the ordinary account, transaction, verification, credit, and discrepancy-report tools described below.

## Guardrails and prerequisites

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For this workflow:

1. Obtain and confirm **two of four** identity fields (date of birth, email, phone number, address) from the customer; do not treat a name alone as verification.
2. Look up the customer only after collecting a usable identifier. Compare the two customer-provided fields with the customer record.
3. Obtain the current timestamp with `get_current_time`, then call `log_verification` with the complete record and timestamp.
4. Confirm the Gold Savings account is active, belongs to the verified customer, and is the account under discussion before accessing its transactions or making a correction.
5. Do not disclose full sensitive identity fields unnecessarily. Do not make a credit or file a report if verification, ownership, eligibility, or the calculation is not established.

If the customer cannot be verified, explain that account-specific investigation or changes require verification and stop. If a system tool is unavailable or returns ambiguous data, do not guess; explain the limitation or transfer using the appropriate normal escalation path.

## Rate rules for Gold Savings

Determine rates from active accounts under the same verified customer profile. The APY is expressed in percentage points, not decimal fractions.

| Component | Rule |
|---|---|
| Base Gold Savings APY | `5.5%` |
| Credit-card APY bonus | Consider active eligible cards, but apply **only the single highest** applicable value. Gold values: Bronze Rewards `0.15`, Silver Rewards `0.2`, Gold Rewards `0.025`, Platinum Rewards `0.15`, Diamond Elite `0.3`, EcoCard `0.6`, Green Rewards `0.35`, Crypto-Cash Back `0`. |
| Linked checking boost | Apply **only the single highest** qualifying linked-checking value. Green checking + Gold Savings is `0.75`; Purple checking + Gold Savings is `0.1`. |
| Gold Rewards relationship bonus | If an active Gold Rewards Card is associated with the Gold Savings profile, add `0.025` as the separately documented relationship bonus. It is distinct from the card's `0.025` card-bonus value. |

The selected credit-card bonus, the selected checking boost, and eligible relationship bonuses are additive to the base APY. Never sum multiple cards or multiple checking accounts. Do not infer a boost for an unlisted checking/savings pairing.

Use `scripts/calculate_gold_savings.py` to select the highest bonuses, produce an expected APY, and, where the reconciled balance was constant, calculate daily-compounded expected interest.

## Investigation workflow

1. **Clarify and verify.** Identify the statement period and the account the customer means. Ask for two identity fields if they have not already been confirmed. Complete the verification logging prerequisite above.
2. **Collect account data.** Use `get_all_user_accounts_by_user_id_3847` (unlock it first if the runtime requires unlocking) to identify active Gold Savings and checking accounts. Use `get_credit_card_accounts_by_user` for active cards. Do not rely solely on customer recollection of account types.
3. **Inspect the interest credit.** Use `get_bank_account_transactions_9173` (unlock first if necessary) for the verified savings account. Locate the posted monthly interest credit for the requested closed statement cycle; capture its exact amount, posting date, and cycle dates if provided. Reconcile the account balance and all deposits, withdrawals, or other balance changes during the cycle.
4. **Compute the expected rate.** Pass only active, eligible card/checking types and the base rate to the helper. Record the selected maximum card and checking components and any relationship component. The helper reports all components, which makes non-stacking decisions auditable.
5. **Compute expected interest conservatively.** Gold Savings compounds daily and credits monthly. For a constant end-of-day principal `B` over `D` days, the expected credit is:

   `B × ((1 + expected_apy / 100 / 365) ^ D − 1)`

   Use the helper with `principal` and `days` only when the period has a demonstrably constant eligible balance. If the balance changed, derive the total from each verified end-of-day balance segment using the same daily-compounding method. Never use the customer's approximate balance, a current balance, or a rounded verbal interest amount as a correction basis.
6. **Reconcile and act only when exact.** Compare the rounded-to-cents expected interest with the actual posted interest credit. If no discrepancy exists, tell the customer the selected highest card/checking benefits and the result; do not create a credit or report. If a discrepancy exists, calculate `amount_difference = expected_interest - actual_interest`, rounded to cents, and ensure it is positive before crediting.
7. **Correct before reporting.** Unlock and call `apply_savings_account_credit_6831` first, using the verified savings account and the exact positive discrepancy amount. Confirm the credit tool reports success. Then unlock and call `submit_interest_discrepancy_report_7294` with `account_id`, `user_id`, `expected_apy`, `actual_apy`, and `amount_difference`. `actual_apy` must be calculated from reconciled statement data, not assumed from the customer's estimate. If the report's required actual APY cannot be derived exactly, do not submit a speculative report; escalate with the reconciled evidence.
8. **Close clearly.** Tell the customer which highest card bonus and checking boost applied, the expected APY, actual versus expected interest, and any successfully posted correction. Do not claim a pending backend report or credit succeeded unless its tool returned success.

## Tool discovery and action order

The account/transaction/correction/report tools may be discoverable. Where needed, call `unlock_discoverable_agent_tool` for the exact tool name before `call_discoverable_agent_tool`:

- `get_all_user_accounts_by_user_id_3847`
- `get_bank_account_transactions_9173`
- `apply_savings_account_credit_6831`
- `submit_interest_discrepancy_report_7294`

The normal `get_credit_card_accounts_by_user`, identity lookup, time, and verification-log tools are used directly when exposed. Discovery and calculator output are informational; they do not themselves create a credit or submit a report. Preserve the mandatory order: verified account review → transaction reconciliation → successful credit → report.

## Calculator interface

Run:

```text
python scripts/calculate_gold_savings.py < input.json
```

Input JSON:

```json
{
  "base_apy": 5.5,
  "active_card_types": ["EcoCard", "Gold Rewards Card"],
  "active_checking_types": ["Green Account", "Purple Account"],
  "gold_rewards_relationship_bonus": true,
  "principal": "96000.00",
  "days": 30
}
```

`principal` and `days` are optional and must be omitted unless established from actual statement data. Output JSON contains the selected maximum bonuses, `expected_apy`, component audit details, and, if both optional inputs are present, unrounded and cent-rounded daily-compounded interest. Reject unknown or unsupported account names rather than assigning a rate.

Validate calculator output before use: `expected_apy` must equal base APY plus exactly one maximum card bonus, exactly one maximum checking boost, and the stated relationship component. When interest is output, ensure the principal is nonnegative, the day count is a positive integer, and use only `expected_interest_cents` for a customer correction after independently reconciling the statement cycle.
