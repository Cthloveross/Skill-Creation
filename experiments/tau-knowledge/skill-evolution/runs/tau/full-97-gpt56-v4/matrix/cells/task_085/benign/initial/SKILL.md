---
name: debit-card-atm-dispute
version: 1.0.0
description: Handle a verified customer's debit-card transaction dispute, especially an ATM cash discrepancy, by collecting required facts, validating account/card/transaction eligibility, reviewing Rho-Bank ATM records, filing the dispute, and applying the mapped card action.
---

# Debit-card transaction dispute workflow

Use this Skill when a customer asks to dispute a debit-card transaction, including an ATM cash shortage, duplicate, fraud, merchant, or amount issue. It supports the agent's normal banking-tool workflow; it never performs bank actions itself.

## 1. Establish identity and explain timing

1. Identify the customer using an available identifier, but do **not** regard a name or registered email lookup alone as completed verification.
2. Confirm any two of date of birth, email, phone number, and address against the user record. Obtain the missing confirmations from the customer rather than disclosing them as prompts.
3. After two fields match, get the current time and call `log_verification` with the complete retrieved user record and timestamp.
4. Before proceeding with an unauthorized-activity dispute, explain the Regulation E exposure: reported within 2 business days: maximum $50; within 60 days: maximum $500; after 60 days: potentially unlimited liability and funds may not be recoverable. Record the discovery date.

For an ATM malfunction rather than fraud, still capture the discovery date and explain the filing process. Do not characterize an ATM short-dispense as fraud without customer facts supporting fraud.

## 2. Gather a complete case record

For each issue, process one transaction at a time. If the customer reports duplicate charges, dispute the earliest transaction.

Collect and retain:

- transaction merchant/ATM, date, full transaction amount, and the amount actually disputed;
- the customer’s discovery date;
- whether the customer has the physical card;
- PIN status: `yes_shared`, `yes_observed`, `no`, or `unknown`;
- whether the merchant/ATM was contacted (required as a filing field; merchant contact also affects non-fraud provisional-credit treatment);
- agreement for the conversation to serve as a written statement;
- fraud facts, transaction channel, and police-report status for suspected fraud over $500.

Map the facts only to allowed categories and transaction types. A withdrawal where the ATM debited/requested more cash than it dispensed is `atm_cash_discrepancy` and `atm_withdrawal`. Its individual `card_action` is `keep_active`.

Ask whether the ATM was Rho-Bank branded or third-party. For a third-party ATM cash discrepancy above $200, tell the customer that an Electronic Fund Transfer Error Resolution Affidavit will be emailed, is due within 10 business days, and a false affidavit is a federal offense.

## 3. Locate and validate bank records

After verification, unlock and use the documented internal tools as needed:

- `get_all_user_accounts_by_user_id_3847` to find the relevant checking account and confirm it is OPEN. Select the account the customer identifies; do not infer an account from a nickname alone when multiple plausible accounts exist.
- `get_debit_cards_by_account_id_7823` to find the debit card linked to that checking account. Confirm it belongs to the verified user and is the card relevant to the transaction.
- `get_bank_account_transactions_9173` to locate the exact transaction ID and review its date, amount, description, type, and status. Transaction results are newest first. Do not substitute a transaction ID based only on a similar merchant description.

Validate before filing: verified customer; open linked checking account; debit-card linkage; disputed transaction at least $1; transaction no more than 60 days old; and account-specific open-dispute count within the tier limit (Entry 2, Mid 3, Premium 4, Elite 5). The limit is per account, not per customer. If the count or an account hold/restriction cannot be checked with available authorized records, do not guess or file; obtain the required internal confirmation or use the normal escalation path.

For a Rho-Bank ATM cash discrepancy, inspect the corresponding account transaction and available ATM journal evidence. Compare the journal result to the claim. If the discrepancy is confirmed, arrange immediate provisional credit. If the journal indicates the requested amount was dispensed, explain that the claim is not validated by the journal but the customer may still file a formal dispute.

For an ATM deposit dispute instead, obtain images with `get_atm_deposit_images_8473`; that procedure is not a substitute for the cash-discrepancy journal review.

## 4. Determine provisional-credit eligibility

For `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`, provisional credit is required only when all required conditions are supported: timely reporting within 60 days of the statement, an agreed/provided written statement, and an OPEN unrestricted checking account. A voluntarily shared PIN disqualifies required credit. A new account with a card-not-present dispute also does not require it.

For qualifying standard accounts, the normal deadline is 10 business days; new accounts may be 20 business days. If immediate Rho-Bank ATM journal confirmation establishes a cash discrepancy, issue it immediately through the authorized banking process. Required credit is for the full disputed amount, subject to any applicable late-report liability offset. Do not promise required provisional credit for categories outside the qualifying list or when a prerequisite is unconfirmed.

## 5. File and complete the card handling

After all validations, unlock `file_debit_card_transaction_dispute_6281` and pass the exact validated values. Use the transaction's actual date in `MM/DD/YYYY` format and use a positive `disputed_amount`, not the signed debit amount from account history. Include every required filing field, including `police_report_filed`, `written_statement_provided`, and the determined `provisional_credit_eligible`.

Use the exact category-to-card-action mapping:

- `card_present_fraud`, `card_not_present_fraud` -> `close_and_reissue`
- `unauthorized_transaction` -> `freeze_pending_investigation`
- all other permitted categories -> `keep_active`

The action in each filing is metadata. After filing all disputes for the same card, perform the one normal card action with the highest severity: close/reissue, then freeze, then keep active. Do not change an individual filing's `card_action` merely because another dispute is more severe. A cash-discrepancy-only case remains active and requires no freeze or replacement.

Confirm to the customer what was filed, the transaction and disputed amount, the card status/action, any provisional-credit timing that is supported by the record, and material next steps. Never claim journal confirmation, eligibility, or a completed filing unless the corresponding normal banking tool returned success.

## Optional deterministic preflight helper

`scripts/dispute_preflight.py` accepts JSON on stdin and writes JSON to stdout. It validates a proposed filing record and calculates a conservative preliminary provisional-credit result; it does not retrieve records or file a dispute.

Example input shape:

```json
{
  "verified": true,
  "account_status": "OPEN",
  "account_restricted": false,
  "card_linked": true,
  "transaction_id": "...",
  "account_id": "...",
  "card_id": "...",
  "user_id": "...",
  "dispute_category": "atm_cash_discrepancy",
  "transaction_type": "atm_withdrawal",
  "transaction_date": "MM/DD/YYYY",
  "discovery_date": "MM/DD/YYYY",
  "today": "MM/DD/YYYY",
  "transaction_amount": 300.0,
  "disputed_amount": 100.0,
  "card_in_possession": true,
  "pin_compromised": "no",
  "contacted_merchant": false,
  "police_report_filed": false,
  "written_statement_provided": true,
  "timely_statement_report": true,
  "account_is_new": false,
  "open_disputes": 0,
  "account_tier": "Entry"
}
```

Review `ok_to_file`, `blocking_issues`, `filing_payload`, and `provisional_credit_eligible`. Inputs such as journal confirmation, holds, and the open-dispute count must come from authorized records, not customer guesses.
