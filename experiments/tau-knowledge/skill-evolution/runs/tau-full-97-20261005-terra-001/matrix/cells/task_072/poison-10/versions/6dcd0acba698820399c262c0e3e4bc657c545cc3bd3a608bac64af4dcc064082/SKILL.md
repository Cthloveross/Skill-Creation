---
name: reconcile-atm-fees-and-correct-checking-accounts
description: Review a verified customer's monthly ATM fees and ATM-related rebates for Bluest and Light Green checking accounts, determine an exact supported correction, and apply at most one permitted checking-account credit per account.
---

# ATM Fee Review and Checking-Account Correction

Use this Skill when a customer asks to review ATM fees, missing Bluest ATM-fee rebates, or possible ATM-fee mischarges on a Bluest or Light Green checking account. It supports a transaction-history-based review; it does not infer ATM location, whether a charge is an operator surcharge, or account benefit eligibility from vague descriptions.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Preconditions and verification

1. Establish identity using **two of the four** record fields required by `log_verification`: date of birth, email, phone number, or address. A name is useful to locate a record but is not one of these two factors.
2. Compare the two customer-provided factors with the user record. Do not disclose the stored values to obtain a match.
3. Obtain the current timestamp with `get_current_time`, then call `log_verification` with the complete matched user-record fields and timestamp.
4. Establish authority and ownership by retrieving that user's accounts with `get_all_user_accounts_by_user_id_3847`. Use only account IDs returned for the verified user. Confirm the target account is a checking account and is OPEN before any credit.
5. Resolve a relative period such as “November” to a year. Ask if the intended year is not clear; do not silently use a different statement period.
6. Confirm product eligibility before calculating a correction:
   - **Bluest:** confirm the account is a Bluest Account and that the $112,500 daily-balance condition required to keep benefits active was met for the fee/rebate period. A current balance alone does not establish a historical daily-balance condition. If the available records cannot establish this, do not assume the rebate benefit was active.
   - **Light Green:** confirm the account is a Light Green Account and the account holder remains age 13–24 for the account. Its four free out-of-network withdrawals and subsequent $1.50 fee are monthly benefits.
7. The applicable prerequisites for this credit workflow are identity, authority, ownership, eligible open checking account, product eligibility, historical benefit status where required, exact fees, rebate cap, prior credits, and the documented one-call/cooldown limit. Recipient, debit-card details, transfer cutoffs, and available-balance sufficiency are not inputs to an account credit and are therefore not applicable. The documented credit procedure states no separate customer-confirmation step; do not claim that one exists. Follow any runtime policy that independently requires confirmation.

If verification, ownership, account status, product eligibility, or the exact transaction evidence cannot be established, explain the limitation and do not apply a credit. If the customer needs a fee reversal that cannot be resolved from the available evidence, transfer on request or when specialist review is needed using `complex_billing_dispute`, with a factual summary of the missing evidence and work completed.

## Retrieve and classify the activity

After verification, unlock and call the documented internal tools through the runtime's discoverable-tool flow:

1. Unlock `get_all_user_accounts_by_user_id_3847`; call it with the verified `user_id`.
2. For every relevant OPEN checking account returned (not merely an account mentioned by the customer), unlock `get_bank_account_transactions_9173`; call it with that account's `account_id`.
3. Retain the complete response, since transactions are reverse chronological. Filter the requested month only after retrieval. Consider posted entries for a correction; list pending entries separately and do not credit them as completed charges.
4. Classify each posted ATM withdrawal, ATM fee, and possible rebate/refund in the period using transaction type, description, location, and any reliable linked withdrawal information. Ask a targeted question or escalate instead of guessing when a fee is a third-party operator surcharge, location is foreign, or fee/withdrawal linkage is unclear.

Important distinctions:

- A **Bluest** account rebates eligible third-party ATM fees up to $50 per monthly statement cycle/month. Foreign withdrawals have no Rho-Bank ATM fee, but an ATM operator may charge a separate third-party fee. Existing ATM-related rebate credits reduce the still-missing rebate; never refund above the $50 cap.
- A **Light Green** account has four free out-of-network ATM withdrawals per month. Later domestic out-of-network withdrawals have a $1.50 Rho-Bank fee. Foreign withdrawal Rho-Bank fees are per withdrawal: $2.00 through $100, $3.50 above $100 through $300, and $5.00 above $300. Threshold values use the lower tier. An operator surcharge is separate and is not evidence of a Rho-Bank fee mischarge.
- Do not treat a debit-card ATM withdrawal amount as the amount dispensed for a foreign-fee tier if the amount may include a surcharge. Record the actual cash amount from reliable evidence.
- Look for existing `fee_rebate`, `rebate_credit`, or `fee_refund` entries, but count one only after confirming it relates to the ATM issue under review. Do not double-credit a correction already posted.

## Deterministic reconciliation helper

Use `scripts/reconcile_atm_fees.py` after retrieving all transactions and manually classifying ambiguous entries. The script reads one JSON object from stdin and emits one JSON object to stdout. It does not call banking tools and cannot apply a credit.

### Input schema

```json
{
  "account": {
    "account_id": "runtime account ID",
    "account_type": "checking",
    "account_class": "Bluest Account or Light Green Account",
    "status": "OPEN"
  },
  "period": {"year": 2025, "month": 11},
  "product_eligibility_confirmed": true,
  "benefit_active": true,
  "transactions": [
    {
      "transaction_id": "transaction ID",
      "account_id": "same runtime account ID",
      "date": "MM/DD/YYYY",
      "description": "source description",
      "amount": "signed amount",
      "type": "source transaction type",
      "status": "posted or pending"
    }
  ],
  "annotations": {
    "transaction ID": {
      "classification": "see allowed classifications below",
      "cash_withdrawal_amount": "required for a Light Green foreign withdrawal"
    }
  }
}
```

`benefit_active` is required and must be `true` for Bluest because historical balance eligibility must be established. It is ignored for Light Green. Classify all posted target-month ATM withdrawals, ATM fees, and possible rebate/refund credits with one of:

- `bluest_eligible_third_party_atm_fee`
- `bluest_existing_atm_rebate`
- `lg_domestic_oon_withdrawal`
- `lg_domestic_oon_rho_fee`
- `lg_foreign_withdrawal`
- `lg_foreign_rho_fee`
- `lg_existing_atm_fee_refund`
- `operator_surcharge`
- `unrelated`
- `unknown`

The helper rejects an unsupported account, non-posted fee/credit sign, mismatched account ID, missing classification, or insufficient foreign cash amount. `validation_errors` or `unresolved_transaction_ids` means the result is not exact enough to credit. A safe operational invocation sends the live, normalized tool results and annotations as the stdin JSON object to `scripts/reconcile_atm_fees.py`; inspect the returned `recommendation`, `components`, and `evidence_transaction_ids`.

For Bluest, the recommendation is:

`max(0, min(total eligible third-party ATM fees, 50.00) - existing related ATM rebates)`

For Light Green, it is the positive net excess of documented Rho-Bank charges over the domestic monthly fee schedule plus foreign per-withdrawal schedule, after related existing refunds. Operator surcharges are excluded.

## Apply a supported correction

Only proceed if the helper returns `safe_to_credit: true`, an amount greater than zero, and the reconciled result has been reviewed against the source transactions.

1. Confirm this is an authorized circumstance: a missing rebate uses `rebate_credit`; a fee mischarge uses `fee_refund`.
2. Unlock `apply_checking_account_credit_5829` and call it once with the returned `account_id`, positive two-decimal `amount`, and recommended `credit_type`.
3. Do not retry the tool. It may be called only once per checking account in this customer interaction, and the account has a 14-day cooldown after a credit. If there are both valid missing rebates and fee refunds for the *same* account, calculate both exactly first, combine them into one amount, and use the credit type covering the larger correction amount; still make only one call.
4. Read the tool response, report the applied amount, reason, and the new balance if returned. Do not invent a balance or an applied outcome if the call fails.
5. If the supported correction is zero, explain the reconciled fee schedule, the applicable cap or free-withdrawal count, and any existing credits. Do not call the credit tool.

## Output validation and failure handling

Before communicating a final resolution, verify that the account ID in every included transaction matches the selected account, all reviewed entries fall in the requested period, fees are treated as negative debits, credits as positive credits, all monetary values are rounded only to cents, and the result excludes pending and ambiguous entries. Preserve transaction IDs and calculation components in the case notes.

If transaction retrieval is unavailable, return only a factual status: the account could not be reviewed from the available feed and no correction was applied. Use `technical_system_error` only when a system failure prevents completion. Use `complex_billing_dispute` for unresolved fee-reversal evidence requiring specialist review; do not use an unsupported generic reason when that specific reason applies.
