---
name: november-atm-fee-reconciliation
version: 1.0.0
description: Review ATM withdrawals and ATM-fee charges for a customer's Blue, Green, and Light Green checking accounts; distinguish bank fees from ATM-operator charges; calculate documented fee mischarges; and safely prepare any permitted checking-account fee refund.
---

# November ATM Fee Reconciliation

Use this Skill when a verified customer disputes ATM fees and the relevant accounts may be Blue, Green, or Light Green checking accounts. It is designed for a complete calendar-month review and does **not** infer facts absent from the transaction record.

## Guardrails

- Do not apply, promise, or estimate a credit until identity is verified, the account is confirmed as a checking account, and the relevant transaction history has been reviewed.
- A transaction description must support the withdrawal location and network classification. Do not assume that an unfamiliar ATM is foreign or out of network.
- ATM-owner/operator surcharges are separate from Rho-Bank fees and are not refundable under these schedules.
- Assess only posted charges. Pending withdrawals or fees should be explained as pending and reviewed after settlement; do not include them in a credit.
- A fee refund is allowed only for a documented fee mischarge, must be exact, and must be applied only once per checking account during this interaction. The banking system also enforces a 14-day cooldown for that account.
- The supplied user record is an account lookup, not identity verification. Before account-specific review or a credit, obtain confirmation of two of date of birth, phone number, address, and email, compare them with the profile, then log the verification.

## Runtime workflow

1. **Set the review period.** Confirm the statement year if unclear. For an unqualified request made during November, review November of the current year through the available transaction date. Record the exact start and end dates used.
2. **Verify identity.** Obtain and match two profile fields. Call `get_current_time`, then call `log_verification` with the complete returned profile and timestamp. If two fields cannot be matched, do not retrieve account activity or apply a credit.
3. **Retrieve the accounts.** Unlock `get_all_user_accounts_by_user_id_3847`, then call it with the verified runtime user ID. Select only active checking accounts whose account class identifies them as Blue, Green, or Light Green. Retain account ID, class, status, balance, and opening date for the review record. If a requested product cannot be identified or is not a checking account, explain that it cannot be reviewed as that product and do not credit it.
4. **Retrieve activity.** Unlock `get_bank_account_transactions_9173` and call it once for each selected account ID. Extract every in-period ATM withdrawal and ATM-fee line, including transaction ID, date, description, signed amount, type, and status. Transaction results are reverse chronological, so sort posted withdrawals chronologically before applying Light Green's monthly allowance.
5. **Classify using evidence, not guesswork.** For each withdrawal, determine from its description/transaction evidence whether it was domestic or foreign and, for domestic withdrawals, whether it was out of network. Associate each Rho-Bank ATM-fee entry with its withdrawal only when the records support that association. Mark ATM-owner fees as `operator`; do not treat them as Rho-Bank fees. If location, network status, ownership, or fee-to-withdrawal association cannot be established, tell the customer what cannot yet be determined and do not submit a credit for that unresolved scope.
6. **Calculate and review.** Normalize the extracted records into the JSON schema accepted by `scripts/atm_fee_review.py`, then run the script. It uses exact decimal arithmetic and reports expected fees, charged Rho-Bank fees, daily-limit observations, unresolved evidence, and a candidate net refund. A candidate is not authorization by itself.
7. **Make the decision.** Review the script rows against the original transaction descriptions. A positive `candidate_credit.amount` is actionable only when `candidate_credit.eligible_for_submission` is true and all manual evidence remains valid. If the result is zero, negative, incomplete, or unresolved, do not call the credit tool. Explain the reviewed fee calculations and any limitation instead.
8. **Apply an eligible correction.** Unlock `apply_checking_account_credit_5829`. For each eligible checking account, call it no more than once with the account ID, the exact positive candidate amount, and `credit_type` set to `fee_refund`. Do not combine different accounts into one credit. If multiple supported discrepancies exist on one account, submit their one net correction in that single call.
9. **Confirm completion.** After a successful credit, retrieve accounts again to obtain the updated balance and, when needed, retrieve transactions to confirm the posted correction. Tell the customer the affected account, exact refund, reason, and new balance. If a tool rejects the action because of cooldown or other system state, do not retry; explain that no additional credit was applied.

## Fee rules encoded by the helper

All withdrawal amounts are the USD amounts posted to the account.

| Product | Domestic ATM fee | Foreign ATM fee | Daily ATM limit |
|---|---|---|---:|
| Blue | Out-of-network: 1% of withdrawal, capped at $3.00 | Greater of 3% or $5.00 | $500 |
| Green | Non-network: $3.00 | Greater of 3% or $5.00 | $600 |
| Light Green | First four domestic out-of-network withdrawals in the calendar month: $0; each later one: $1.50 | Up to and including $100: $2.00; over $100 through $300: $3.50; over $300: $5.00 | $150 |

For Light Green, the first-four allowance is processed across all supported **posted domestic out-of-network** withdrawals in chronological order. Foreign withdrawals use the separate foreign schedule and do not consume that allowance. Daily-limit observations are informational; a limit anomaly alone is not a basis for a fee refund.

## Helper interface

Run `scripts/atm_fee_review.py` using the Skill runtime. The script reads one JSON object from stdin and emits one JSON object to stdout. It has no external dependencies and does not call banking tools or apply credits.

### Input schema

```json
{
  "account": {"account_id": "string", "product": "blue|green|light_green"},
  "review_month": "YYYY-MM",
  "coverage_complete": true,
  "withdrawals": [
    {
      "transaction_id": "string",
      "date": "MM/DD/YYYY or YYYY-MM-DD",
      "amount": "positive USD amount",
      "status": "posted|pending",
      "location": "domestic|foreign|unknown",
      "out_of_network": true,
      "fee_transaction_ids": ["associated ATM-fee transaction IDs"]
    }
  ],
  "fees": [
    {
      "transaction_id": "string",
      "date": "MM/DD/YYYY or YYYY-MM-DD",
      "amount": "negative posted debit amount",
      "status": "posted|pending",
      "kind": "bank|operator|unknown"
    }
  ]
}
```

`coverage_complete` may be true only after all relevant in-period ATM withdrawals and ATM-fee lines from the retrieved history have been included. Use `unknown` rather than inventing a classification. `fee_transaction_ids` are explicit evidence-based associations; the helper deliberately does not guess associations by date or dollar amount.

The output has `ok`, per-withdrawal `assessments`, `unresolved`, `unmatched_fee_ids`, `daily_limit_observations`, exact two-decimal totals, and `candidate_credit`. Submit only `candidate_credit.amount` when `eligible_for_submission` is true and the independent procedural checks above are complete.

### Meaningful validation

Before relying on an output, ensure:

- `ok` is true;
- account ID and product match the account record;
- every source record is from the intended calendar month and has been included;
- every bank or unknown ATM-fee record is either associated to one withdrawal or appears in `unmatched_fee_ids` for further investigation;
- `unresolved` is empty and `coverage_complete` was truthfully set to true;
- all candidate components can be traced to posted source transactions; and
- the computed candidate is positive and is reviewed before the one permitted credit call.

If the helper emits `ok: false`, correct the normalized input rather than guessing. If the transaction evidence cannot support classification, provide the customer the completed portions of the review and request a statement or allow settlement before resuming.
