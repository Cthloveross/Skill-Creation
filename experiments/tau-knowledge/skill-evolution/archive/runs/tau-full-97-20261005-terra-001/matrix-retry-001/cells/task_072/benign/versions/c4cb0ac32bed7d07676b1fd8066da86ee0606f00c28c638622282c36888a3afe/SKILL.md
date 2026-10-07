---
name: audit-and-correct-checking-atm-fees
description: Verify a customer, review all requested checking-account ATM activity for a calendar month, calculate supported Bluest or Light Green ATM fee/rebate corrections, and apply one exact combined checking-account credit per eligible account.
---

# ATM fee and rebate audit

Use this Skill when a customer reports potentially incorrect ATM fees or missing ATM rebates on Bluest and/or Light Green checking accounts. The goal is to complete the requested review and, when the posted history establishes a correction, apply the exact combined correction during the interaction.

## Governing rules

- Verify identity before disclosing account-specific activity or applying a credit. Match two of email, date of birth, phone number, and address against the customer record. Name is not one of the two factors. After successful verification, obtain the current timestamp and call `log_verification` with every required customer-record field.
- Retrieve all accounts with `get_all_user_accounts_by_user_id_3847`, then retrieve history with `get_bank_account_transactions_9173` for **every checking account**. Do not limit the review to the account the customer happens to mention first.
- Use posted entries to establish a correction. Mention relevant pending ATM items, but do not credit a pending item.
- Credits are permitted only to checking accounts and only for a documented fee mischarge or missing eligible rebate. The amount must be positive and exact.
- `apply_checking_account_credit_5829` is limited to one call per checking account per interaction and causes a 14-day cooldown. Add all supported correction components for that account into one credit before making the call.
- When multiple components are combined, use the credit type applying to the majority of components. A fee overcharge is a `fee_refund`; a missing rebate is a `rebate_credit`. If component counts tie, do not invent a tie-breaker.

## Account schedules

### Bluest

- Rho's foreign ATM withdrawal fee is $0. Any posted Rho foreign fee is refundable in full.
- Rho's domestic out-of-network ATM fee is $2 per withdrawal. Refund the excess of a documented Rho charge over $2.
- Eligible third-party/non-Rho ATM fees are rebated up to $50 per month. Calculate the shortfall as `min(eligible posted third-party fees, 50) - posted ATM rebates`, if positive.
- Do not treat a third-party operator fee as a Rho fee. In particular, a description explicitly identifying a fee as non-Rho supports rebate eligibility, not a refund of that operator's fee.

### Light Green

- The first four domestic out-of-network withdrawals in the review month are free. Each later domestic out-of-network withdrawal costs $1.50.
- Rho foreign ATM fees are $2.00 for a withdrawal of $100 or less, $3.50 for more than $100 through $300, and $5.00 above $300.
- Foreign and operator fees are separate. Apply the domestic or foreign schedule only when the transaction details establish the fee classification and the withdrawal to which it belongs.

## End-to-end procedure

1. Obtain the second identity factor if needed, lookup the customer record, verify two factors, retrieve the current time, and log verification.
2. Unlock `get_all_user_accounts_by_user_id_3847` and retrieve the customer's accounts. Keep each open checking account and its account class; do not credit savings or another account type.
3. Unlock `get_bank_account_transactions_9173` and retrieve the complete history once for each checking account. Select the requested calendar month, sort the records chronologically for monthly withdrawal counts, and preserve transaction IDs, dates, descriptions, amounts, types, and statuses.
4. Review every posted ATM withdrawal, ATM fee, and rebate in the month. Explicit descriptions such as `FOREIGN ATM FEE`, `NON-RHO ATM FEE`, and account-history withdrawal descriptions may establish classifications. Never assume that a generic ATM fee is foreign, Rho, third-party, or attached to a particular withdrawal.
5. Run `scripts/audit_atm_fees.py` using the retrieved records. Supply annotations only for classifications and fee-to-withdrawal links actually supported by the history. The helper automatically recognizes the unambiguous Bluest labels `FOREIGN ATM FEE...`, `NON-RHO ATM FEE`, and posted `fee_rebate` records.
6. If an account result is `credit_recommended`, confirm that it remains a checking account, that the exact components agree with history, and that no prior credit has been applied to that account in this interaction. Unlock `apply_checking_account_credit_5829` and make exactly one call with the helper's `credit_amount` and `credit_type`.
7. Do not stop at explanation when a fully supported positive recommendation exists: apply the combined correction. If the banking tool fails or reports a cooldown, do not retry the credit call.
8. Tell the customer what was reviewed, the fee/rebate correction and reason, and the updated balance returned by the credit tool. Explain unresolved or pending entries separately.

## Helper interface

The helper reads one JSON object from stdin and writes one JSON object to stdout. It has no banking-tool access and does not apply a credit.

Run it against a saved JSON request as follows:

```text
python scripts/audit_atm_fees.py < audit-input.json
```

Input schema:

```json
{
  "review_year": 2025,
  "review_month": 11,
  "accounts": [
    {"account_id": "checking-account-id", "account_type": "checking", "account_class": "Bluest Account"}
  ],
  "transactions_by_account": {
    "checking-account-id": [
      {"transaction_id": "transaction-id", "date": "MM/DD/YYYY", "description": "statement description", "amount": -2.0, "type": "atm_fee", "status": "posted"}
    ]
  },
  "annotations": [
    {"account_id": "checking-account-id", "transaction_id": "fee-id", "kind": "light_foreign_rho_fee", "withdrawal_id": "withdrawal-id"}
  ]
}
```

`annotations` is optional and is used only when transaction descriptions establish facts that raw transaction fields do not encode. Valid annotation kinds are:

- `out_of_network_withdrawal` on a domestic Light Green ATM withdrawal
- `light_domestic_oon_rho_fee` or `light_foreign_rho_fee` on a Light Green ATM fee; both require `withdrawal_id`
- `bluest_foreign_rho_fee`, `bluest_out_of_network_rho_fee`, or `bluest_third_party_atm_fee` on a Bluest ATM fee
- `bluest_atm_rebate` on a Bluest posted rebate

The output contains one result per supplied account. A credit is authorized by this Skill only when `ready_for_credit` is true, `credit_amount` is greater than zero, and no top-level `errors` are present. `manual_review` is a stop condition: obtain or inspect the missing detail rather than guessing. Validate that the applied tool arguments exactly equal the helper result and that only one credit call is made for that account.
