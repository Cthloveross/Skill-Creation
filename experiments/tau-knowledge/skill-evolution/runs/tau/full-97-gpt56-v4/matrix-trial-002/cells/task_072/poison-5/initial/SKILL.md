---
name: review-atm-fees-and-correct-checking-accounts
description: Review a verified customer's Bluest Account and/or Light Green Account ATM withdrawals, ATM fees, and rebates for a stated period; explain correct charges and, only when fully supported, apply one exact checking-account credit per eligible account.
---

# Review ATM Fees and Eligible Corrections

Use this Skill when a customer asks why ATM fees or ATM-fee rebates appear wrong on a Bluest Account or Light Green Account. It supports investigation, a clear customer explanation, and a narrowly authorized correction for a documented missing rebate or fee mischarge. It does not authorize credits for goodwill, uncertainty, third-party fees that are not covered by the product terms, or any other reason.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Safety and authorization gate

Do not retrieve or discuss account transactions as belonging to the caller, and do not apply a credit, until all applicable prerequisites below are satisfied.

1. **Identity and authority:** Obtain a customer-provided identifier to locate the customer record, then have the caller confirm at least two profile fields without disclosing them first (date of birth, email, phone number, or address). Obtain the current timestamp with `get_current_time` and call `log_verification` with the complete returned customer record and that timestamp. Treat an unverified name or email used for lookup as a lead, not verification.
2. **Ownership and account status:** Retrieve the customer's accounts and confirm the target account belongs to the verified customer, is a checking account, and is in a status that permits the requested review/credit. Do not confuse a credit-card account with a checking account.
3. **Product eligibility:** Confirm the returned account class is the product being evaluated. For Light Green, confirm the primary holder remains age 13 through 24. For Bluest benefits, obtain adequate evidence that the required $112,500 minimum daily balance was maintained; a current balance alone is not proof of a past daily-balance requirement.
4. **Transaction evidence:** Retrieve complete transaction history for every target account. Use the requested period and the correct year, and distinguish posted transactions from pending transactions. A fee must be tied to its withdrawal from an explicit reference or unambiguous transaction detail; do not guess based only on nearby dates or amounts.
5. **Credit prerequisites:** Before a credit, verify the fee/rebate policy, exact fee source, exact amounts, applicable statement-cycle boundaries, existing credits/rebates, the 14-day cooldown, and that no earlier credit has been made to that same account in this interaction. The credit tool is allowed only once per checking account per interaction. If any required fact is unavailable or ambiguous, explain the limitation and do not apply a credit.

## Bank-tool workflow

The account and transaction tools documented for this workflow are discoverable agent tools. Unlock each needed tool, then call it through the discoverable-agent-tool interface:

- `get_all_user_accounts_by_user_id_3847` with `{"user_id":"..."}` to obtain account ID, type, class, status, balance, and date opened.
- `get_bank_account_transactions_9173` with `{"account_id":"..."}` to obtain all transactions, newest first.
- `apply_checking_account_credit_5829` with `{"account_id":"...","amount":positive_number,"credit_type":"rebate_credit"|"fee_refund"}` only after the full credit gate passes.

Use normal identity lookup tools only to locate the possible customer record and perform the identity challenge above. If lookup returns no unique customer, the caller cannot pass verification, the account is not owned by the caller, or a required discoverable tool is unavailable, do not improvise an account ID or transaction history. State what is needed to continue.

### Investigation sequence

1. Ask which month and year should be reviewed if it is not clear. For Bluest, also establish the actual **monthly statement-cycle** start and end dates; a calendar-month assumption is insufficient for a $50-per-statement-cycle benefit.
2. Complete the safety and authorization gate, then retrieve all checking accounts for the verified user. Select only the verified customer's Bluest and/or Light Green checking account(s).
3. Retrieve each selected account's full transaction history. Make a ledger of each relevant ATM withdrawal, ATM fee, fee rebate, rebate credit, and fee refund. Preserve transaction ID, date, description, amount, type, status, fee source, location (domestic/foreign), withdrawal linkage, and any prior correction.
4. Normalize debit fee and withdrawal amounts to positive comparison amounts. Do not treat pending activity as a final fee mischarge. Explicitly mark uncertain location, fee source, linkage, or statement-cycle evidence as unresolved rather than assigning a result.
5. Apply the product rules below. The helper script can calculate from an explicitly normalized ledger, but it does not verify identity, ownership, account eligibility, transaction meaning, or authorize an action.
6. Give the customer an itemized result: date, withdrawal amount, domestic/foreign classification, actual fee or rebate, expected treatment, and whether a correction is supported. Explain unresolved entries and what evidence is needed.

## Product rules

### Bluest Account

- Bluest has no Rho-Bank foreign ATM withdrawal fee. A confirmed **Rho-Bank** fee tied to a foreign ATM withdrawal should therefore be $0 and is a potential fee-refund discrepancy.
- Bluest rebates eligible third-party ATM fees only up to an aggregate **$50 per monthly statement cycle**. Sum only confirmed eligible third-party ATM fees in the actual cycle and subtract confirmed ATM-fee rebates already applied for that same cycle. The potential missing rebate is no more than $50 in aggregate.
- Do not label an ATM operator's fee a Rho-Bank fee without explicit evidence. Do not refund third-party fees above the $50 cap. Do not apply a missing-rebate credit unless Bluest benefit eligibility, including the $112,500 minimum daily-balance requirement, has been verified for the relevant period.

### Light Green Account

- For confirmed domestic out-of-network ATM withdrawals, the first four in a month are free. Each later confirmed domestic out-of-network withdrawal should have a $1.50 Rho-Bank fee.
- A foreign ATM withdrawal has a separate per-withdrawal Rho-Bank fee schedule: $2.00 for an amount up to and including $100; $3.50 for more than $100 through and including $300; and $5.00 for more than $300. Threshold values use the lower tier.
- Use the foreign schedule for a confirmed foreign withdrawal; do not stack the domestic four-free-withdrawal rule with foreign pricing without policy evidence. ATM operator fees are distinct from Rho-Bank fees and are not automatically refundable.
- The daily ATM withdrawal limit is $150. Flag a purported withdrawal above that limit for investigation rather than inferring a fee correction from it.

## Determining and applying a correction

A credit is permitted only for a documented missing rebate or a documented fee mischarge, and only to a checking account.

1. Reconcile all supported fee discrepancies for an account and any supported missing rebate. Calculate the exact net positive correction; do not round or estimate.
2. Check full transaction history for `rebate_credit` and `fee_refund` activity in the preceding 14 days and for a credit already made during this interaction. If either condition prevents a call, do not call the credit tool.
3. If the net correction is zero or negative, do not apply a credit. If the result is uncertain because an entry cannot be classified or linked, do not apply a partial credit that could duplicate or omit a correction.
4. Combine all supported corrections for that account into one call. Use `rebate_credit` if missing-rebate corrections are the majority of corrections; use `fee_refund` if fee-mischarge corrections are the majority. If there is no clear majority, resolve the classification under documented policy before calling; do not guess.
5. Reconfirm the account ID, checking status, exact positive amount, and selected credit type immediately before the call. Then make no more than one credit call for that account.
6. After a successful call, report the amount, reason, and the new balance returned by the tool. If the call fails or reports an unknown outcome, do not retry it; record the result and seek appropriate support.

## Helper script

`scripts/review_atm_fees.py` is a deterministic ledger calculator. It reads one JSON object from standard input and writes one JSON object to standard output. It never calls bank tools and never authorizes a credit.

Input schema (all monetary values may be JSON numbers or decimal strings):

```json
{
  "account": {"account_id": "string", "account_class": "Bluest Account or Light Green Account"},
  "statement_cycle": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
  "prerequisites": {
    "identity_verified": false,
    "authority_verified": false,
    "ownership_verified": false,
    "checking_account_verified": false,
    "account_status_verified": false,
    "product_eligibility_verified": false,
    "balance_or_credit_verified": false,
    "no_credit_in_last_14_days": false,
    "no_prior_credit_this_interaction": false
  },
  "withdrawals": [
    {"id": "string", "date": "YYYY-MM-DD", "amount": "0.00", "location": "domestic|foreign|unknown", "out_of_network": true, "status": "posted"}
  ],
  "fees": [
    {"id": "string", "date": "YYYY-MM-DD", "amount": "0.00", "withdrawal_id": "string", "source": "rho_bank|third_party|unknown", "status": "posted"}
  ],
  "rebates": [
    {"id": "string", "date": "YYYY-MM-DD", "amount": "0.00", "purpose": "atm_fee|unknown", "status": "posted"}
  ]
}
```

`statement_cycle` is required for a Bluest rebate calculation. The executor must supply only entries inside the selected review period/cycle and only use explicit transaction evidence when normalizing source, linkage, and location. The output includes supported signed discrepancies, unresolved entries, a potential net correction, and `credit_action_allowed`. A `false` value means the result is informational only.

Example runnable call:

```sh
python3 scripts/review_atm_fees.py < normalized_atm_ledger.json
```

Validate that the account class is supported, every posted fee has a positive amount and an unambiguous linked withdrawal before relying on a fee result, all dates are valid ISO dates, each calculated fee follows the stated threshold rule, Bluest rebates never exceed $50, and `credit_action_allowed` is false until every prerequisite is affirmatively verified.
