---
name: atm-fee-and-rebate-review
version: 1.0.0
description: Review a verified customer's Bluest and Light Green checking-account ATM activity for a stated month, explain applicable ATM fee and rebate rules, identify exact supported corrections, and—only when all prerequisites are met—apply one consolidated checking-account credit per account.
---

# ATM Fee and Rebate Review

Use this Skill for a customer who asks to review ATM withdrawals, ATM fees, and ATM rebates on their Bluest Account and/or Light Green Account. It supports investigation and a permitted credit only for a missing eligible rebate or a documented fee mischarge. It does not file an ATM cash-discrepancy dispute, change account/card settings, or infer facts from incomplete transaction descriptions.

## Mandatory control and prerequisites

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this workflow, complete and document these checks before retrieving account activity or applying a credit:

1. Locate the customer record using the information supplied by the customer, but do not disclose confidential record values as part of the lookup.
2. Verify identity by having the customer confirm at least two of date of birth, email address, phone number, and address against the customer record. Obtain the current timestamp with `get_current_time` and call `log_verification` with all required stored fields and that timestamp.
3. Confirm the verified customer is authorized for, and owns, each returned account. Do not treat a matching name alone as proof of authority. If the account-return data does not establish authority/ownership, obtain the required confirmation or stop and route under the applicable operating procedure.
4. Confirm the account is an OPEN checking account with the requested product class. Credits are never permitted to savings or non-checking accounts.
5. Review the account balance and account activity, all relevant posted and pending transactions, the applicable product fees/benefits, the monthly cap or free-withdrawal allowance, existing rebates/refunds, the one-credit-per-interaction rule, and the 14-day cooldown before proposing a credit.
6. Confirm the calculated amount is exact, is positive, has not already been credited, and that the customer has been told what will be credited. Do not estimate, round, or credit pending charges.

If verification, ownership/authority, product classification, transaction linkage, or exact calculation cannot be established, explain the limitation and do not call a credit tool. A customer who declines identity verification cannot receive an account-specific review.

## Available banking tools

Unlock and use these discoverable internal tools only after the prerequisites above are met:

- `get_all_user_accounts_by_user_id_3847(user_id)` to obtain all customer accounts and their IDs, types, classes, statuses, balances, and opening dates.
- `get_bank_account_transactions_9173(account_id)` for each identified account. It returns all transactions newest first; retain transaction ID, date, description, amount, type, and status.
- `apply_checking_account_credit_5829(account_id, amount, credit_type)` only when this Skill's final credit gate permits it.

The tool results, not this Skill, establish account IDs, transactions, balance, and whether an account is present. Do not hardcode those values.

## Product rules used in the review

### Bluest Account

- Bluest provides rebates for qualifying third-party ATM fees up to **$50 per monthly statement cycle**. Rebates cease once the cap is reached.
- Bluest's stated out-of-network ATM withdrawal fee is **$2.00 per withdrawal**. ATM-operator surcharges are separate from that bank fee.
- Foreign Rho-Bank ATM withdrawal fees are $0, though an operator may impose a separate third-party fee.
- Treat only a positively identified, posted third-party ATM fee as rebate eligible. Do not call an ambiguous fee a third-party fee merely because its description contains “ATM.”

### Light Green Account

- Light Green has **four free out-of-network ATM withdrawals per month**. Thereafter, the stated out-of-network ATM withdrawal fee is **$1.50 per withdrawal**.
- Its foreign ATM bank fee is tiered per single withdrawal: $2.00 through $100, $3.50 over $100 through $300, and $5.00 over $300. These fees are distinct from operator fees.
- Do not apply the four-free-withdrawal rule to a foreign fee or an operator surcharge. A posted, identified domestic out-of-network bank fee on one of the first four qualifying withdrawals is a fee-mischarge candidate; after the fourth, compare the actual bank fee exactly with $1.50.

## Procedure

1. **Establish the review period.** Ask which statement month the customer wants reviewed when not clear. Use the current time for context; do not silently treat a partial current month as a completed statement cycle. Explain that pending entries are reviewed but not corrected until posted.
2. **Identify and validate accounts.** Retrieve accounts for the verified user and select only accounts whose returned account class identifies Bluest or Light Green, whose type is checking, and whose status is OPEN. If either requested product is absent, say so without substituting another account.
3. **Retrieve complete history.** Retrieve transaction history separately for every selected account. Preserve both posted and pending records. Filter the requested review month using transaction dates in `MM/DD/YYYY` form.
4. **Classify and link each ATM fee.** For every ATM fee line in the month, identify its related withdrawal and determine from the description/available records whether it is a third-party fee, Bluest bank out-of-network fee, Light Green domestic out-of-network bank fee, foreign bank fee, operator surcharge, or unknown. Record why the classification is supported. Do not make a credit recommendation while a posted ATM-fee line remains unlinked or unknown.
5. **Account for credits already received.** Find posted `fee_rebate`, `rebate_credit`, and `fee_refund` records. Match them to the review period and underlying fee where possible. Never issue a duplicate credit.
6. **Calculate conservatively.** Run `scripts/assess_atm_fees.py` with normalized tool data and explicit fee links. The script validates dates and amounts, lists unresolved fee lines, calculates supported Bluest rebate shortfalls and Light Green fee discrepancies, checks visible 14-day cooldown evidence, and produces a proposed single credit only when the supplied review is complete.
7. **Perform a credit only if permitted.** For each eligible account, the credit tool can be called only once during this customer interaction, and a previous `rebate_credit` or `fee_refund` within 14 days prevents another call. Combine all supported corrections for that account into one exact positive amount. Use:
   - `rebate_credit` for a missing qualifying rebate;
   - `fee_refund` for an incorrectly charged fee;
   - when both are combined, use the type that applies to the majority of discrete corrections. If there is a tie, do not guess; resolve under the applicable approval procedure before calling the tool.

   Call `apply_checking_account_credit_5829` exactly once for that account with the script-approved amount and type. A script recommendation does not execute a banking action. If the tool rejects the request or shows a cooldown, do not retry or split the amount.
8. **Close the interaction.** Explain the reviewed transactions, the product rule, any posted credit and tool-reported resulting balance, and any remaining pending/unresolved items. If no correction is due, clearly explain why. Do not claim a credit was applied unless the credit tool confirms it.

## Analyzer script

`scripts/assess_atm_fees.py` reads one JSON object from stdin and emits one JSON object to stdout. It uses only supplied data and never invokes banking tools.

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

`withdrawal_order` is required for every Light Green domestic out-of-network fee link and must be the chronological order of that qualifying withdrawal in the review month. `confirmed_fee_refund_amount` is only for a documented exact discrepancy that the agent established from policy and transaction records; it is not a guess. The analyzer never derives fee kind or linkage from free text.

A minimal structural call, useful for checking integration, is a JSON input with a valid `review_month`, `as_of_date`, and empty `accounts`/`fee_links`; it will return a valid empty assessment. In production, pass complete account and transaction data retrieved during the verified review.

### Output interpretation

The output contains per-account `unlinked_posted_atm_fee_ids`, `pending_atm_fee_ids`, `warnings`, calculation fields, cooldown evidence, and a `credit_plan`. Only a plan with `permitted: true` may be used to prepare a credit-tool call. `permitted: false` means the agent must resolve the named issue or refrain from crediting. The output amounts are decimal strings and must be sent as the exact positive monetary amount.

## Failure handling

- If no user record, requested account, or matching transaction is found, state that no account-specific conclusion can be made; do not fabricate activity.
- If an ATM fee description cannot identify whether it is a bank fee, operator fee, or foreign fee, request the statement detail or follow the approved investigation process rather than applying a credit.
- If the transaction is pending, disclose it as pending and wait for posting before a correction.
- If the rebate cap has already been met, no additional Bluest rebate is due for that cycle.
- If the account is closed, non-checking, unauthorized, in cooldown, or has already received a credit during the interaction, do not apply a credit.
- If a customer asserts an ATM cash discrepancy rather than a fee/rebate issue, use the separate ATM-dispute process; do not turn it into a fee credit.
