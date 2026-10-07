---
name: atm-fee-review-and-human-transfer
version: 1.0.0
description: Review a verified customer's checking-account ATM transactions against Purple, Light Blue, Dark Green, and Evergreen fee terms; identify possible fee mischarges or missing Purple ATM-operator-fee rebates; and safely transfer a customer who requests human assistance.
---

# ATM Fee Review and Human Transfer

Use this Skill when a customer asks about ATM withdrawal fees, ATM operator surcharges, ATM rebates, or a review of checking-account ATM activity for Purple, Light Blue, Dark Green, or Evergreen accounts.

## Controls and prerequisites

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For an account-specific review or a credit, obtain and log identity verification first. Verify at least two of date of birth, email, phone number, and address against the customer record, then call `log_verification` with all returned record fields and the current timestamp. A name and email used merely to locate a record do not replace the required two-field verification.

Do not disclose account activity before verification. Do not apply a credit merely because an ATM charge appears high: first verify ownership, checking status, every relevant transaction, the applicable product term, the exact net correction, and whether a qualifying credit is already present.

## Immediate human-transfer path

If the customer explicitly asks for a human, agent, representative, or transfer (including a transfer marker), do not keep them in a self-service loop. Call `transfer_to_human_agents` with reason `customer_requests_human_no_specific_reason` and a concise summary that states:

- the request is an ATM-fee/ATM-rebate review;
- which account products are named, if known;
- whether identity verification was completed; and
- what review steps or information are still outstanding.

A transfer itself must not cause an account lookup, transaction lookup, or credit. If the customer has not explicitly requested a human, continue with the review below.

## Account and transaction lookup workflow

1. Identify the customer using a provided registered identifier. Use the appropriate normal lookup tool, such as `get_user_information_by_email`, `get_user_information_by_name`, or `get_user_information_by_id`.
2. Ask for and verify two identity fields, retrieve the current time with `get_current_time`, and log the successful verification.
3. Unlock `get_all_user_accounts_by_user_id_3847` using `unlock_discoverable_agent_tool`, then call it through `call_discoverable_agent_tool` with the verified `user_id`. Confirm that each account under review belongs to the customer, is open/eligible as applicable, and is a checking account. Record its account ID, account class, status, and balance for the review.
4. Unlock `get_bank_account_transactions_9173`. For every selected checking account, call it with that account ID. It returns reverse-chronological transactions; retain all requested-month entries and sort copies oldest to newest when counting monthly free withdrawals or rebates.
5. Inspect ATM withdrawals, `atm_fee` entries, and credits such as `fee_rebate`, `rebate_credit`, or `fee_refund`. Read descriptions and dates carefully. A separate ATM-owner/operator surcharge is not automatically a bank ATM fee and must not be treated as one without supporting transaction detail.
6. State the transaction evidence and comparison for each account. If the history does not identify whether an ATM was foreign, out of network, or an operator surcharge, explain that classification cannot safely be inferred and request a receipt or a specialist review.

Use only actual transaction records returned at runtime. Do not invent withdrawals, locations, posting dates, surcharge amounts, rebate eligibility, or fee corrections.

## Fee comparison rules

Apply the rule matching the verified account class and the transaction's supported classification. Fees are assessed per withdrawal unless a monthly allowance is stated.

| Account | Out-of-network ATM withdrawal | Foreign ATM withdrawal | Rebate notes |
|---|---|---|---|
| Purple | $2.50 per withdrawal | $0 bank foreign-ATM withdrawal fee | Eligible posted ATM operator fees may be rebated up to $30 per month. Check operator-fee coding, posting, and total rebates already received. |
| Light Blue | First 2 monthly out-of-network withdrawals are free; later ones are $2.50 each | First 2 monthly foreign withdrawals are free; later ones are $4 each | Operator charges are separate. |
| Dark Green | 1% of cash amount, $1.50 minimum | 2.5% of cash amount, $6 maximum | Operator charges may be separate. |
| Evergreen | 1% of cash amount, $2.50 maximum | 2% of cash amount, $3 minimum | Operator charges may be separate. |

For allowance accounts, count all relevant withdrawals in the entire calendar month, not just transactions the customer believes are wrong. For percentage fees, use the cash dispensed amount and compare to the separate bank fee line. Do not combine an ATM owner surcharge with a Rho-Bank fee.

Use `scripts/calculate_atm_fees.py` only after transaction classifications and amounts are supported by history. It calculates documented bank-fee expectations from explicitly labeled events; it does not establish that a transaction is eligible or identify a surcharge from free text.

## Possible correction and credit procedure

Only consider a checking-account credit if transaction history demonstrates either (1) a missing eligible rebate or (2) a bank fee mischarge. Confirm the credit has not already been applied and calculate the exact net correction across all discrepancies for that account.

Before applying a credit, verify the account is checking, ownership and eligibility are current, the transaction history supports every component, and the precise amount is positive. Unlock and use `apply_checking_account_credit_5829` only after those checks. It may be called only once per checking account per customer interaction, and a 14-day cooldown follows. Combine all supported corrections for that account into one exact credit. Use `rebate_credit` for missing rebates or `fee_refund` for incorrect fees; if combined, use the type covering the majority of the correction amount. Never round or estimate.

If information is missing, no mismatch is supported, the account is not checking, a prior credit/cooldown prevents a new credit, or the customer seeks a human, do not apply a credit. Explain the limitation or transfer as appropriate.

## Customer response

Provide a clear account-by-account summary: transaction date, cash withdrawal if known, separate bank fee, separate operator surcharge if known, applicable rule, and whether the transaction appears supported, needs more evidence, or is a supported correction. Do not promise a credit until it has been successfully applied. After a successful credit, state the amount, reason, and updated balance returned by the banking tool.

## Fee-calculator runtime interface

Run `scripts/calculate_atm_fees.py` with JSON on stdin. It emits JSON on stdout.

Input schema:

```json
{
  "account_class": "purple|light_blue|dark_green|evergreen",
  "events": [
    {
      "date": "MM/DD/YYYY",
      "classification": "out_of_network|foreign",
      "withdrawal_amount": "positive decimal string",
      "actual_bank_fee": "optional nonnegative decimal string"
    }
  ]
}
```

All events must be for one calendar month and one account. The output returns events in chronological order with an expected bank fee and, when `actual_bank_fee` was supplied, `difference_actual_minus_expected`. A positive difference means the recorded bank fee exceeds the calculated documented bank fee; it is not by itself authorization to issue a credit. Invalid dates, amounts, classes, classifications, mixed months, and duplicate/non-object fields return a JSON error.

Example executor call (with values obtained from the live history, not prefilled examples):

```text
run_skill_script(relative_path="scripts/calculate_atm_fees.py", input_json={"account_class":"...","events":[...]})
```

Validate calculator output by checking that its event count equals the supplied transaction count, that all events have the same month, and that each result maps to a supported transaction-history record before relying on it.
