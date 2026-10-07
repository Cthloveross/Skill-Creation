---
name: atm-fee-review-and-correction
version: 1.0.0
description: Review November (or another stated period) ATM charges on Blue, Green, and Light Green checking accounts; distinguish bank fees from ATM-operator fees, identify supportable fee mischarges or missing Rho Bank Plus reimbursements, and apply a compliant net checking-account credit only after verification.
---

# ATM fee review and correction

Use this Skill when a customer questions ATM withdrawal fees, asks for a transaction-history review, or may be owed an ATM-fee correction. It is intended for Blue, Green, and Light Green checking accounts.

## Policy facts used by this Skill

- A **Blue** domestic out-of-network ATM fee is 1% of the withdrawal, capped at $3.00. Its foreign ATM fee is the greater of 3% of the USD-equivalent withdrawal or $5.00.
- A **Green** foreign ATM fee is the greater of 3% of the USD-equivalent withdrawal or $5.00. Green domestic out-of-network documents conflict: one states $3.00 per withdrawal and another states four free monthly withdrawals followed by $1.50. Do not choose between those schedules or issue a correction for a Green domestic fee without an authoritative applicable account agreement or supervisor direction.
- A **Light Green** domestic out-of-network fee is $0 for the first four such withdrawals in a month and $1.50 thereafter. Its foreign fee is $2.00 through $100, $3.50 above $100 through $300, and $5.00 above $300, per withdrawal.
- ATM-operator fees are separate from bank ATM fees. Rho Bank Plus can reimburse eligible operator fees up to $32 per month, but the membership must be active and the reimbursement must actually be missing before it is treated as a possible missing rebate.
- A checking-account credit is allowed only for a verified fee mischarge or a missing, eligible rebate. It must be an exact positive amount, be applied only to a checking account, and may be applied only once per checking account per interaction (with a 14-day cooldown afterward). Combine all qualifying corrections for one account into one net credit. Use `fee_refund` for a fee correction and `rebate_credit` for a missing rebate; if both are combined, use the type covering the majority of the correction amount.

## Required conversation and verification

1. Acknowledge the request and explain that you will review each checking account's November ATM activity, including separate bank and ATM-owner charges.
2. Before disclosing account or transaction information or issuing a credit, verify the caller by having them confirm any two of date of birth, email, phone number, and address. Do not read unconfirmed profile values aloud as prompts.
3. Look up the user by the customer-provided name or email only as needed to locate the profile. Compare the two volunteered values against the profile. Obtain the current time and call `log_verification` with all required profile fields and that timestamp only after two fields match.
4. If identity cannot be verified, do not retrieve or discuss account-specific information and do not credit an account. Request the needed confirmation or follow the applicable escalation process.

## Banking-tool procedure

The named account and transaction tools are discoverable internal tools. Unlock each before calling it:

1. Unlock `get_all_user_accounts_by_user_id_3847`, then call it with the verified `user_id`.
2. From the returned active checking accounts, identify the Blue, Green, and Light Green accounts by their returned account type/class; do not assume an account exists merely because the caller named it. Note inactive, closed, savings, or unrecognized accounts separately and never credit non-checking accounts.
3. Unlock `get_bank_account_transactions_9173`, then call it once for each relevant checking `account_id`. The results are reverse chronological, so reorder the target month's ATM-related entries chronologically before counting Light Green domestic withdrawals.
4. Review all target-month posted ATM withdrawals, ATM fee transactions, possible ATM-operator charges, `fee_rebate`, `rebate_credit`, and `fee_refund` entries. Pending entries should be described as pending and not treated as settled mischarges. Pair a fee to the corresponding withdrawal using date, amount, description/location, and nearby transaction context. Do not infer that every ATM-related fee is a bank fee.
5. Establish whether a Rho Bank Plus membership is active using a supported membership/account record if one is actually available. Do not represent that the account lookup proves membership unless it explicitly does. If active status cannot be verified with available tools, state that limitation and do not credit a purported missing Plus reimbursement. If it is verified, calculate eligible unreimbursed **operator** fees for the month, net of already-posted reimbursements, subject to the $32 monthly cap.
6. Use `scripts/fee_review.py` after normalizing paired, settled events. The script deliberately reports Green domestic charges as unresolved rather than guessing through the documented policy conflict. Review its findings against the original transaction descriptions before deciding a credit.
7. For every account, verify no correction/rebate credit has already addressed the same charge. Confirm the exact net amount, checking status, and eligibility. If an `apply_checking_account_credit_5829` call is warranted, unlock it and call it exactly once for that account with the combined amount and the required credit type. Never call it for a preliminary estimate, a pending item, an ambiguous Green domestic item, an operator charge without proven membership eligibility, or an amount of zero.
8. If the credit tool reports a cooldown, failure, or uncertainty, do not retry. Explain the result and escalate where necessary.

## Interpreting outcomes and customer response

Give the customer an account-by-account summary: dates and descriptions reviewed, bank fee versus operator fee distinction, the applicable schedule or ambiguity, any existing rebate/refund found, and whether a correction was applied. If a credit succeeds, state its exact amount, reason, and the new balance returned by the banking tool. Do not promise reimbursement when eligibility, membership, transaction matching, or the applicable schedule is unconfirmed.

For Green domestic charges, clearly explain that the available account documents conflict and that the charge needs authoritative review rather than asserting it is correct or incorrect. Escalate a material unresolved billing dispute using the appropriate available human-transfer reason (normally `complex_billing_dispute`), with a concise summary of the accounts, entries, conflict, and work already completed.

## Analyzer input and output

Run the packaged helper by sending a JSON object on stdin. It does not access banking systems and does not apply credits.

Input schema:

```json
{
  "account_class": "Blue|Green|Light Green",
  "events": [
    {
      "date": "MM/DD/YYYY",
      "channel": "domestic_out_of_network|foreign",
      "withdrawal_amount": "positive USD amount",
      "bank_fee": "positive charged bank fee, or 0",
      "operator_fee": "positive operator fee, optional",
      "status": "posted|pending",
      "description": "optional statement description"
    }
  ],
  "prior_month_domestic_withdrawals": 0
}
```

`prior_month_domestic_withdrawals` is required for a Light Green review when the supplied events do not cover the beginning of the calendar month. It is the number of prior settled Light Green domestic out-of-network withdrawals in that same month. Events should otherwise include every settled target-month ATM withdrawal in chronological order. The script emits JSON with a per-event expected bank fee, a discrepancy amount (`actual - expected`), unresolved-policy flags, and a total supportable bank-fee overcharge. It does not decide Rho Bank Plus eligibility because active-membership and prior-reimbursement evidence must come from actual records.

Example execution after normalization:

```text
run_skill_script(relative_path="scripts/fee_review.py", input_json={"account_class":"Blue","events":[...],"prior_month_domestic_withdrawals":0})
```

Validate that each event is posted, paired to the correct withdrawal, in chronological order for Light Green domestic counting, and has a nonnegative dollar amount. The helper rejects malformed values and unsupported account classes/channels rather than silently calculating a credit.
