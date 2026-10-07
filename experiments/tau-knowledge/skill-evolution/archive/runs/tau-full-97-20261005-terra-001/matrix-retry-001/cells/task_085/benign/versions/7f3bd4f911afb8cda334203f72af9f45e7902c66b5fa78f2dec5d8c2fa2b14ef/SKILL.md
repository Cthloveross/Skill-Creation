---
name: debit-card-atm-dispute-filing
description: Formally file a verified debit-card ATM cash-discrepancy claim through the authorized banking tools. Use when an ATM withdrawal dispensed too little cash or no cash and the agent must verify eligibility, review a Rho-Bank ATM record, determine provisional-credit eligibility, and submit the complete dispute payload.
---

# Debit-card ATM cash-discrepancy filing

Use this Skill with the execution agent's normal banking tools. `scripts/assess_dispute.py` evaluates runtime-supplied facts and produces a candidate payload. It never files a dispute, issues credit, or modifies a card; the execution agent must make the authorized filing call.

## Do not defer an eligible filing

A statement date is **not** a listed pre-filing requirement. Do not delay, refuse, transfer, or otherwise withhold a timely ATM cash-discrepancy filing merely because the statement date, an exact account tier label, or a journal-confirmation result is unavailable.

Give the customer the general Regulation E notice before proceeding: reports within two business days of the statement may limit liability to $50; within 60 days may limit liability to $500; after 60 days liability may be unlimited. Obtain a statement date when it is useful for a personalized liability explanation, but do not make it a filing gate.

If the customer reported the ATM shortage on the transaction date, the report is timely for provisional-credit purposes even when the later statement date is not presently available: a statement showing that transaction cannot make a same-day report late. Still do not invent a statement date or a personalized liability tier.

## Facts required before filing

For each claim, obtain and preserve:

- Verified customer identity, verified `user_id`, and a successful `log_verification` audit record. Match two customer-provided identity fields against the user record, get the current time, then log the complete returned profile and timestamp.
- The selected checking account's ID, type, status, opening date, and any known hold/restriction status.
- A debit card linked to that account, including `card_id`, linked `account_id`, cardholder `user_id`, and status.
- The exact matching transaction from the account history: ID, account ID, date, debit amount, description/ATM identifier, type, and status.
- Existing debit-dispute records, counted only for the selected account.
- The actual cash shortage, discovery date, card-possession response, PIN-compromise enum, ATM-operator-contact response, and written-statement consent.
- Whether the ATM is Rho-Bank owned or third-party. For Rho-Bank ATMs, review the corresponding transaction/journal information available in account history and compare it with the claim.

If the customer provides conflicting dates or facts, ask for a clear correction and use the final confirmed fact. Do not silently select a date that contradicts the customer.

## Filing eligibility

File when all of these are established:

1. Verification was successful and logged.
2. The selected transaction is an ATM withdrawal, belongs to the linked checking account, and has an exact transaction ID.
3. The shortage is at least $1.00 and does not exceed the withdrawal amount.
4. The transaction is no more than 60 calendar days old.
5. The card is linked to an `OPEN` checking account and belongs to the verified user.
6. The ATM owner is identified.
7. Adding the claim remains within the account's active-dispute capacity.

Count `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED` disputes as active unless an authoritative result gives an account-specific active count. Limits are per account: Entry 2, Mid 3, Premium 4, Elite 5.

Do not block a filing solely because an account product/class label is not one of those tier names. With zero or one active disputes, the account has capacity under every documented tier maximum. If there are two or more active disputes and the tier is unknown, obtain an authoritative tier or account-specific capacity before filing.

A Rho-Bank journal indicating the requested amount does not validate the shortage, but it also does not prevent the customer from formally filing the dispute.

## Required execution sequence

1. Locate the customer if needed. Verify two identity fields, call `get_current_time`, and call `log_verification`. Stop if verification fails.
2. Unlock and call `get_all_user_accounts_by_user_id_3847` using the verified user ID. Select the customer-identified `OPEN` checking account. Ask a clarifying question if selection is ambiguous.
3. Unlock and call `get_debit_cards_by_account_id_7823` for that account. Confirm the card is linked to the selected account and belongs to the verified user. If multiple plausible cards exist, confirm the last four digits.
4. Unlock and call `get_bank_account_transactions_9173` for the selected account. Match date, debit amount, ATM description/identifier, and `atm_withdrawal` type. Use the exact returned transaction ID. The disputed amount is the missing cash, not the total ATM debit.
5. Unlock and call `get_debit_dispute_status_7483` for the verified user. Determine the selected account's active-dispute count and capacity using the rule above.
6. For a Rho-Bank ATM, review the corresponding transaction/journal data. Record whether it corroborates the shortage if the data supports a determination; do not require corroboration to file.
7. Run `scripts/assess_dispute.py` with normalized live facts. Correct missing or inconsistent blocking facts. Warnings are not filing blocks.
8. When `ready_to_file` is true, unlock and call `file_debit_card_transaction_dispute_6281` using every field in `filing_payload`. Confirm all identifiers and dates against live results immediately before the call. Do not transfer instead of making this call for an otherwise eligible claim.
9. Report the actual filing result. Do not state that a credit or card action occurred unless an authorized banking tool records it.

## ATM cash-discrepancy filing payload

For an ATM that dispensed too little cash or no cash, submit:

- `dispute_category`: `atm_cash_discrepancy`
- `transaction_type`: `atm_withdrawal`
- `card_action`: `keep_active`
- Exact runtime `transaction_id`, `account_id`, `card_id`, and `user_id`
- `transaction_date` and `discovery_date` in `MM/DD/YYYY`
- Positive float `disputed_amount` equal to the actual shortage
- `card_in_possession` as the customer's boolean response
- `pin_compromised` as exactly `yes_shared`, `yes_observed`, `no`, or `unknown`
- `contacted_merchant` as whether the customer contacted the ATM operator
- `police_report_filed: false` for an ATM malfunction absent a separate fraud claim
- `written_statement_provided: true` only after consent, including consent to use the conversation as the statement
- `provisional_credit_eligible` from the assessment

Operator contact is collected for the filing record but is not a pre-filing requirement for an ATM cash discrepancy. Do not reclassify an ATM malfunction as fraud merely because the operator was not contacted.

## Provisional credit and follow-up

`atm_cash_discrepancy` is a qualifying provisional-credit category. Required eligibility is established when reporting is timely relative to the statement, the customer provides the written statement, the checking account is OPEN without a known hold/restriction, and the PIN was not voluntarily shared (`yes_shared`). A same-day report of the transaction is timely even if the statement date is unavailable. The filing payload must always include the assessed `provisional_credit_eligible` boolean.

For a confirmed Rho-Bank ATM shortage with established eligibility, follow the immediate provisional-credit process. Otherwise, qualifying standard accounts require provisional credit within 10 business days; accounts open fewer than 30 days have a 20-business-day timeline. Do not claim that credit has been issued unless the appropriate authorized tool confirms it.

For a third-party ATM, explain that a chargeback is submitted to the owner/network and the investigation may take up to 90 days. For a third-party ATM cash discrepancy over $200, explain that an Electronic Fund Transfer Error Resolution Affidavit will be sent to the registered email, must be returned within 10 business days, and false certification is a federal offense.

`keep_active` is filing metadata and requires no card change for this claim. If other claims on the same card are also filed, retain each claim's own mapped action and perform only the most severe authorized actual card action after all filings.

## Script interface

Send one JSON object to `scripts/assess_dispute.py` on stdin. It emits one JSON object on stdout with:

- `ready_to_file`: whether only blocking requirements are satisfied
- `blocking_reasons` and non-blocking `warnings`
- `active_dispute_count_for_account` and `account_dispute_limit`
- `liability_assessment` and `provisional_credit` assessments
- `filing_payload`: the complete candidate arguments for the filing tool

Input schema (replace all placeholders with live tool facts):

```json
{
  "current_date": "MM/DD/YYYY",
  "verified_and_logged": true,
  "account": {
    "account_id": "runtime-account-id",
    "account_type": "checking",
    "status": "OPEN",
    "account_class": "runtime-product-or-tier-label",
    "date_opened": "MM/DD/YYYY",
    "has_holds_or_restrictions": false
  },
  "card": {
    "card_id": "runtime-card-id",
    "account_id": "runtime-account-id",
    "user_id": "runtime-user-id",
    "status": "ACTIVE"
  },
  "transaction": {
    "transaction_id": "runtime-transaction-id",
    "account_id": "runtime-account-id",
    "date": "MM/DD/YYYY",
    "amount": -300.0,
    "type": "atm_withdrawal"
  },
  "claim": {
    "user_id": "runtime-user-id",
    "disputed_amount": 100.0,
    "discovery_date": "MM/DD/YYYY",
    "statement_date": null,
    "card_in_possession": true,
    "pin_compromised": "no",
    "contacted_merchant": false,
    "written_statement_provided": true,
    "atm_owner": "rho_bank",
    "journal_discrepancy_confirmed": null
  },
  "disputes": []
}
```
