---
name: reconcile-atm-fees-and-credits
description: Securely review November (or another specified period) ATM fees for Bluest and Light Green checking accounts, calculate documented fee or rebate discrepancies from complete transaction history, and—only after all prerequisites and customer confirmation—apply one exact eligible checking-account credit per account.
---

# Reconcile ATM Fees and Eligible Credits

Use this Skill when a verified customer asks to investigate ATM fees, missing ATM rebates, or fee corrections on Bluest or Light Green checking accounts. It supports review, explanation, and the strictly controlled application of an eligible credit. It does not authorize any debit, adjustment to a savings account, estimated credit, or credit for an unsupported reason.

## Governing control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this workflow, do not expose account activity or take a credit action until identity, authority, and ownership are verified. Before a credit, verify checking eligibility, the applicable product policy, the complete relevant transaction history, prior credits/rebates, exact cents, the one-credit/cooldown restriction, and the customer's confirmation to apply it. Recipient/card/cutoff checks are not applicable unless the transaction data makes them relevant.

## Applicable policy

- **Bluest checking:** Rebate eligible third-party ATM fees up to **$50 per monthly statement cycle**. Aggregate eligible fees over $50 are not rebated. A missing amount is a `rebate_credit`, not a refund of an unrelated fee.
- **Light Green checking:** Four out-of-network ATM withdrawals are free each calendar month; subsequent out-of-network withdrawals incur a **$1.50** bank fee. Foreign ATM withdrawal bank fees are assessed per withdrawal: $2.00 at or below $100, $3.50 above $100 through $300, and $5.00 above $300. These bank fees are separate from fees imposed by an ATM operator. An excess bank fee is a `fee_refund`.
- Credits are allowed only for a documented missing rebate or fee mischarge, only on a checking account, and for the exact amount. The credit tool can be called only once per checking account in a customer interaction and is subject to a 14-day cooldown. Combine multiple supported corrections for one account into one call; choose the credit type applying to the majority of corrections if both types are genuinely present.

## Runtime workflow

1. **Establish identity without disclosing records.** Locate the customer using a supplied identifier if needed (for example, `get_user_information_by_email`). Ask the customer to confirm two of the following four profile fields; do not read the values to them: date of birth, email, phone number, and address. A name is not one of the two factors.
2. **Log successful verification.** Retrieve the profile by ID as needed, obtain the current time with `get_current_time`, and call `log_verification` only after two profile fields were independently confirmed. Supply all required profile fields and the timestamp to that tool.
3. **Retrieve owned bank accounts.** Unlock `get_all_user_accounts_by_user_id_3847`, then call it with the verified `user_id`. Confirm that each target is active, owned by this customer, is a checking account, and has a Bluest or Light Green account class/product. Do not rely on a customer’s account nickname alone.
4. **Retrieve complete history internally.** Unlock `get_bank_account_transactions_9173` and call it once for every eligible target `account_id`. Obtain the whole relevant November period, including posted and pending ATM withdrawals, `atm_fee` entries, and `fee_rebate`, `rebate_credit`, or `fee_refund` entries. If the customer says only “November” and the year or the Bluest statement-cycle boundaries are unclear, clarify them. Do not ask the customer to provide statements when the documented history tool is available.
5. **Normalize and reconcile.** Preserve transaction IDs, dates, descriptions, amounts, types, statuses, ATM location/network evidence, and links between a withdrawal and its related fee. Use `scripts/reconcile_atm.py` on structured, complete posted entries. Treat pending entries as informational; do not credit pending charges. For Bluest, confirm the exact statement-cycle scope rather than assuming a calendar month. For Light Green, include every out-of-network and foreign withdrawal in the calendar month, because omission changes the free-withdrawal count.
6. **Explain the result.** Identify each fee/rebate, the relevant rule, expected amount, recorded amount, and any exact supported discrepancy. If data is incomplete, a fee cannot be classified as a bank versus operator fee, a statement cycle is unknown, or no discrepancy exists, do not apply a credit. State what remains to be confirmed.
7. **Get explicit authorization for a supported credit.** The request to investigate is not authorization to change the balance. Tell the customer the account, exact total, reason, and resulting credit type, then obtain confirmation to apply it.
8. **Apply at most one authorized credit per account.** Immediately before the action, re-check ownership, checking status, exact amount, policy eligibility, prior rebate/refund postings, no earlier credit call in this interaction, and the 14-day cooldown. Unlock `apply_checking_account_credit_5829` and call it only with `account_id`, a positive exact decimal `amount`, and `credit_type` of `rebate_credit` or `fee_refund`. Never call it for a savings account or an unsupported/estimated discrepancy.
9. **Close accurately.** Report the completed credit and updated balance returned by the banking tool. If no credit is due, explain the calculation. If a required fact cannot be verified, do not make a compensating adjustment; offer an appropriate review or escalation path.

## Reconciliation helper

`scripts/reconcile_atm.py` is a calculation and validation aid only. It never invokes banking tools or changes an account.

It reads one JSON object from stdin and emits one JSON object to stdout.

### Input schema

```json
{
  "period": "YYYY-MM",
  "accounts": [
    {
      "account_id": "runtime account id",
      "product": "Bluest",
      "complete_period": true,
      "statement_cycle_confirmed": true,
      "events": [
        {
          "date": "MM/DD/YYYY",
          "status": "posted",
          "location_kind": "domestic_out_of_network | foreign | other",
          "withdrawal_amount": "120.00",
          "bank_atm_fee_amount": "0.00",
          "third_party_atm_fee_amount": "3.00",
          "rebate_amount": "0.00",
          "transaction_ids": ["source transaction ids"]
        }
      ]
    }
  ]
}
```

All money fields are nonnegative decimal strings. An event can contain just a rebate by setting withdrawal and fee fields to `0.00`. Supply all period events, not only suspicious ones. `third_party_atm_fee_amount` is used for Bluest only after the agent establishes from the transaction description/evidence that it is an eligible third-party operator fee. `bank_atm_fee_amount` is used for Light Green only after distinguishing the bank’s fee from an operator fee.

The helper returns account-level totals, discrepancy lines, warnings, and an optional `recommendation` with an exact positive amount and permitted credit type. A `blocked` result means a missing prerequisite makes calculation unsafe. Review raw transaction records before accepting any recommendation.

Example runnable call (replace all placeholder data with runtime-derived records):

```sh
python3 scripts/reconcile_atm.py <<'JSON'
{"period":"YYYY-MM","accounts":[]}
JSON
```

Validation expectations: confirm the output has one result per input account; accept a recommendation only when `status` is `ok`, there are no blocking errors, its amount is positive, every cited transaction ID maps to the retrieved history, and the reconciled period/cycle is complete. The executor must still perform the policy, identity, ownership, cooldown, and customer-confirmation checks described above.
