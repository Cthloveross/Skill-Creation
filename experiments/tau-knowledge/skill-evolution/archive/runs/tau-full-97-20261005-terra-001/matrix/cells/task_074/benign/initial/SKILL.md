---
name: review-atm-fees-and-credit-corrections
description: Review a customer's posted November (or other calendar-month) ATM charges across checking accounts, compare them with Purple, Light Blue, Dark Green, and Evergreen ATM rules, identify only documented fee mischarges or missing qualifying Purple ATM-operator-fee rebates, and prepare a single compliant checking-account credit per account when justified.
---

# Review ATM fees and apply justified corrections

Use this Skill when a customer asks for an investigation of ATM fees and the agent must inspect account and transaction records before deciding whether a correction is warranted. It supports Purple, Light Blue, Dark Green, and Evergreen checking-account rules documented in `references/atm_fee_rules.md`.

## Guardrails

- Treat the customer's claim as a request for review, not evidence that a fee is wrong.
- Verify identity and account ownership before an account-specific review that may lead to a credit. Confirm at least two of date of birth, email, phone number, and address against the customer record; then obtain the current timestamp and call `log_verification` with all required fields. Do not count information merely returned by a lookup as customer confirmation.
- Retrieve accounts rather than relying on the customer's list. Only checking accounts may receive a credit.
- Retrieve the full transaction history for every relevant checking account. Include activity needed to connect fee posting dates with their corresponding withdrawal dates; ATM fees can post on a different date.
- Do not treat an ATM-owner/operator surcharge as a bank ATM fee. It is separate. A correction is permitted only for a documented bank fee mischarge or a missing qualifying rebate.
- Do not correct pending transactions, estimates, unidentified fee lines, unsupported account classes, or an ATM transaction whose domestic/foreign or network facts are needed but cannot be established.
- Do not credit an account until the history confirms the correction was not already applied. Credits must be exact positive dollar amounts, never rounded or estimated.
- The credit tool may be called only once for a checking account during this interaction. Combine every validated correction for that account into one call. A failed call is still an attempted call; do not retry it.

## Runtime procedure

1. **Locate and verify the customer.** Use a supplied exact email or full name with the applicable user lookup tool. Ask for enough identity fields to satisfy two-of-four verification, compare them with the retrieved record, get the current time, and log the verification. If verification cannot be completed, do not access or change account-specific information.

2. **Retrieve accounts.** Unlock `get_all_user_accounts_by_user_id_3847`, then call it with the verified `user_id`. Retain each account's `account_id`, `account_type`, `account_class`, `status`, balance, and opening date. Select actual checking accounts only. Match account classes to the four supported names; do not infer a product from a nickname.

3. **Retrieve and classify activity.** For every relevant checking account, unlock and call `get_bank_account_transactions_9173(account_id)`. Transactions are reverse chronological. Review the requested calendar month plus adjacent dated withdrawals or credits when needed to link a fee/rebate that posted on a different date.

   For every ATM withdrawal related to a fee entry in scope, record:
   - withdrawal transaction ID, date, and cash amount;
   - whether it was domestic or foreign, and whether it was out-of-network when that fact matters;
   - each separately posted Rho/Bank ATM fee, its transaction ID, date, amount, and status;
   - each separately posted ATM-owner surcharge, its ID, date, amount, and whether it is confirmed eligible for a Purple operator-fee rebate;
   - each posted rebate credit known to relate to that specific operator fee.

   Classify each line from its description and available transaction facts. Ask the customer for a receipt or location details if the history does not establish the needed facts. Record every unclassified ATM-related fee line rather than silently excluding it.

4. **Calculate deterministically.** Build the JSON schema described in the script section and run `scripts/review_atm_fees.py`. Set `history_complete_by_account` to `true` only after all relevant history has been reviewed, and pass every line that remains unclassified in `unclassified_atm_fee_lines`. The script uses decimal arithmetic, produces per-event comparisons, tracks Light Blue's first two out-of-network withdrawals by withdrawal date, and tracks Purple's monthly operator-fee rebate cap.

5. **Review script output.** A proposed credit is usable only if the account result says `ready_for_credit: true`, its exact `recommended_credit_total` is greater than `0.00`, and all listed correction items are supported by the retrieved history. A warning about a pending line means it is not included. A blocking warning, an unknown transaction reference, a false completeness flag, or `manual_decision_required` means do not apply a credit until resolved.

   The script reports `fee_refund_items` and `missing_rebate_items`. Select the credit type from the strict majority of valid correction items:
   - `fee_refund` if fee-mischarge items are the majority;
   - `rebate_credit` if missing-rebate items are the majority.

   If there is no strict majority, do not guess a type or apply a credit; obtain appropriate policy guidance or escalate through the normal process.

6. **Apply only a validated correction.** For each eligible checking account, unlock `apply_checking_account_credit_5829` and call it once with:
   - `account_id`: the reviewed checking account ID;
   - `amount`: the script's exact positive `recommended_credit_total` expressed as a dollar number with two decimals;
   - `credit_type`: the majority type determined above.

   Do not call it for savings or other account types, no-error reviews, unsupported products, incomplete data, or unresolved ambiguity. If multiple valid corrections exist on one account, include their net total in the one call. If the tool rejects the call (including a cooldown), do not retry or claim that a credit was applied.

7. **Respond clearly.** Explain each confirmed fee versus the applicable rule, distinguish operator surcharges from bank fees, state any missing rebate and the $30 Purple monthly limit where applicable, and report only the credit and new balance actually returned by the tool. If all reviewed entries are correct, say so and explain the relevant charges without offering a discretionary credit.

## Calculator input and output

Run the packaged script through the runtime with an object like this (values are runtime-derived, not hardcoded):

```json
{
  "review_month": "YYYY-MM",
  "accounts": [
    {"account_id": "...", "account_type": "checking", "account_class": "Purple Account"}
  ],
  "history_complete_by_account": {"...": true},
  "transactions_by_account": {"...": [{"transaction_id": "..."}]},
  "events": [
    {
      "event_id": "...",
      "account_id": "...",
      "withdrawal_date": "MM/DD/YYYY",
      "withdrawal_amount": "100.00",
      "geography": "domestic",
      "out_of_network": true,
      "rho_fee_lines": [
        {"transaction_id": "...", "date": "MM/DD/YYYY", "amount": "-2.50", "status": "posted"}
      ],
      "operator_fee_lines": [],
      "rebate_lines": []
    }
  ],
  "unclassified_atm_fee_lines": []
}
```

`geography` must be `domestic` or `foreign`; `out_of_network` must be a boolean where the product rule requires it. `rho_fee_lines`, `operator_fee_lines`, and `rebate_lines` are separate arrays because their treatment differs. For Purple, set `eligible_for_purple_rebate: true` only when the operator fee is confirmed eligible. Put posted, confirmed-related rebate credits in that event's `rebate_lines`. Include all Light Blue out-of-network withdrawals in the withdrawal month, including fee-free ones, so the two-free-withdrawal allowance can be counted correctly.

The script emits JSON with event comparisons, exact `fee_refund_total`, `missing_rebate_total`, correction item counts, warnings, and an account-level `recommended_credit_total`. It does not perform banking actions.

## Unsupported or missing facts

This Skill does not establish policies for other account classes, disputed ATM cash dispensing, fraud, ATM-owner surcharge refunds, or charges not identifiable from transaction history. Do not use it to resolve those matters. Obtain the missing transaction facts or use the applicable specialized workflow instead.
