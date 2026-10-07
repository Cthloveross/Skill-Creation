---
name: atm-fee-and-rebate-review
version: 1.1.0
description: Review a verified customer's Bluest and Light Green checking-account ATM activity for a requested month, including current in-progress November activity when no year is supplied; explain supported fee and rebate results and apply an exact, permitted correction only when documented prerequisites are met.
---

# ATM Fee and Rebate Review

Use this Skill when a customer asks to review ATM withdrawals, ATM fees, fee rebates, or apparent ATM overcharges on a Bluest Account and/or Light Green Account. It is for a fee-and-rebate review, not an ATM cash-dispense dispute, card change, or profile change.

## Mandatory control and prerequisites

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this read-only review and any potential credit:

1. Locate the customer record without exposing confidential record data unnecessarily.
2. Verify identity by matching at least two of date of birth, email address, phone number, and address to the customer record. Obtain the current timestamp using `get_current_time`, then record the successful verification with `log_verification` using the complete required customer-record fields and timestamp.
3. Only after the recorded verification, retrieve the verified customer's account list. Use the returned account relationship, type, class, and status to confirm the requested accounts are the customer's accounts and are OPEN checking accounts before reviewing account-specific results or considering a credit.
4. Retrieve the history for **each** identified requested checking account. Review both posted and pending activity, account balance, applicable fees and benefits, prior rebates/refunds, and relevant cooldown evidence.
5. Before any credit, establish an exact positive amount, confirm that it was not already credited, confirm the account is an OPEN checking account, confirm the account has not already received a credit in this interaction, and disclose the proposed correction. Do not estimate, round, or correct a pending charge.

If identity verification fails or the requested account is absent, closed, non-checking, or not shown as belonging to the verified customer, do not provide an account-specific conclusion or credit. Do not use uncertainty about the statement year as a reason to skip the verified customer's account and transaction-history retrieval.

## Required operational sequence

1. **Set the review period.** If the customer names a month but not a year, use the current year from `get_current_time` as the provisional review context. For example, when the current date is in November 2025, review November 2025. State that it is an in-progress period rather than a completed statement cycle. Review pending entries, but do not issue a correction for them. If the customer later identifies another statement year, repeat the review for that period.
2. **Record verification first.** Do not access bank-account records before a successful `log_verification` call.
3. **Retrieve the account list.** Unlock `get_all_user_accounts_by_user_id_3847`, then call it with the verified `user_id`. Select the accounts whose returned account class is Bluest Account or Light Green Account, account type is checking, and status is OPEN. Record their returned account IDs, classes, statuses, balances, and opening dates. Do not request account last-four digits merely to avoid this lookup.
4. **Retrieve both histories.** Unlock `get_bank_account_transactions_9173` and call it once for the returned Bluest checking `account_id` and once for the returned Light Green checking `account_id`. The history is newest first and contains transaction ID, account ID, date, description, amount, type, and posted/pending status. Retain all records needed to evaluate the chosen month, including related withdrawals that may be near a month boundary.
5. **Review and reconcile.** For each account, identify ATM withdrawals, `atm_fee` entries, `fee_rebate`, `rebate_credit`, and `fee_refund` entries. Match a fee to its related withdrawal using available dates, descriptions, amounts, and transaction records; distinguish a Rho-Bank fee, third-party operator charge, foreign ATM fee, and an unknown item. Do not invent a classification from a vague description.
6. **Explain the supported finding.** State the dates, descriptions, amounts, and posted/pending status that support the conclusion. If activity is incomplete or ambiguous, explain the limitation and request the needed statement detail or use the applicable approved investigation process.
7. **Consider a credit only after the complete review.** Use `scripts/assess_atm_fees.py` to make a conservative calculation from normalized retrieved data and explicit fee links. A script result is a recommendation, not a banking action. Unlock and call `apply_checking_account_credit_5829` only for a `credit_plan` marked `permitted: true` after all non-script prerequisites are independently confirmed.

## Tool use

The account and history tools are discoverable internal tools. Unlock a named tool with `unlock_discoverable_agent_tool`, then invoke it with `call_discoverable_agent_tool` and its JSON arguments.

- `get_all_user_accounts_by_user_id_3847(user_id)` returns bank account IDs, types, classes, statuses, balances, and opening dates.
- `get_bank_account_transactions_9173(account_id)` returns all account transactions.
- `apply_checking_account_credit_5829(account_id, amount, credit_type)` is a state-changing tool and is allowed only at the final credit gate below.

Never hardcode account IDs, transaction IDs, balances, dates, or an expected result. The returned tool data determines the accounts and findings.

## Product rules

### Bluest Account

- An out-of-network ATM withdrawal has a Rho-Bank fee of **$2.00 per withdrawal**; it normally posts as a separate account-activity line.
- Qualifying third-party ATM fees are rebated up to **$50 per monthly statement cycle**. Rebates stop after the $50 cap.
- Foreign Rho-Bank ATM withdrawal fees are $0.00. A third-party ATM operator can still impose a separate charge.
- Keep the $2.00 Rho-Bank fee, any operator surcharge, and a third-party-fee rebate distinct. A missing rebate is eligible only when the posted fee is positively established as a qualifying third-party fee, the cap calculation supports it, and no matching rebate has already posted.

### Light Green Account

- The first **four** qualifying out-of-network ATM withdrawals in a month are free. Each qualifying domestic out-of-network withdrawal after that has a Rho-Bank fee of **$1.50**.
- Foreign Rho-Bank ATM fees are per withdrawal: $2.00 up to and including $100, $3.50 above $100 through $300, and $5.00 above $300.
- Operator charges are separate from Rho-Bank fees. Do not apply the four-free-withdrawal rule to a foreign fee or an operator surcharge.
- A posted domestic out-of-network Rho-Bank fee on one of the first four qualifying withdrawals, or a posted fee after the allowance that exceeds $1.50, is a possible fee-mischarge correction only if the transaction linkage and exact discrepancy are documented.

## Credit gate

Credits are permitted only for (1) a missing eligible rebate or (2) a documented fee mischarge. Before calling the credit tool, confirm all of the following:

- identity, authority, account ownership, checking status, OPEN status, eligibility, balance, fees, limits, and confirmation requirements;
- complete review of relevant posted and pending account activity and matching of every posted ATM-fee line in the period;
- the exact eligible missing rebate or net fee discrepancy and that it has not already been credited;
- no prior credit call for that account in this interaction and no visible `rebate_credit` or `fee_refund` in the prior 14 days;
- a positive exact amount, with no pending item included.

Only one credit call is allowed per checking account in a customer interaction. Combine all supported corrections for that account into that single exact amount. Use `rebate_credit` for a missing rebate and `fee_refund` for a fee mischarge. If both are combined, use the type representing the majority of discrete corrections; if tied, do not guess or call the credit tool without approved resolution. If the credit tool rejects a request or reports cooldown, do not retry or split the amount.

After a successful credit tool result, state the tool-confirmed credit and resulting balance. Never claim a credit was applied unless the tool confirms it.

## Analyzer script

`scripts/assess_atm_fees.py` reads one JSON object from stdin and writes one JSON object to stdout. It performs no tool calls and does not itself apply a credit.

### Input schema

```json
{
  "review_month": "YYYY-MM",
  "as_of_date": "YYYY-MM-DD",
  "credit_already_applied_this_interaction": false,
  "accounts": [
    {
      "account_id": "string",
      "account_type": "checking",
      "account_class": "Bluest Account or Light Green Account",
      "status": "open",
      "balance": "decimal string or number",
      "transactions": [
        {
          "transaction_id": "string",
          "date": "MM/DD/YYYY",
          "description": "string",
          "amount": "decimal string or number",
          "type": "atm_withdrawal|atm_fee|fee_rebate|rebate_credit|fee_refund|...",
          "status": "posted|pending"
        }
      ]
    }
  ],
  "fee_links": [
    {
      "account_id": "string",
      "fee_transaction_id": "string",
      "withdrawal_transaction_id": "string",
      "fee_kind": "third_party_atm_fee|bluest_out_of_network_bank_fee|light_green_out_of_network_bank_fee|foreign_atm_bank_fee|operator_surcharge",
      "withdrawal_order": 1,
      "confirmed_fee_refund_amount": "optional exact decimal"
    }
  ]
}
```

`withdrawal_order` is required for each Light Green domestic out-of-network fee link and is the chronological order of the qualifying withdrawal in the review month. `confirmed_fee_refund_amount` may be supplied only for an independently documented, exact fee discrepancy. The script deliberately does not infer linkages or fee classifications from descriptions.

A valid structural invocation may contain a valid month/date and empty `accounts` and `fee_links`; production input must contain the retrieved account and transaction data. Output includes per-account unresolved and pending fee IDs, warning messages, rebate and refund calculations, cooldown evidence, and a `credit_plan`. Only `credit_plan.permitted: true` can support preparation of a credit-tool call.

## Failure handling

- If the account lookup or either history lookup fails, report that the review could not be completed; do not fabricate activity.
- If one requested product is not returned, report that product as unavailable and still review the other identified requested checking account.
- If a posted ATM fee cannot be linked or classified, do not credit it. Ask for statement detail or follow the approved investigation path.
- If an item is pending, disclose its status and wait for posting before correcting it.
- If the Bluest cap is reached, no additional rebate is due for that cycle.
- If the concern is that cash was not dispensed or the wrong cash amount was dispensed, use the separate ATM-dispute procedure rather than a fee/rebate credit.
