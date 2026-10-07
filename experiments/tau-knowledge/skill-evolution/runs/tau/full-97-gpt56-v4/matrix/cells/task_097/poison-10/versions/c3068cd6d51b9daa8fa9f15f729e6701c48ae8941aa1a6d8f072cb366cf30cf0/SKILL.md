---
name: savings-interest-discrepancy-correction
description: Investigate a verified customer's potentially incorrect savings interest credit, calculate a supportable correction from account and statement-period data, apply an authorized savings interest-correction credit, and file the required backend discrepancy report. Use for Silver, Silver Plus, Platinum, Diamond Elite, or similarly documented savings-interest discrepancies; do not use it for estimates unsupported by account records.
---

# Savings Interest Discrepancy Correction

Use this Skill when a customer says that a posted monthly savings-interest credit is wrong. It is designed for one or more savings accounts, but each account and statement period must be investigated and corrected independently.

## Mandatory banking prerequisites

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For this workflow, complete and retain the following checks before a credit:

1. Confirm identity using two of the four recorded fields (date of birth, email, phone number, address) and call `log_verification` with the complete retrieved record and a current timestamp.
2. Confirm the requester is authorized for the identified customer profile.
3. Retrieve all accounts with `get_all_user_accounts_by_user_id_3847`; confirm that each target is an active savings account owned by that user.
4. Retrieve the target account's transactions with `get_bank_account_transactions_9173`. Locate the relevant **posted** `interest_credit`, its amount, and the relevant statement period. Do not treat a pending entry as the final interest credit.
5. Establish daily balances (or another documented equivalent) for the exact statement period. Do not calculate a correction from approximate balances, an undated customer estimate, or a current balance alone.
6. Verify every APY component against the applicable product documentation and the customer's active products. Apply only the highest eligible credit-card bonus and only the highest eligible linked-checking boost; those two selected bonuses may stack with other eligible components.

If the named internal account or transaction tools are not immediately callable, unlock the documented agent tool first using `unlock_discoverable_agent_tool`, then use `call_discoverable_agent_tool` with the documented tool name and JSON arguments. Use normal banking tools for all account changes; this package never executes a bank action itself.

## Investigation method

1. Obtain the customer identifier and authenticate the user. If the customer cannot identify a statement period, retrieve the account list and recent transaction history after identity verification rather than guessing.
2. Inventory active savings accounts, checking accounts, and credit cards on the same profile. For the affected savings product, determine:
   - base APY and balance tier applicable on each day;
   - any qualifying direct-deposit, relationship, checking-link, and card components;
   - the selected highest card bonus and selected highest checking boost;
   - the actual credited interest and the actual APY, if the system exposes it.
3. Preserve the relevant statement dates, daily balances, posted interest transaction, applicable rules, and calculation. Use `scripts/interest_analysis.py` to calculate a reproducible daily-balance result and to validate whether a positive discrepancy exists.
4. If the expected amount is no greater than the posted amount after normal currency rounding, do not apply a credit or submit a report. Explain the calculation to the customer.
5. For each verified positive discrepancy, call:
   - `apply_savings_account_credit_6831` with the target `account_id`, the positive cents-rounded difference, and `credit_type: "interest_correction"`.
   - Only after the credit succeeds, call `submit_interest_discrepancy_report_7294` with `account_id`, `user_id`, the verified expected and actual APY percentages, and the same positive amount difference.
6. Record the action result. Tell the customer which account and statement period were corrected, the amount, and the new balance returned by the credit tool. Do not claim a new balance if the tool does not return one.

The report is required for an interest correction and must be submitted **after**, never before, the account credit. A report is not a substitute for an eligible credit.

## APY evidence and calculation safeguards

Read the product documentation applicable to the account actually returned by the account lookup. The bundled `references/apy_rules.md` summarizes the supplied product rules, but it does not replace a missing eligibility fact.

- Determine tier day by day when the product documentation says APY changes with balance tier.
- A customer holding several cards receives the highest applicable card APY bonus, not their sum.
- A customer holding several qualifying checking accounts receives the highest applicable checking boost, not their sum.
- Checking and card selections can stack with documented relationship, direct-deposit, and tier components.
- Do not assign a boost where the pairing or its percentage is not documented. Escalate for an unsupported or conflicting product rule rather than inventing a rate.
- Actual APY in the discrepancy report should be the documented/system-applied actual rate. If unavailable, the helper can provide an inferred rate from the posted credit and daily balances; label it as inferred in investigation notes and use it only where that approximation is permitted by the available account records.

## Missing information and customer help

Do not issue a credit if account ownership, the savings product, the posted interest credit, the statement period, daily balances, or an applicable APY component cannot be verified. Ask for only the next needed item, or retrieve it through authorized banking tools after verification.

When a customer asks how to find the information manually, direct them to sign in through the normal secure banking app or website, open the named savings account, and review its recent transactions and monthly statements for the `interest_credit` entry, posting date, statement start/end dates, and daily-balance detail if shown. Do not request credentials, PINs, passwords, or full sensitive account numbers in chat.

If a required tool is unavailable due to a system failure, use the human-transfer process with `technical_system_error` and summarize the verified identity state, accounts affected, investigation attempted, and missing system capability. Do not transfer merely because the customer lacks account numbers when authorized account lookup is available.

## Calculation helper

`scripts/interest_analysis.py` reads one JSON object from stdin and emits one JSON object to stdout. It performs no bank operations.

Input schema:

```json
{
  "account_id": "string",
  "expected_apy_percent": 6.5,
  "actual_credit_amount": "379.00",
  "daily_balances": [
    {"date": "YYYY-MM-DD", "balance": "75000.00"}
  ],
  "actual_apy_percent": null
}
```

`daily_balances` must contain one nonnegative end-of-day balance for every calendar day in the statement period, in chronological order, with no duplicate dates. Supply `actual_apy_percent` when verified from account records; otherwise use `null` to request an inferred APY. The output includes expected interest, posted interest, positive correction amount (or `0.00`), the inferred/used actual APY, day count, and validation errors. A nonempty `errors` list means the result must not support a credit.

Example runnable call:

```sh
printf '%s' '{"account_id":"savings-id","expected_apy_percent":6.5,"actual_credit_amount":"0.00","daily_balances":[{"date":"2025-01-01","balance":"50000.00"}],"actual_apy_percent":null}' | python3 scripts/interest_analysis.py
```

Validate before acting that `errors` is empty, `correction_amount` is greater than `0.00`, the output account ID matches the verified savings account, and the inputs describe the same statement period as the posted interest transaction. The calculated value is a recommendation for the authorized agent; it does not apply a credit automatically.
