---
name: review-checking-atm-fees
version: 1.0.0
description: Review November (or another month’s) ATM fees on Purple, Light Blue, Dark Green, and Evergreen checking accounts, reconcile posted bank fees and eligible rebates against product terms, and safely issue one exact combined checking-account correction only when fully substantiated.
---

# Review Checking-Account ATM Fees

Use this Skill when a customer asks whether ATM-related charges, fee rebates, or refunds on one or more of the supported checking products were correct. It supports investigation and, only where the records prove a mischarge or missing rebate, a properly controlled correction.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Required tools and records

The workflow uses these discoverable internal tools when available:

- `get_all_user_accounts_by_user_id_3847(user_id)` for the customer’s accounts and account IDs.
- `get_bank_account_transactions_9173(account_id)` for account activity. Results are reverse chronological and include date, description, amount, type, and posting status.
- `apply_checking_account_credit_5829(account_id, amount, credit_type)` only for a proven correction.

Unlock a discoverable tool before calling it. Do not substitute credit-card tools for checking-account records. If a required tool is unavailable or does not return the relevant checking history, explain that the fees cannot be determined from the available records and request the relevant statement lines; do not guess or credit the account.

## Safe investigation workflow

1. **Authenticate and establish authority.** Obtain an identifier, retrieve the matching customer record, and have the customer confirm at least two of the four identity fields (date of birth, email, phone number, address) without disclosing unconfirmed values. Retrieve the current time and call `log_verification` with the complete matched record and timestamp only after two fields have been confirmed. Confirm the requester is the account holder.
2. **Retrieve accounts.** Use the account-list tool for the verified `user_id`. Confirm each named account is an open checking account owned by the verified customer. Record account ID, product/class, status, and balance. Do not investigate or credit a savings, closed, unknown, or unowned account.
3. **Retrieve and scope activity.** For every eligible account named by the customer, retrieve transaction history. Isolate the requested calendar month and retain all relevant `atm_withdrawal`, `atm_fee`, `fee_rebate`, `rebate_credit`, and `fee_refund` records, including pending versus posted status. ATM fee postings can have a date different from the related withdrawal, so use descriptions, amounts, locations, and nearby dates to reconcile them; do not assume a same-day match.
4. **Classify each withdrawal from the records.** Determine whether it was out-of-network domestic or foreign, the cash amount, and any separately charged operator surcharge. If location/network/currency classification is not shown, mark it unresolved rather than selecting a fee schedule by assumption. Operator surcharges are separate from the bank’s own ATM fee.
5. **Calculate expected bank fees.** Use `scripts/calculate_atm_fees.py` with withdrawals in chronological order for a single calendar month. It calculates only the documented bank fee, not third-party surcharges or uncertain rebate eligibility. Review the output against posted bank-fee transactions and all prior credits/rebates.
6. **Assess rebate eligibility separately.** For Purple, determine whether each operator fee is actually coded as an eligible ATM operator fee and is posted within the eligible rebate window. Total posted/eligible operator-fee rebates for the month cannot exceed $30. A missing rebate cannot be inferred merely because an ATM fee appeared: coding, posting, and the monthly cap matter.
7. **Calculate one exact net correction.** A correction is allowed only for a documented fee mischarge or a documented missing rebate that has not already been applied. Sum every proven overcharge and every proven missing eligible rebate, minus any refund/rebate already posted for the same item. Exclude pending, duplicate, ambiguous, third-party, and unsupported items. Preserve the withdrawal/fee/rebate mapping and calculation in the case notes.
8. **Apply only when authorized and complete.** Before applying, reconfirm identity, ownership, checking status, exact amount, and that the correction is one of the two allowed circumstances. The credit tool can be called only once per checking account per interaction and starts a 14-day cooldown. Combine all proven corrections for that account into one positive exact amount. Use `fee_refund` when fee-mischarge corrections are the majority; otherwise use `rebate_credit`. Do not make a zero-dollar call and never make a second call after an `UNKNOWN` or successful result.
9. **Close clearly.** Tell the customer which reviewed charges were correct, any exact correction applied, the credit type, and the resulting balance returned by the banking tool. If no correction is justified, explain the applicable terms and what record is missing. State that operator surcharges may be separate.

## Product fee rules

Apply only the rule matching the verified product and transaction classification.

| Product | Out-of-network domestic bank fee | Foreign ATM bank fee | Important rebate/allowance rule |
|---|---|---|---|
| Purple | $2.50 per withdrawal | $0.00 | Eligible posted ATM operator fees can be rebated up to $30 per month; coding and posting conditions apply. |
| Light Blue | First 2 withdrawals per month free, then $2.50 each | First 2 foreign withdrawals per month free, then $4.00 each | Allowances do not roll over; operator fees are separate. |
| Dark Green | 1% of withdrawal, $1.50 minimum | 2.5% of withdrawal, $6.00 maximum | Third-party operator fees may apply separately. |
| Evergreen | 1% of withdrawal, $2.50 maximum | 2% of withdrawal, $3.00 minimum | Third-party operator fees may apply separately. |

For Light Blue, submit only one mutually exclusive classification per withdrawal. If the record does not establish whether a foreign transaction should be governed by the foreign or the out-of-network schedule, leave it unresolved and obtain supporting detail.

## Calculator interface

Run `scripts/calculate_atm_fees.py` with JSON on standard input. It emits JSON on standard output.

Input schema:

```json
{
  "account_product": "purple|light_blue|dark_green|evergreen",
  "withdrawals": [
    {"amount": "positive USD decimal", "kind": "out_of_network|foreign"}
  ]
}
```

The withdrawals must be in chronological order and all belong to one calendar month for the specified checking product. The script rejects malformed or unsupported input. Its `expected_fee` values are two-decimal USD strings and `total_expected_fee` is the sum. This output is a calculation aid, not proof that a specific posted fee belongs to a specific withdrawal.

Example invocation through the packaged-script runtime uses the same object as `input_json`; do not use example transaction values as case evidence.

## Validation before a credit

Verify all of the following: authenticated customer; owned, open checking account; actual history retrieved; each disputed line matched; product and ATM classification established; correct monthly sequence; fee and rebate policies applied; prior corrections removed from the net; exact positive amount; and a single permitted credit call. If any condition fails, complete the informational review only and do not apply a credit.
