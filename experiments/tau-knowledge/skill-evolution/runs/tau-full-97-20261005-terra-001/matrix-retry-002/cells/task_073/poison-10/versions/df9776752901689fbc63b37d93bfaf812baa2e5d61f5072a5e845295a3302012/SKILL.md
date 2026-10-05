---
name: audit-and-correct-checking-atm-fee-mischarges
description: Audit a verified customer's monthly Blue, Green, and Light Green checking-account ATM activity, identify documented bank-fee overcharges including in-network and duplicate-fee contradictions, and prepare one exact fee-refund credit per eligible account after customer confirmation.
---

# Audit and Correct Checking ATM Fee Mischarges

Use this Skill when a customer asks to review ATM fees for Blue, Green, or Light Green checking accounts. It performs a complete month-level review before any correction. It does not authorize goodwill credits, unverified operator-fee reimbursements, or credits to non-checking accounts.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this workflow, identity and authority are prerequisites to disclosing account activity. Account ownership, checking status, product terms, posted transaction evidence, the exact amount, account status/balance, cooldown risk, and customer confirmation are prerequisites to applying a credit.

## Required operational sequence

1. **Verify the customer.** Match at least two customer-provided fields from email, date of birth, phone number, and address against a single customer record. Name alone is insufficient. Obtain the current time and call `log_verification` with the complete verified customer record and timestamp.
2. **Retrieve and validate accounts.** Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified user ID. For every checking account requested for review, confirm ownership, account ID, product/class, status, balance, and opening date. Do not assume a customer-named product exists or is checking.
3. **Retrieve complete monthly activity.** Unlock and call `get_bank_account_transactions_9173` once for each verified checking account under review. Retain every transaction in the requested calendar month, including all `atm_withdrawal`, `atm_fee`, `fee_refund`, `fee_rebate`, and `rebate_credit` records. Histories are reverse chronological, so sort records chronologically for monthly allowance calculations.
4. **Establish fee-to-withdrawal evidence.** Match each ATM-fee line to its associated withdrawal using a supplied transaction ID when available; otherwise use an unambiguous same-date transaction pairing and the descriptions. A withdrawal explicitly described as a `RHO-BANK` ATM is in-network. A fee line explicitly labelled `NON-RHO ATM FEE` is evidence of a purported bank non-network fee, not automatically an unassessable operator fee. If one withdrawal has repeated purported bank-fee lines, only the fee allowed for that one withdrawal may remain.
5. **Audit the whole account.** Run `scripts/atm_fee_audit.py` using all retrieved month transactions. Supply explicit `fee_context` only when classification or matching cannot safely be inferred from the public records. For Light Green, include every domestic out-of-network withdrawal in the month, including ones with no fee, so the four-free-withdrawal allowance is counted chronologically.
6. **Manually confirm prior corrections.** Review all historical refund/rebate entries and any already-applied correction. Do not assume that a generic credit resolved a particular fee without evidence. Exclude only amounts demonstrably corrected.
7. **Disclose the complete result before action.** For each affected account, explain the fee lines, associated withdrawal, allowed fee, actual fee, and total unresolved correction. Include all supported discrepancies for that account in one total; do not make partial or serial credits.
8. **Obtain explicit confirmation immediately before action.** Ask the customer to confirm the disclosed combined amount for each account. Earlier consent to investigate is not credit authorization.
9. **Apply and report the credit.** Reconfirm the account is an eligible checking account, checking status, account ownership, exact amount, credit type, cooldown/one-call restriction, and confirmation. Call `apply_checking_account_credit_5829(account_id, amount, "fee_refund")` no more than once for each affected account. Report the tool outcome, credit amount, and updated balance when returned.

If any prerequisite, match, eligibility fact, prior-correction status, cooldown status, or confirmation is unavailable, do not estimate, split a credit, retry a rejected call, or apply a credit. Explain the missing evidence or obtain appropriate assistance.

## Fee rules

Assess Rho-Bank fees separately from genuine ATM-owner/operator fees.

| Product | Transaction | Correct bank fee |
|---|---|---:|
| Blue | Domestic out-of-network withdrawal | 1% of withdrawal amount, capped at $3.00 |
| Blue | Foreign withdrawal | greater of 3% of USD-equivalent withdrawal or $5.00 |
| Green | Domestic non-network withdrawal | $3.00 |
| Green | Foreign withdrawal | greater of 3% of USD-equivalent withdrawal or $5.00 |
| Light Green | Domestic out-of-network withdrawal | first four in each calendar month free; $1.50 each after the fourth |
| Light Green | Foreign withdrawal | $2.00 through $100; $3.50 over $100 through $300; $5.00 over $300 |
| Any listed product | In-network RHO-BANK withdrawal | $0.00 under these out-of-network fee schedules |

For Light Green foreign tiers, a withdrawal exactly equal to $100 or $300 receives the lower tier. Count the Light Green domestic allowance by withdrawal date and retain a deterministic transaction-ID tie-breaker when dates are the same.

A supported overcharge includes: a purported non-network bank fee paired with a documented RHO-BANK withdrawal; an amount over the schedule; a premature Light Green domestic charge within the first four monthly out-of-network withdrawals; and duplicate purported bank-fee lines for one withdrawal. Do not discard an explicit `NON-RHO ATM FEE` merely because an ATM owner can separately charge fees.

Rho Bank Plus operator-fee reimbursement is distinct. Consider it only if active membership, an actual operator-fee line, eligibility, month-to-date reimbursements, and the $32 cap are all verified. It does not cover conversion or other third-party charges, and an unclassified fee must not be assumed eligible.

## Credit constraints

Credits are permitted only for a documented fee mischarge or missing eligible rebate, and only to checking accounts. `apply_checking_account_credit_5829` accepts a positive exact amount and `fee_refund` or `rebate_credit`. It may be called only once per checking account per customer interaction and imposes a 14-day cooldown. Therefore aggregate every unresolved supported fee mischarge for one account into one exact `fee_refund` call. Never issue separate calls for individual fee lines.

## Audit helper interface

Run the packaged script with JSON on stdin and read one JSON object from stdout:

```sh
python3 scripts/atm_fee_audit.py <<'JSON'
{
  "review_month": "YYYY-MM",
  "accounts": [{"account_id":"ACCOUNT_ID","account_type":"checking","account_class":"Blue Account"}],
  "transactions_by_account": {"ACCOUNT_ID": [/* complete month transaction records */]},
  "fee_context": {
    "FEE_TRANSACTION_ID": {
      "withdrawal_transaction_id":"WITHDRAWAL_TRANSACTION_ID",
      "withdrawal_classification":"foreign",
      "fee_component":"bank_fee"
    }
  }
}
JSON
```

Required input fields are `review_month` (`YYYY-MM`), `accounts`, and `transactions_by_account`. Each transaction must contain `transaction_id`, `date` (`MM/DD/YYYY`), `amount`, `type`, `status`, and, for automatic description-based inference, `description`. `fee_context` is optional and may specify `fee_component` (`bank_fee` or `operator_fee`) and a withdrawal classification (`in_network`, `domestic_out_of_network`, or `foreign`). `correction_by_fee_id` is optional, but may contain only verified prior corrections as `{fee_id: {"amount":"positive decimal", "transaction_id":"..."}}`.

The script emits `fee_results`, one result per fee line; `combined_credit_candidates`, grouped exact unresolved bank-fee totals by account; and `validation_errors`. A candidate is a calculation aid, never authorization to credit. Do not credit when `validation_errors` are material to the account, an applicable fee is `unassessable` or pending, or manual prerequisite checks have not been completed.
