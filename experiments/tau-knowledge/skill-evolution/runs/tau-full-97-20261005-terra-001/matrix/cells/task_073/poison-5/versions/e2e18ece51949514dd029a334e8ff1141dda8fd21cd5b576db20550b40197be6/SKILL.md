---
name: reconcile-and-correct-checking-atm-fees
description: Verify a customer's ownership of Blue, Green, and Light Green checking accounts; review ATM withdrawals and fees for a requested period; calculate documented bank-fee mischarges including erroneous out-of-network fees at a Rho-Bank ATM; and apply one exact fee-refund credit per eligible checking account.
---

# Reconcile and correct checking-account ATM fees

Use this Skill when a customer asks Rho-Bank to investigate ATM fees, unexpected ATM charges, or missing ATM-fee benefits on Blue, Green, or Light Green checking accounts.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this workflow, record: verified identity; authority; ownership; returned account type, class, status, and balance; applicable fee rules; relevant withdrawal and fee details; whether a prior credit was made in this interaction; the 14-day cooldown status; and confirmation requirements. Recipient and card details do not apply to a checking-account credit; record them as not applicable. A credit increases the account balance and does not require a debit-side available-balance check, but the returned current balance must still be reviewed and recorded.

## Runtime tools

Use only these documented banking tools through the normal discoverable-agent-tool workflow. Unlock a tool before calling it.

- `get_all_user_accounts_by_user_id_3847(user_id)` retrieves the customer's accounts.
- `get_bank_account_transactions_9173(account_id)` retrieves all account transactions, newest first.
- `apply_checking_account_credit_5829(account_id, amount, credit_type)` applies an eligible checking-account credit.

Use `get_current_time` and `log_verification` after confirming two identity fields against the customer record. Do not use credit-card tools for this checking-account request.

## Required procedure

1. **Verify the caller before account access or action.** Locate the customer record using supplied identifying information, then have the caller affirmatively confirm at least two of date of birth, email address, phone number, or street address against that record. Confirm authority to request the review. Obtain the current time and log the verification using every returned customer-record field. A name or email used only to find a record is not itself sufficient verification.

2. **Retrieve all accounts.** Call `get_all_user_accounts_by_user_id_3847` with the verified user ID. Select only returned Blue, Green, and Light Green accounts that are checking accounts, belong to the verified customer, and have an eligible status. Record the account IDs, product/class, status, and balance. Do not infer an account ID, product, ownership, or checking eligibility.

3. **Retrieve every selected account history.** Call `get_bank_account_transactions_9173` once for each selected account. Review all requested-period ATM withdrawals, ATM fees, fee rebates, rebate credits, and fee refunds. Since histories are reverse chronological, reorder relevant withdrawals chronologically before applying monthly Light Green counting rules. Include zero-fee withdrawals when they affect the Light Green free-withdrawal count.

4. **Build evidence-based withdrawal/fee mappings.** For each relevant ATM withdrawal, retain its transaction ID, date, amount, description, status, currency/location evidence, and each associated fee or offset. Match fees using transaction identifiers, a clear description, or an evidenced transaction sequence. Do not associate a fee with a withdrawal solely because both have the same date.

   Treat a fee specifically identified as an ATM owner/operator surcharge as an operator charge, not a refundable Rho-Bank fee. Conversely, a line identified as the bank's own non-Rho, non-network, or out-of-network ATM fee is a bank fee, not an operator surcharge merely because it references a network. If a withdrawal description identifies a **Rho-Bank ATM**, classify the domestic withdrawal as `domestic_in_network`: the documented domestic out-of-network fee does not apply, so an associated posted bank non-Rho/out-of-network fee is a confirmed mischarge with expected bank fee `$0.00`.

5. **Apply the documented schedules only.** Use settled USD-equivalent withdrawal amounts for foreign transactions.

   | Product | Foreign withdrawal bank fee | Domestic out-of-network bank fee | Domestic in-network bank fee |
   |---|---:|---:|---:|
   | Blue | `max(3% × withdrawal, $5.00)` | `min(1% × withdrawal, $3.00)` | `$0.00` |
   | Green checking | `max(3% × withdrawal, $5.00)` | `$3.00` | `$0.00` |
   | Light Green | `<= $100: $2.00`; `> $100 and <= $300: $3.50`; `> $300: $5.00` | First four qualifying withdrawals in the calendar month: `$0.00`; later withdrawals: `$1.50` | `$0.00` |

   Foreign-fee rules and ATM-operator surcharges are separate. For Light Green, count every supported qualifying domestic out-of-network withdrawal in the calendar month in chronological order, including the first four free withdrawals. An amount exactly `$100` or `$300` uses the lower foreign-fee tier.

6. **Calculate each confirmed correction.** For each posted, mapped bank fee, subtract only posted, mapped `fee_rebate`, `rebate_credit`, or `fee_refund` offsets from the gross bank fee. The event correction is `max(net posted bank charge − expected bank fee, 0)`. A duplicate bank fee for one evidenced withdrawal is an excess fee. Use `scripts/reconcile_atm_fees.py` for deterministic arithmetic after supplying the established mappings.

   An unknown, pending, unsupported, or operator fee must be marked unresolved or excluded and must not be estimated. However, such an independent item does **not** justify withholding a separately evidenced, exact correction on the same account. Apply all confirmed posted account-level corrections first; explain and, if needed, escalate only the remaining unresolved items afterward.

7. **Make required fee-refund credits.** For each eligible checking account with a positive confirmed total, recheck identity, authority, ownership, account status, current balance, exact amount, fee schedule, one-credit-per-account rule, 14-day cooldown, and confirmation requirements. Then make exactly one call:

   `apply_checking_account_credit_5829(account_id, amount, "fee_refund")`

   The amount must be the exact positive net total of all confirmed fee mischarges for that account. Combine all confirmed fee corrections into that one call; never split them. Do not apply credits to savings or other non-checking accounts. If the tool returns an error or does not explicitly confirm success, do not claim a credit was applied.

8. **Close accurately.** For every successful credit, state that it was applied, give the amount, summarize the confirmed fee corrections, and provide the updated balance if returned by the tool. Clearly distinguish successful credits from excluded operator charges, pending items, and any unresolved items being referred for additional review.

## Calculator interface

`scripts/reconcile_atm_fees.py` reads one JSON object from standard input and writes one JSON object to standard output. It makes no banking calls and cannot apply a credit.

Input schema:

```json
{
  "records": [
    {
      "account_id": "returned checking account ID",
      "product": "Blue|Green|Light Green",
      "account_type": "checking",
      "account_status": "returned status",
      "date": "MM/DD/YYYY",
      "order": 1,
      "withdrawal_amount": "absolute positive amount",
      "scope": "foreign|domestic_out_of_network|domestic_in_network",
      "fee_source": "bank|operator|unknown",
      "bank_fee": "absolute amount or null when no bank fee posted",
      "fee_status": "posted|pending",
      "offsetting_credits": [
        {"amount": "absolute positive amount", "status": "posted|pending", "type": "fee_rebate|rebate_credit|fee_refund"}
      ],
      "withdrawal_transaction_id": "audit identifier",
      "fee_transaction_id": "audit identifier"
    }
  ],
  "prerequisites": {
    "identity_verified": true,
    "authority_verified": true,
    "account_ownership_verified": true,
    "checking_eligibility_verified": true,
    "balance_reviewed": true,
    "confirmation_requirements_checked": true,
    "one_credit_rule_and_cooldown_verified": true
  }
}
```

`order` is required for Light Green domestic out-of-network records and orders same-day events chronologically. The records must include all qualifying Light Green domestic out-of-network withdrawals for the reviewed calendar month. The executor, not the script, establishes mapping evidence and scope from transaction history.

Example invocation with actual retrieved records:

```text
run_skill_script(relative_path="scripts/reconcile_atm_fees.py", input_json={"records": [...], "prerequisites": {...}})
```

Before crediting, validate that each supported withdrawal appears once, mapped bank fees and offsets are traceable, operator fees are excluded, Light Green counting is complete, every total is the sum of positive event corrections, and each recommended account has an eligible checking status with every live prerequisite affirmed.

## Failure handling

- If identity or authority cannot be verified, do not retrieve activity or credit an account.
- If an account is absent, non-checking, ineligible, already credited in this interaction, or under the cooldown, do not call the credit tool for it.
- If a fee is pending, its source is unknown, or the evidence does not support its linkage or classification, do not estimate a correction for that item.
- Do not refund a documented operator surcharge with the checking-account credit tool.
- A failed credit-tool response means no applied credit; explain the result and use approved support escalation where appropriate.
- Do not defer an exact, independently confirmed posted fee correction because another event is unresolved.
