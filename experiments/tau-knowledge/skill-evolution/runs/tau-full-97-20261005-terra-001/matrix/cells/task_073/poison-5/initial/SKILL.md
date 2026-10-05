---
name: reconcile-checking-atm-fees
description: Review a verified customer's November (or other specified period) ATM-fee activity on Blue, Green, and Light Green checking accounts; distinguish bank fees from operator surcharges; calculate documented fees; and safely prepare a single exact fee-refund credit recommendation per eligible checking account.
---

# Reconcile checking-account ATM fees

Use this Skill when a customer asks to investigate ATM charges or possible missing ATM-fee rebates on Blue, Green, or Light Green checking accounts. It supports a review and, only where the documented prerequisites are affirmatively satisfied, preparation of a fee-refund credit. It does **not** apply a credit automatically.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this read-and-credit workflow, verify and record the applicable items: identity, authority, ownership, checking product and account status, current available balance as returned with the account, applicable fee schedule, ATM/fee transaction details, and whether the one-credit call and its cooldown permit a credit. Recipient and card details are not inputs to an account-credit call; document them as not applicable rather than inventing values. Confirm there is no additional confirmation requirement for the proposed credit before submitting it.

## Runtime inputs and tools

The workflow uses these internal tools documented for this task:

- `get_all_user_accounts_by_user_id_3847(user_id)` — retrieve bank account IDs, type, class, status, balance, and opening date.
- `get_bank_account_transactions_9173(account_id)` — retrieve all checking or savings transactions, newest first.
- `apply_checking_account_credit_5829(account_id, amount, credit_type)` — apply one positive checking-account credit of `rebate_credit` or `fee_refund`.

When these are exposed as discoverable agent tools, unlock each required tool first, then call it through the normal discoverable-agent-tool interface. Do not use unrelated credit-card tools for this checking-account request.

## Procedure

1. **Establish and log identity verification.** Obtain and compare at least two of date of birth, email, phone number, and address against the customer record. A name or email used solely to locate a record is not by itself proof that the caller controls the account. Once two fields are confirmed, get the current time and call `log_verification` with all returned customer-record fields and that timestamp. Confirm the caller has authority to request the review.

2. **Retrieve and validate accounts.** Retrieve all accounts using the verified `user_id`. Locate the accounts whose returned product/class identifies them as Blue, Green, or Light Green **checking** accounts. Record each account ID, type/class, status, and current balance. Do not assume that an account mentioned by the caller exists, belongs to them, is checking, or is eligible for a credit.

3. **Retrieve transaction history separately for every candidate checking account.** Call `get_bank_account_transactions_9173(account_id)`. The results are reverse chronological. Retain all requested-month transactions needed to establish the sequence of ATM withdrawals, including zero-fee withdrawals, plus their associated `atm_fee`, `fee_rebate`, `rebate_credit`, and `fee_refund` entries. Include posted and pending entries in the review, but do not treat pending fees as final or refund them.

4. **Map fee entries carefully.** For each cash withdrawal, record the withdrawal date, amount, description/location, status, and linked fee/credit transactions. Use descriptions and dates to establish a supportable linkage; do not pair a fee to a withdrawal merely because both occurred in the same month. Determine whether it was foreign (cash dispensed in foreign currency) or domestic out-of-network from the transaction evidence. A charge identified as an ATM-owner/operator/network surcharge is separate from the bank fee and must not be refunded under these schedules. If scope, fee source, amount, or linkage is unclear, mark the event unresolved and request clarification or escalate rather than guessing.

5. **Apply only the documented fee schedules.** Amounts below are in USD; for foreign activity use the settled USD-equivalent cash withdrawal amount.

   | Product | Foreign ATM withdrawal | Domestic out-of-network withdrawal |
   |---|---|---|
   | Blue | `max(3% × withdrawal, $5.00)` per withdrawal | `min(1% × withdrawal, $3.00)` |
   | Green checking | `max(3% × withdrawal, $5.00)` per withdrawal | `$3.00` per withdrawal |
   | Light Green | Per withdrawal: `<= $100: $2.00`; `> $100 and <= $300: $3.50`; `> $300: $5.00` | First four qualifying withdrawals in the calendar month: `$0.00`; each later withdrawal: `$1.50` |

   Foreign ATM fee rules are separate from ATM-operator charges. For Light Green, count **all** supported, qualifying domestic out-of-network withdrawals in chronological order for the month, including free ones. An exact $100 or $300 foreign withdrawal is in the lower tier. Do not infer in-network pricing or a foreign/domestic classification not supported by account activity.

6. **Account for already-applied offsets.** A fee may have a linked `fee_rebate`, `rebate_credit`, or `fee_refund`. Compare the expected bank fee with the net posted bank charge (bank fee minus linked posted offsetting credit), not just the gross fee line. The exact overcharge is `net posted bank charge − expected fee` when positive. A lower-than-expected charge is not a customer refund. Use `scripts/reconcile_atm_fees.py` for deterministic arithmetic and totals after creating a supported withdrawal-to-fee mapping.

7. **Decide whether a credit may be applied.** A credit is permissible only for a confirmed fee mischarge (or a documented missing eligible rebate), only to a checking account, only after reviewing the complete relevant history, and only at the exact net correction. Do not credit an account with unresolved or pending in-scope activity if that prevents a complete reconciliation. Before an action, affirm identity, authority, ownership, checking eligibility, exact transaction evidence, the current account balance, fee schedule, and that no previous credit has been made to the account in this interaction or is blocked by the 14-day cooldown.

8. **Apply at most one credit per account, if eligible.** If the account has one or more confirmed ATM fee overcharges and all prerequisites pass, combine all corrections into one positive `apply_checking_account_credit_5829` call with:
   - `account_id`: the verified checking account ID;
   - `amount`: the exact positive net total, with no estimate or rounding beyond cents;
   - `credit_type`: `fee_refund` for ATM-fee mischarges.

   The tool may be called only once per checking account in a customer interaction and enforces a 14-day cooldown. Do not split a correction into multiple calls. If both a missing rebate and fee refunds genuinely require one combined credit, total them and use the type applicable to the majority of corrections, as required by policy.

9. **Close clearly.** Explain each reviewed bank fee, separately identify nonrefundable operator charges, report any confirmed correction and the updated balance returned by the credit action, and state any unresolved evidence or pending activity. Never claim that a credit was applied unless the credit tool actually returned success.

## Calculator input and output

Run the packaged calculator through the Skill runtime:

```json
{
  "records": [
    {
      "account_id": "returned checking account ID",
      "product": "Blue",
      "account_type": "checking",
      "account_class": "returned class",
      "account_status": "returned status",
      "date": "MM/DD/YYYY",
      "order": 1,
      "withdrawal_amount": "100.00",
      "scope": "foreign",
      "fee_source": "bank",
      "bank_fee": "5.00",
      "fee_status": "posted",
      "offsetting_credits": [{"amount": "0.00", "status": "posted", "type": "fee_rebate"}],
      "withdrawal_transaction_id": "optional audit ID",
      "fee_transaction_id": "optional audit ID"
    }
  ],
  "prerequisites": {
    "identity_verified": true,
    "authority_verified": true,
    "account_ownership_verified": true,
    "available_balance_verified": true,
    "confirmation_requirements_checked": true,
    "credit_call_available": true
  }
}
```

`records` must cover every ATM withdrawal in the review period whose classification is needed, not merely charged fees. Valid products are `Blue`, `Green`, and `Light Green`; valid scopes are `foreign` and `domestic_out_of_network`; valid fee sources are `bank`, `operator`, and `unknown`. `order` is required for Light Green domestic out-of-network withdrawals and gives chronological order within a date. `bank_fee` is the linked bank fee, or `null` only when no fee posted. Only posted offsetting credits reduce the net charge.

The script emits JSON with event-level expected and net charges, account totals, unresolved conditions, and a non-actioning `credit_recommendation`. A non-null recommendation is still only a calculation result: the executor must perform the live prerequisite checks, make no more than one permitted tool call, and interpret the tool response.

Example runtime invocation (use actual retrieved records, never the illustrative values above):

```text
run_skill_script(relative_path="scripts/reconcile_atm_fees.py", input_json={"records": [...], "prerequisites": {...}})
```

Validate the output before any action: every in-scope withdrawal must appear once; Light Green domestic withdrawal order must be complete; bank and operator charges must be separated; all currency values must have two decimal places; all proposed totals must equal the sum of positive confirmed event overcharges; and each proposed account must be a verified checking account with no listed blocking reasons.

## Failure handling

- If two identity fields or authority cannot be confirmed, do not retrieve account activity or apply a credit.
- If account retrieval does not return a matching checking account, explain that no eligible matching account was found; do not substitute another account.
- If a fee is pending, has unknown source/scope, lacks a supportable withdrawal linkage, or lacks the complete Light Green monthly withdrawal sequence, do not make an exact correction from assumptions.
- If the request concerns an ATM operator fee, explain that it is separate from the bank fee schedule; do not refund it with the checking-credit tool.
- If the account is not checking, the cooldown/one-call condition fails, or a prerequisite is not satisfied, do not call the credit tool. Provide the completed review or route the unresolved issue through approved support procedures.
