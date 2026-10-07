---
name: november-atm-fee-review
version: 1.0.0
description: Review posted November ATM fees across a verified customer's Blue, Green, and Light Green checking accounts, identify exact bank-fee mischarges from account-specific terms, and safely prepare a consolidated correction for confirmation.
---

# November ATM Fee Review

Use this Skill when a customer asks to investigate ATM fees on one or more Blue, Green, or Light Green checking accounts. It supports a review and, only after all banking prerequisites and customer confirmation, a single eligible checking-account fee-refund credit.

## Safety and prerequisites

Before **any** bank lookup, transaction review, credit, or other banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For this workflow:

1. Obtain and independently confirm at least two of the four identity fields: date of birth, email, phone number, and address. A name alone is not an identity factor.
2. Look up the supplied identifier, compare the two confirmed fields to the returned profile, obtain the current time, and create the verification audit record with `log_verification`.
3. Use `get_all_user_accounts_by_user_id_3847(user_id)` to retrieve accounts. Review only accounts returned for that verified user, with `account_type` checking and an applicable account class. Do not infer that a claimed account exists or is active.
4. Confirm account ownership from that result. For an account that is closed, ineligible, or whose class cannot be determined, do not make a credit. Explain the limitation or obtain the necessary account-status clarification.
5. Before a credit, verify the fee, exact amount, applicable monthly ordering/count, transaction status, account eligibility, 14-day/one-credit constraint, and the customer's confirmation to apply the credit.

Providing an email for lookup is not by itself sufficient verification. Do not reveal transaction details until verification is complete.

## Retrieve and organize activity

1. Unlock and call `get_all_user_accounts_by_user_id_3847` after verification. Record only the returned account IDs needed for the review.
2. For each eligible checking account, unlock and call `get_bank_account_transactions_9173(account_id)`.
3. Select records dated in the requested November. Transaction dates are `MM/DD/YYYY`; use the requested or current-year November and clarify the year if it is ambiguous. Keep posted and pending records distinct.
4. Collect every posted `atm_withdrawal` and `atm_fee` record. Preserve transaction ID, date, description, amount, type, and status. The history is reverse chronological, so sort withdrawals oldest-to-newest before applying Light Green's monthly free-withdrawal count.
5. Determine each successful withdrawal's route from the transaction description or other supported record details:
   - `domestic_in_network`
   - `domestic_out_of_network`
   - `foreign`

   Also determine whether a fee line is a Rho-Bank fee or a separate ATM-owner/operator fee. Do not call an operator fee a bank mischarge. If a route, withdrawal-to-fee pairing, currency status, or operator-fee distinction cannot be supported by the available records, mark that item **needs clarification** rather than guessing.
6. Do not treat pending items as settled mischarges or include them in a credit. They may be described separately as pending observations.

## Fee rules to audit

Calculate only Rho-Bank's fee. All amounts are USD; use the USD-equivalent withdrawal amount for a foreign withdrawal.

| Account class | Successful domestic out-of-network withdrawal | Foreign-currency withdrawal |
|---|---|---|
| Blue Account | 1% of the withdrawal amount, capped at $3.00 | greater of 3% of USD equivalent or $5.00 |
| Green Account (checking) | $3.00 | greater of 3% of USD equivalent or $5.00 |
| Light Green Account | First 4 out-of-network withdrawals in the calendar month are free; each later withdrawal is $1.50 | $2.00 if amount is at most $100; $3.50 if over $100 through $300; $5.00 if over $300 |

No bank fee is expected for an in-network domestic withdrawal under these rules. For Light Green, exact thresholds of $100 and $300 use the lower tier. Treat each foreign withdrawal as its own fee event; do not silently count it against the domestic free-withdrawal allowance unless the transaction data or governing policy explicitly establishes that it does.

A discrepancy is `actual Rho-Bank fee - expected Rho-Bank fee`. A positive discrepancy is an overcharge eligible to be considered for refund; zero is correct; a negative discrepancy is not a reason to debit the customer. A missing matching fee line is an observation, not a fee overcharge.

## Deterministic calculation helper

Use `scripts/audit_atm_fees.py` to calculate expected fees after transaction review and classification. It performs no banking action.

Input JSON schema:

```json
{
  "account_class": "Blue Account | Green Account | Light Green Account",
  "withdrawals": [
    {
      "withdrawal_id": "transaction identifier",
      "date": "MM/DD/YYYY",
      "amount": 0,
      "route": "domestic_in_network | domestic_out_of_network | foreign",
      "status": "posted"
    }
  ],
  "fees": [
    {
      "fee_id": "transaction identifier",
      "withdrawal_id": "matching withdrawal identifier",
      "amount": 0,
      "fee_source": "bank | operator",
      "status": "posted"
    }
  ]
}
```

Withdrawal amounts and fee amounts may be signed transaction values or positive dollar amounts; the helper uses their absolute values. Each bank-fee item must be paired to a withdrawal ID based on supported transaction evidence. The helper rejects unknown classes, routes, malformed dates, duplicate IDs, unsupported statuses, and unpaired bank fee entries. It emits JSON containing itemized expected/actual amounts, positive overcharges, pending records, and a two-decimal `total_overcharge`.

Example runnable call (illustrative values only):

```sh
python3 scripts/audit_atm_fees.py <<'JSON'
{"account_class":"Blue Account","withdrawals":[],"fees":[]}
JSON
```

Validate that every posted ATM fee from the transaction history is either represented once in `fees` or separately listed as unresolved with an explanation; validate that Light Green posted domestic out-of-network withdrawals are in chronological order; and compare the helper's item IDs and totals to the source transaction records before communicating results.

## Customer outcome and correction path

Give an itemized, plain-language review: account, withdrawal date and amount, route if supported, expected Rho-Bank fee, posted Rho-Bank fee, operator fees excluded, and whether the result is correct, overcharged, or unresolved. State that a foreign ATM operator may separately charge its own fee.

If no confirmed positive discrepancy exists, explain that no fee-refund credit is warranted. If evidence is incomplete, request the necessary statement/transaction detail or explain the system limitation; do not estimate a refund.

If one or more exact fee mischarges are confirmed:

1. Total all positive corrections separately for each checking account. Do not offset an overcharge with a correctly charged or undercharged item.
2. Ask the customer to confirm the exact total credit for each affected account before proceeding.
3. Verify that no checking-account credit has already been applied in this interaction and that the account is eligible under the 14-day cooldown.
4. Unlock and call `apply_checking_account_credit_5829(account_id, amount, "fee_refund")` once for that account only. The amount must be the exact positive total, with two decimal places.
5. Do not credit savings or other account types, do not use a credit for an unconfirmed or pending item, and do not call the credit tool more than once per account in the interaction. If unrelated missing rebates are also established, combine corrections only if policy permits one credit and choose the credit type that represents the majority; otherwise do not improvise another call.
6. After a successful credit, report the credit amount and new balance returned by the normal banking tool. If the tool fails or eligibility/cooldown cannot be confirmed, do not retry blindly; explain the outcome and escalate through the approved support process if needed.

The helper is advisory only. It never unlocks tools, retrieves records, verifies identity, or applies money movement.
