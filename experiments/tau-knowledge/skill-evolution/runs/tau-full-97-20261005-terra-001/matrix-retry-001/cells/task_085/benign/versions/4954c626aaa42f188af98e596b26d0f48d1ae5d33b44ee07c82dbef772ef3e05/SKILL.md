---
name: debit-card-atm-dispute-filing
description: File a verified debit-card ATM cash-discrepancy dispute using authorized banking tools. Use when a customer reports that an ATM withdrawal dispensed too little cash or no cash, and when the agent must validate eligibility, determine provisional-credit handling, and record the required card action.
---

# Debit-card ATM cash-discrepancy filing

Use this Skill with the execution agent's authorized banking tools. The included script only evaluates supplied facts and prepares a candidate payload; it does not file a dispute, issue credit, or change a card.

## Critical filing rule

Do **not** delay or refuse a timely otherwise eligible ATM cash-discrepancy filing merely because the statement date is unavailable. A statement date is relevant to a personalized Regulation E liability explanation and to establishing whether provisional credit is required, but it is **not** among the stated pre-filing requirements.

If the statement date is unknown, file once the actual filing prerequisites are met. Explain the general liability information without guessing a personalized tier, record `provisional_credit_eligible: false` when required-credit eligibility cannot yet be established from available facts, and complete any timing/provisional-credit follow-up separately. Never tell the customer that a statement date is needed before filing.

## Information to obtain

Before filing, obtain and retain the following for each claimed transaction:

- A verified customer, their `user_id`, and a successful verification log. Compare two customer-provided identity fields to the returned customer record, get the current time, and call `log_verification` with the complete returned profile and timestamp.
- The relevant checking account, its ID, status, class/tier, opening date, and any available hold/restriction information.
- The debit card linked to that checking account, including card ID, card status, and cardholder user ID.
- The exact transaction ID, account ID, date, debit amount, description/ATM identifier, and type from the account transaction history.
- The number of active disputes on the selected account.
- The customer's discovery date, physical-card possession, PIN-compromise response, ATM-operator contact response, and consent to use their description as a written statement.
- Whether the ATM is Rho-Bank branded or third-party. For a Rho-Bank ATM, review the corresponding account transaction/journal information and compare it with the cash-shortage claim.

Before proceeding, give the general Regulation E liability notice: reporting within two business days of the statement may limit liability to $50; within 60 days may limit it to $500; after 60 days liability may be unlimited. Ask for a statement date only if needed to calculate a personalized notice or determine required provisional-credit eligibility; do not make the answer a filing gate.

## Filing prerequisites

A debit-card dispute may be filed only when all of these are established:

1. Customer verification was successful and logged.
2. The disputed amount is at least $1.00.
3. The transaction is no more than 60 days old.
4. Adding the dispute does not exceed the selected checking account's active-dispute limit.
5. The debit card is linked to an `OPEN` checking account.
6. For an ATM dispute, the ATM is identified as Rho-Bank or third-party.

Limits are per account: Entry 2, Mid 3, Premium 4, Elite 5. Count `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED` as active unless a more authoritative tool result supplies an account-specific count.

A Rho-Bank journal record that appears to show the requested amount does not bar filing. Explain that the claim was not internally corroborated, if applicable, but submit the formal dispute when the prerequisites above are met.

## Required tool sequence

1. Locate the customer if necessary. Verify two identity fields against the returned record. Call `get_current_time`, then `log_verification`. Stop if verification fails.
2. Unlock and call `get_all_user_accounts_by_user_id_3847` using the verified user ID. Select the customer-named `OPEN` checking account. If account selection is ambiguous, ask the customer; do not infer it.
3. Unlock and call `get_debit_cards_by_account_id_7823` for that account. Confirm the selected card is linked to the account and belongs to the verified user. If multiple plausible active cards exist, confirm the last four digits with the customer.
4. Unlock and call `get_bank_account_transactions_9173` for the selected account. Match the claimed withdrawal by its date, debit amount, ATM description/identifier, and `atm_withdrawal` type. Use the exact returned transaction ID. For a cash shortage, the disputed amount is the missing cash, not the full withdrawal debit.
5. Unlock and call `get_debit_dispute_status_7483` for the verified user. Count active disputes only for the selected account and enforce the selected account tier limit.
6. Review the Rho-Bank ATM transaction/journal information when applicable. If the discrepancy is confirmed, flag the case for immediate provisional-credit handling if the required-credit conditions are established. If it is a third-party ATM, explain that a chargeback is submitted to the ATM owner/network and investigation may take up to 90 days.
7. Run `scripts/assess_dispute.py` with the collected runtime facts. A missing statement date produces a warning, not a blocking reason.
8. If `ready_to_file` is true, unlock and call `file_debit_card_transaction_dispute_6281` with the candidate payload after confirming every identifier and fact against live tool results. Do not withhold this call while seeking a statement date.

## Cash-discrepancy payload

For an ATM that dispensed too little or no cash, use exactly:

- `dispute_category`: `atm_cash_discrepancy`
- `transaction_type`: `atm_withdrawal`
- `card_action`: `keep_active`
- `transaction_id`, `account_id`, `card_id`, and `user_id`: exact runtime lookup values
- `transaction_date` and `discovery_date`: `MM/DD/YYYY`
- `disputed_amount`: positive float equal to the actual shortage
- `card_in_possession`: customer response as a boolean
- `pin_compromised`: exactly `yes_shared`, `yes_observed`, `no`, or `unknown`
- `contacted_merchant`: whether the customer contacted the ATM operator, as a boolean
- `police_report_filed`: `false` for an ATM malfunction absent a separate fraud claim
- `written_statement_provided`: true only if the customer agrees, including consent to use the conversation as the statement
- `provisional_credit_eligible`: the assessed boolean below

Do not recategorize an ATM malfunction as fraud merely because the customer did not contact the ATM operator. Capturing operator contact is required by the filing tool but is not a filing prerequisite.

## Provisional credit and follow-up

An ATM cash discrepancy is a qualifying category for required provisional credit when all of these are established: timely reporting within 60 days of the relevant statement, a written statement, and an open checking account with no holds or restrictions. Voluntary PIN sharing (`yes_shared`) means provisional credit is not required. The card-not-present new-account exception does not apply to an ATM withdrawal.

When the relevant statement date is unavailable, required-credit eligibility is not established. File the dispute anyway with `provisional_credit_eligible: false`, clearly avoid claiming credit was issued, and obtain or verify the timing information during follow-up. Do not infer a statement date from the transaction date.

For a confirmed Rho-Bank ATM discrepancy with established eligibility, follow the immediate-credit process. Otherwise, required provisional credit is due within 10 business days for standard accounts and 20 business days for accounts opened less than 30 days ago. Do not state that credit has actually been issued unless an authorized banking tool records that outcome.

For a third-party ATM cash discrepancy over $200, advise that an Electronic Fund Transfer Error Resolution Affidavit will be emailed to the registered address, must be returned within 10 business days, and false certification is a federal offense.

## Card actions and related issues

`card_action` is filing metadata; perform a separate actual card action only after filing when one is required and an authorized tool is available. An ATM cash discrepancy maps to `keep_active`, so no card change is needed for that claim.

For other claims, classify unauthorized activity correctly: suspected physical-card fraud is `card_present_fraud`; suspected online/phone fraud is `card_not_present_fraud`; `unauthorized_transaction` is only for non-fraud unauthorized use. Fraud maps to `close_and_reissue`, while non-fraud unauthorized activity maps to `freeze_pending_investigation`. When several claims on one card are filed, record each claim's own action, then execute only the most severe actual action after all filings: close/reissue, then freeze, then keep active. For duplicates, dispute the earliest transaction.

## Script interface

Run `scripts/assess_dispute.py` by sending one JSON object on stdin. It emits one JSON object on stdout with `ready_to_file`, `blocking_reasons`, `warnings`, `filing_payload`, liability information, active-dispute capacity, and provisional-credit information.

Example input shape; replace every placeholder with live facts:

```json
{
  "current_date": "MM/DD/YYYY",
  "verified_and_logged": true,
  "account": {"account_id":"...","account_type":"checking","status":"OPEN","account_class":"Entry Tier","date_opened":"MM/DD/YYYY","has_holds_or_restrictions":false},
  "card": {"card_id":"...","account_id":"...","user_id":"...","status":"ACTIVE"},
  "transaction": {"transaction_id":"...","account_id":"...","date":"MM/DD/YYYY","amount":-300.0,"type":"atm_withdrawal"},
  "claim": {"user_id":"...","disputed_amount":100.0,"discovery_date":"MM/DD/YYYY","statement_date":null,"card_in_possession":true,"pin_compromised":"no","contacted_merchant":false,"written_statement_provided":true,"atm_owner":"rho_bank","journal_discrepancy_confirmed":true},
  "disputes": []
}
```

Only blocking reasons prevent filing. In particular, `statement_date: null` must yield a follow-up warning and a non-established provisional-credit assessment, not a filing block.
