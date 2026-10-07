---
name: atm-fee-and-rebate-review
version: 1.2.0
description: Review a verified customer's Bluest and Light Green checking-account ATM activity for a requested month, including an in-progress current month when no year is supplied; reconcile posted ATM fees, rebates, and credits, and apply at most one exact permitted correction per account.
---

# ATM Fee and Rebate Review

Use this Skill when a customer asks to review ATM withdrawals, ATM fees, fee rebates, or apparent ATM overcharges on a Bluest Account and/or Light Green Account. It is for fee and rebate review, not an ATM cash-dispense dispute, a card change, or a profile change.

## Mandatory control and prerequisites

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this review and any possible correction:

1. Locate the customer record without disclosing unnecessary confidential data.
2. Verify identity by matching at least two of date of birth, email address, phone number, and address against the customer record. Obtain the current timestamp with `get_current_time`, then call `log_verification` with all required fields from the verified record and that timestamp.
3. Do not retrieve account records until the verification is successfully logged.
4. Confirm the requested accounts belong to the verified customer and are OPEN checking accounts before giving account-specific findings or considering a credit.
5. Review all relevant posted and pending activity before deciding whether a correction is owed. A pending item may be explained but must not be credited.
6. Before a credit, calculate every confirmed eligible correction for that account, verify the exact positive total was not already credited, check for an existing credit in this interaction and the 14-day cooldown, and make only one credit call for that account.

If verification fails, ownership is not established, or an account is absent, closed, or non-checking, do not provide an account-specific conclusion or credit.

## Operational sequence

1. **Choose the review period.** If a month is named without a year, obtain the current time and use its year as the provisional context. If the chosen month is the current month, review activity through the current-date cutoff and explain that it is in progress, not a completed statement cycle. Do not stop merely because the customer did not provide a statement year.
2. **Verify and log first.** Match two identity factors and successfully call `log_verification` before account or history access.
3. **Retrieve accounts.** Unlock `get_all_user_accounts_by_user_id_3847`, then invoke it through `call_discoverable_agent_tool` with the verified `user_id`. Identify each requested account from returned `account_class`, `account_type`, and `status`; retain its returned account ID, class, status, balance, and opening date. Do not require account last-four digits as a substitute for this available lookup.
4. **Retrieve both histories.** Unlock `get_bank_account_transactions_9173`, then invoke it through `call_discoverable_agent_tool` once for each identified requested checking `account_id`. The results are reverse chronological and include transaction ID, date, description, amount, type, and posted/pending status.
5. **Reconcile all in-scope ATM activity.** For each account, review `atm_withdrawal`, `atm_fee`, `fee_rebate`, `rebate_credit`, and `fee_refund` records through the cutoff. Match fees to withdrawals using dates, descriptions, amounts, ATM/location data, and transaction IDs where available. Retain enough surrounding records to detect already-posted rebates and credits.
6. **Complete the correction calculation before acting.** Use the product rules and the complete, posted history. Do not issue a partial credit and then attempt another credit: the credit tool is permitted only once per checking account per interaction.
7. **Explain and, if permitted, correct.** Explain the supporting transaction dates, descriptions, amounts, and statuses. Use the credit tool only after the credit gate below is satisfied. State a credit or new balance only if the tool result confirms it.

## Discoverable-tool use

These specialized tools must be unlocked before use and invoked via the observable wrapper:

- `get_all_user_accounts_by_user_id_3847(user_id)`
- `get_bank_account_transactions_9173(account_id)`
- `apply_checking_account_credit_5829(account_id, amount, credit_type)`

For each invocation, call `call_discoverable_agent_tool` with `agent_tool_name` set to the unlocked tool name and `arguments` containing the tool arguments as JSON text. The credit tool is state-changing; it belongs only at the final credit gate.

Do not hardcode account IDs, transaction IDs, balances, dates, or correction amounts. Derive them from the current verified account and history results.

## Product reconciliation rules

### Bluest Account

- A domestic out-of-network withdrawal has a separately posted Rho-Bank fee of $2.00 per withdrawal.
- Qualifying third-party ATM fees are rebated up to $50 per monthly statement cycle. Sum qualifying posted third-party fees and subtract matching posted `fee_rebate` or `rebate_credit` entries; no rebate is due above the cap.
- Rho-Bank's fee for a foreign ATM withdrawal is $0.00. A third-party operator surcharge can still be valid, but it is distinct from a Rho-Bank fee.
- Treat a separately posted `atm_fee` whose transaction evidence explicitly identifies it as a **FOREIGN ATM FEE** as a Rho-Bank foreign-fee charge unless the transaction evidence instead specifically establishes it as a third-party operator surcharge. Do not relabel an explicit foreign-fee line as an operator charge merely to avoid the $0 foreign Rho-Bank fee rule. A posted Rho-Bank foreign fee is a fee mischarge and its full charged amount is refundable.
- Keep separately posted Rho-Bank fees, qualifying third-party charges, and supported operator surcharges separate in the explanation and calculation. A vague description alone is not sufficient to invent an operator surcharge classification.

### Light Green Account

- The first four qualifying domestic out-of-network ATM withdrawals in a month are free. Each later qualifying domestic out-of-network withdrawal has a Rho-Bank fee of $1.50.
- Foreign Rho-Bank fees are charged per withdrawal: $2.00 for a withdrawal up to and including $100, $3.50 above $100 through $300, and $5.00 above $300.
- Operator charges are separate. Do not apply the domestic four-free-withdrawal allowance to a foreign fee or an operator surcharge.
- A posted domestic Rho-Bank fee on one of the first four qualifying withdrawals, or a posted amount over $1.50 afterwards, is refundable only when linkage and the exact discrepancy are established. A foreign fee is refundable only to the extent it differs from the applicable tier.

## Credit gate

A credit is allowed only for a missing eligible rebate or a documented fee mischarge. Before unlocking and invoking `apply_checking_account_credit_5829`, confirm all of the following:

- identity, authority, account ownership, OPEN checking status, product eligibility, applicable fees, limits, cutoff, balance/credit considerations, and confirmation requirements;
- complete reconciliation of every relevant posted ATM-fee line, related withdrawal, rebate, and prior credit in the selected period;
- an exact positive net correction, with no pending item included and no matching correction already posted;
- no previous credit call for that account in this interaction and no visible posted `rebate_credit` or `fee_refund` within the prior 14 days;
- all documented fee mischarges and missing rebates for the account have been consolidated before the sole credit call.

Call the credit tool with a positive exact amount. Use `rebate_credit` for a correction consisting predominantly of missing rebates and `fee_refund` for one consisting predominantly of fee mischarges. When both occur, select the type corresponding to the majority of discrete corrections. If they are tied or classification remains unresolved, do not guess or split the credit; obtain approved resolution instead.

If the tool rejects the request, reports cooldown, or fails, do not retry or divide the amount. Never claim that a credit was made unless the tool confirms it.

## Analyzer script

`scripts/assess_atm_fees.py` deterministically evaluates normalized retrieved records. It reads one JSON object from stdin and writes one JSON object to stdout. It makes no tool calls and does not itself apply a credit.

Use it after retrieving complete histories and explicitly matching fee records to withdrawals. Its output is a recommendation; the executor must still independently complete the credit gate.

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
      "withdrawal_order": 1
    }
  ]
}
```

`withdrawal_order` is required for each Light Green domestic out-of-network fee link and is the chronological number of the qualifying withdrawal in the review month. Set `fee_kind` only from transaction evidence. In particular, use `foreign_atm_bank_fee` for an explicit foreign Rho-Bank fee line, not for an established operator surcharge. The script rejects a credit plan when a posted ATM fee is unlinked, malformed, or unresolved.

The output includes linked/unlinked and pending fee IDs, rebate and refund components, warnings, cooldown evidence, and a per-account `credit_plan`. Only a `credit_plan` with `permitted: true` can support preparing a credit-tool call.

## Failure handling

- If account lookup or either history lookup fails, explain that the review cannot be completed and do not fabricate activity.
- If one requested product is absent, report it unavailable and review the other only if it is verified, owned, OPEN, and checking.
- If a posted ATM fee cannot be linked or classified, do not credit it; request needed statement detail or use the approved investigation process.
- If an entry is pending, disclose that it will require posting before correction.
- If the issue is no cash or the wrong amount of cash dispensed, use the separate ATM-dispute procedure, not a fee/rebate credit.
