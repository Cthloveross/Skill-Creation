---
name: review-checking-atm-fees
version: 1.0.0
description: Review a verified customer's November (or another confirmed period) checking-account ATM fees across Blue, Green, and Light Green accounts, identify documented bank-fee mischarges, and—only with required verification and confirmation—apply one exact net fee-refund credit per eligible checking account.
---

# Review Checking-Account ATM Fees

Use this Skill when a customer asks to investigate ATM fees on their checking account(s), particularly Blue, Green, or Light Green accounts. It supports a review of actual transaction history and a narrowly authorized correction for documented bank-fee mischarges. It does not treat ATM-owner/operator fees as bank fees and does not guess ATM location, foreign-currency status, or a fee-to-withdrawal match.

## Required controls

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this workflow:

1. Verify identity before exposing account activity or applying a credit. Obtain and confirm at least two of date of birth, registered email, phone number, and address against the user record. Obtain the current timestamp and call `log_verification` with all required fields only after the two-field verification succeeds.
2. Confirm the caller is the account owner and that every reviewed account belongs to the verified user. Review only active checking accounts. Credits may never be applied to savings or other account types.
3. Confirm the requested date range. If a year is not stated, do not silently review a prior November. If it is currently November, the safe default only after clearly telling the customer is November 1 through the current date/time; future dates cannot be reviewed.
4. Do not expose or act on an account that cannot be tied to the verified user. Do not apply a credit merely because a fee seems high.
5. Before a credit, verify the exact applicable fee, transaction history, any already-applied correction, the exact net correction, and the account's eligibility. Obtain explicit customer confirmation of the account and proposed credit amount.

## Runtime tools

The documented internal tools are discoverable. Unlock each before calling it:

- `get_all_user_accounts_by_user_id_3847(user_id)` — identify account IDs, account type/class, status, balance, and opening date.
- `get_bank_account_transactions_9173(account_id)` — retrieve all transaction records for an account; results are newest first.
- `apply_checking_account_credit_5829(account_id, amount, credit_type)` — use only for an approved, exact correction.

Use the normal identity lookup tools to locate the customer, `get_current_time` for the verification timestamp, and `log_verification` after successful verification. A lookup by name or email is only customer discovery; it is not by itself completion of the required two-field verification.

## End-to-end procedure

### 1. Establish scope and identity

- Acknowledge the request and explain that the review distinguishes Rho-Bank fees from ATM-owner/operator fees.
- Resolve the user record from customer-supplied identifying information. Ask for enough additional information to confirm two of the four required identity fields. Compare the supplied values with the retrieved record.
- On a successful comparison, call `get_current_time`, then `log_verification` using the retrieved full user record and that timestamp.
- Confirm the requested November/year or an explicit start and end date. State any current-month cutoff used.

### 2. Locate eligible accounts

- Unlock and call `get_all_user_accounts_by_user_id_3847` for the verified user ID.
- Select only the customer's active checking accounts whose account class/product is Blue, Green, or Light Green (or other accounts explicitly requested and supported by documented fee rules).
- Record each selected account ID, product, type, status, and balance. Do not infer product solely from a customer nickname if the returned account details disagree.

### 3. Retrieve and organize activity

- Unlock and call `get_bank_account_transactions_9173` once for each selected account.
- Filter the returned activity to the confirmed review period. The transaction list is reverse chronological, so sort relevant events chronologically before counting monthly free withdrawals.
- Identify posted `atm_withdrawal` and `atm_fee` transactions. Use descriptions, amounts, dates, and available ATM details to match a separate bank fee to its withdrawal. Keep matching rationale.
- Separately identify posted `fee_rebate`, `fee_refund`, and `rebate_credit` entries that demonstrably correct one of the ATM fees under review. Do not treat an unrelated credit as an ATM correction.
- Determine whether each withdrawal was in-network, out-of-network, or foreign-currency from transaction evidence. If the history cannot establish this, or cannot reliably match the fee to a withdrawal, list it as unresolved and ask for a statement/receipt or clarify with the customer. Never use a speculative expected fee as a basis for a credit.
- Exclude ATM-owner/network operator fees from the bank-fee comparison. They are separate charges and are not refundable under these schedules.

### 4. Apply the documented fee schedule

Evaluate each confirmed bank fee independently, in cents. The charged amount is the Rho-Bank fee associated with the withdrawal, not cash dispensed and not an operator fee.

| Product | Confirmed withdrawal classification | Expected Rho-Bank fee |
|---|---|---|
| Blue | Foreign-currency | `max(3% of USD-equivalent withdrawal, $5.00)` |
| Blue | Domestic out-of-network | `min(1% of withdrawal, $3.00)` |
| Green | Foreign-currency | `max(3% of USD-equivalent withdrawal, $5.00)` |
| Green | Domestic out-of-network | `$3.00` |
| Light Green | Foreign-currency | `$2.00` if withdrawal is ≤ $100; `$3.50` if > $100 and ≤ $300; `$5.00` if > $300 |
| Light Green | Domestic out-of-network | First four such withdrawals in the calendar month are $0.00; each later withdrawal is $1.50 |
| Any product | In-network | $0.00 under the supplied out-of-network/foreign fee rules |

Foreign-fee rules are separate per-withdrawal rules. Do not stack a domestic out-of-network fee or Light Green's domestic free-withdrawal benefit onto a foreign fee unless a documented transaction rule expressly establishes both charges. Amounts exactly at Light Green's $100 and $300 thresholds use the lower tier.

Use `scripts/analyze_atm_fees.py` for deterministic calculation after normalizing the relevant, confidently matched events. It emits qualified, unresolved, and overcharged findings. Review its result against the transaction descriptions; the script does not itself establish ATM classification or fee matching.

### 5. Determine whether a correction is authorized

For each account:

- Calculate each supported overcharge as `charged_bank_fee - expected_bank_fee` only when positive.
- Offset it only by an already-posted correction that is demonstrably tied to the same reviewed ATM-fee discrepancy. The result is the exact net correction; never round or estimate.
- If the net correction is zero or negative, do not credit the account.
- Recheck transaction history immediately before action to confirm the correction was not already posted and that no prior credit has been applied during this interaction. The credit tool is limited to one call per checking account per customer interaction and enforces a 14-day cooldown.
- Explain the date, withdrawal, fee charged, expected bank fee, existing correction (if any), and proposed net refund. Ask the customer for explicit confirmation to apply the stated refund.

### 6. Apply a credit only when authorized

When all controls pass and the customer explicitly confirms:

- Call `apply_checking_account_credit_5829` exactly once for that checking account with the positive exact net amount and `credit_type: "fee_refund"`.
- If several ATM-fee discrepancies on that one account need correction, combine their net amounts in that single call.
- Do not make another call after a failed, uncertain, or duplicate-looking result. Escalate or explain the limitation instead.
- Report the successfully applied refund and returned updated balance, if supplied by the tool. If no credit is warranted, give the review findings and unresolved items without implying a refund was issued.

## Script interface

Run the packaged helper with JSON on standard input:

```json
{
  "account_product": "light green",
  "events": [
    {
      "id": "stable-event-id",
      "date": "MM/DD/YYYY",
      "withdrawal_amount": "125.00",
      "classification": "out_of_network",
      "charged_bank_fee": "1.50",
      "match_confident": true,
      "status": "posted",
      "note": "optional transaction-match rationale"
    }
  ],
  "existing_corrections": [
    {"event_id": "stable-event-id", "amount": "0.00", "match_confident": true}
  ]
}
```

`classification` must be one of `foreign`, `out_of_network`, `in_network`, or `unknown`. Supply only the Rho-Bank fee in `charged_bank_fee`; use `null` when a fee has not been reliably matched. `existing_corrections` must only contain confidently linked, already-posted ATM-fee corrections. The script emits JSON with event-level findings, `gross_overcharge`, `existing_corrections_total`, and `net_correction`, expressed as two-decimal strings. A non-empty `unresolved` array means those events must not support a credit.

## Validation checklist

Before customer communication or a credit, verify that:

- identity verification was logged after two matching identity fields;
- account ownership, active checking status, product, and date range are documented;
- every credited fee is posted, classified, and confidently matched to a withdrawal;
- Light Green domestic out-of-network events were sorted chronologically across the calendar month before the four-free count;
- foreign amounts use USD-equivalent posted withdrawal amounts;
- operator fees and unrelated credits were excluded;
- existing applicable refunds/rebates were netted once;
- the proposed amount is positive, exact to cents, and confirmed by the customer; and
- no previous credit call has been made for that account in this interaction.

If any item cannot be verified, complete the non-action review, request the missing evidence, and do not apply a credit.
