---
name: debit-card-atm-dispute-filing
description: Process and file a verified debit-card ATM cash-discrepancy dispute, including Regulation E notices, account/card/transaction lookup, Rho-Bank versus third-party ATM handling, provisional-credit assessment, and card-action follow-through. Use when a customer reports an ATM withdrawal that dispensed too little or no cash. Also supports the shared eligibility checks used for other debit-card disputes.
---

# Debit-card ATM dispute filing

Use this Skill only with the execution agent's authorized banking tools. The included script assesses supplied runtime facts; it never files a dispute, changes a card, or issues credit itself.

## Required runtime inputs and checks

Before filing, obtain and retain these facts for each claimed transaction:

- A successfully verified customer and their `user_id`. Verify two identity fields against the user record, retrieve the current time, and call `log_verification` with the complete returned user profile and timestamp.
- The claimed transaction, its exact transaction ID, date, posted debit amount, and account ID.
- The linked debit card ID and cardholder user ID.
- A checking account that is `OPEN`, its tier/class, opening date, and whether it has any hold or restriction.
- The number of currently active disputes on *that account* (not all of the customer's accounts).
- Discovery date; the customer's physical-card possession; PIN-compromise answer; merchant/ATM-operator contact answer; written-statement consent; and, when applicable, fraud and police-report details.
- Whether the ATM is Rho-Bank branded or third-party. For a Rho-Bank ATM, review the corresponding transaction/journal information and record whether it corroborates the cash discrepancy.

Tell the customer before proceeding that liability exposure is up to $50 when reported within two business days of the statement, up to $500 within 60 days, and may be unlimited after 60 days. Obtain the statement date if a personalized tier must be calculated; do not guess it from a transaction date.

The filing prerequisites are: verified customer, at least a $1 dispute, transaction no more than 60 days old, an open linked checking account, and no excess active disputes for that account. Tier limits are Entry 2, Mid 3, Premium 4, and Elite 5. Treat investigation-in-progress statuses (`OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED`) as active when conservatively assessing capacity. If a tool or local policy exposes a more specific count, use that authoritative count.

## Tool workflow

1. If identity has not already been verified in the live interaction, locate the customer with an available user lookup. Compare at least two provided fields to the returned record. Call `get_current_time`, then `log_verification`. Do not file if verification fails.
2. Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified `user_id`. Match the customer-named account to an `OPEN` checking account. If the account name is ambiguous, ask the customer to select it; do not infer it.
3. Unlock and call `get_debit_cards_by_account_id_7823` for that account. Select the card actually linked to the claim. If multiple plausible current cards exist, confirm its last four digits with the customer. Ensure its returned `user_id` is the verified user.
4. Unlock and call `get_bank_account_transactions_9173` for the selected account. Match the ATM transaction by date, amount, description/ATM identifier, and withdrawal type. For a cash shortage, `disputed_amount` is the shortage, not necessarily the full account debit. The transaction must be at least $1 and no more than 60 calendar days old.
5. Unlock and call `get_debit_dispute_status_7483` with the user ID. Count only active disputes whose `account_id` equals the selected account. Stop if adding this dispute exceeds the selected account's tier limit.
6. For a Rho-Bank ATM, use the corresponding account-transaction review/journal information to compare what the ATM recorded with the claim. A journal that shows the full requested amount does not prevent filing; explain that the claim could not be internally validated but the customer may still file a formal dispute. If a discrepancy is confirmed, flag the case for immediate provisional credit subject to the required eligibility facts.
7. For a third-party ATM, advise that the bank submits a chargeback to the owner/network, the investigation may take up to 90 days, and provisional credit is due within 10 business days when required. For a cash-discrepancy amount above $200, advise that an Electronic Fund Transfer Error Resolution Affidavit will be emailed, must be returned within 10 business days, and false certification is a federal offense.
8. Build and validate the filing payload. Then unlock and call `file_debit_card_transaction_dispute_6281` using the exact field names and allowed enum values below.

## ATM cash-discrepancy filing payload

For this issue type use:

- `dispute_category`: `atm_cash_discrepancy`
- `transaction_type`: `atm_withdrawal`
- `card_action`: `keep_active`
- `transaction_id`, `account_id`, `card_id`, and `user_id`: runtime lookup values only
- `transaction_date` and `discovery_date`: `MM/DD/YYYY`
- `disputed_amount`: the actual dollar shortage as a positive float
- `card_in_possession`: customer response
- `pin_compromised`: exactly `yes_shared`, `yes_observed`, `no`, or `unknown`
- `contacted_merchant`: whether the customer contacted the ATM operator
- `police_report_filed`: `false` unless a fraud case requires and has received the customer response; cash malfunction claims are not fraud claims
- `written_statement_provided`: true only when the customer agrees to provide a statement, including consent to use the conversation
- `provisional_credit_eligible`: the assessed boolean described below

For cash discrepancies, merchant contact is still captured because the tool requires it. It is not a reason to recategorize an ATM malfunction as fraud.

## Provisional credit and timelines

ATM cash discrepancies are in the qualifying categories. Mark `provisional_credit_eligible` true only when all of the following are established: report within 60 days of the relevant statement, a written statement is provided, and the linked checking account is open with no hold/restriction. A voluntary shared PIN makes provisional credit not required; a new account's card-not-present exception is not relevant to an ATM withdrawal. If the Rho-Bank ATM journal confirms the discrepancy and those conditions are met, follow the Rho-Bank process for immediate provisional credit. Otherwise, qualifying standard accounts must receive it within 10 business days; accounts open under 30 days have a 20-business-day deadline. Do not claim that credit was actually issued unless an authorized banking tool records it.

The generic non-fraud merchant-contact guidance may mean credit is discretionary when the customer did not contact an operator. It does not override a confirmed Rho-Bank ATM discrepancy's immediate-credit process. Clearly describe any discretionary determination rather than presenting it as guaranteed.

## Fraud, duplicates, and card actions

An ATM malfunction is `atm_cash_discrepancy`, not an unauthorized/fraud category. If a different issue is unauthorized, determine whether fraud is suspected: use `card_present_fraud` for physical-card fraud and `card_not_present_fraud` for online/phone fraud; use `unauthorized_transaction` only where fraud is not suspected. For duplicate charges, select the earliest transaction first.

Record each filing's own mapped action: fraud categories map to `close_and_reissue`, unauthorized non-fraud maps to `freeze_pending_investigation`, and ATM cash discrepancies map to `keep_active`. If several disputes on one card are filed, finish all filings, then perform the single most severe actual action: close/reissue over freeze over keep active. A `card_action` in the filing is metadata only. For `keep_active`, do not change the card. For more severe actions, use only an authorized, available banking tool; do not invent a close/reissue tool name.

## Script-assisted validation

Run `scripts/assess_dispute.py` with collected runtime facts before filing. It reads one JSON object from stdin and emits one JSON object to stdout.

Example shape (replace all values with live lookup results; omitted/null values cause a non-ready result):

```json
{
  "current_date": "MM/DD/YYYY",
  "verified_and_logged": true,
  "account": {"account_id":"...","account_type":"checking","status":"OPEN","account_class":"Entry Tier","date_opened":"MM/DD/YYYY","has_holds_or_restrictions":false},
  "card": {"card_id":"...","account_id":"...","user_id":"...","status":"ACTIVE"},
  "transaction": {"transaction_id":"...","account_id":"...","date":"MM/DD/YYYY","amount":-100.0,"type":"atm_withdrawal"},
  "claim": {"user_id":"...","disputed_amount":25.0,"discovery_date":"MM/DD/YYYY","statement_date":"MM/DD/YYYY","card_in_possession":true,"pin_compromised":"no","contacted_merchant":false,"written_statement_provided":true,"atm_owner":"rho_bank","journal_discrepancy_confirmed":true},
  "disputes": [{"account_id":"...","status":"OPEN"}]
}
```

Only file when `ready_to_file` is true. Copy `filing_payload` only after separately confirming its tool-required values against live tool results. Read `blocking_reasons`, `warnings`, `liability_assessment`, and `provisional_credit` aloud or act on them as applicable. The script's result is validation support, not a substitute for reviewing the actual account transaction/journal data.
