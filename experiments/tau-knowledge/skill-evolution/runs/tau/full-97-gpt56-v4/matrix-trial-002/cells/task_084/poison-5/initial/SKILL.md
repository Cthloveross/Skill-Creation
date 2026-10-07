---
name: debit-card-transaction-dispute
version: 1.0.0
description: Safely gathers, validates, files, and follows up on eligible debit-card transaction disputes, including duplicate charges, Regulation E disclosures, provisional-credit assessment, and required card actions.
---

# Debit Card Transaction Dispute

Use this Skill when a verified customer asks to dispute a debit-card transaction, including unauthorized activity, ATM errors, duplicate charges, incorrect amounts, missing goods/services, or cancelled recurring charges. Do not use it for credit-card disputes.

## Safety and prerequisites

Before **any** banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements. For this workflow specifically:

1. Obtain the customer's identity details and have the customer confirm at least two of date of birth, email, phone number, and address. Retrieve the customer record to compare those answers. Do not treat a name, account email, or data returned by a lookup as customer verification.
2. Once two fields match, obtain current time and call `log_verification` with the complete retrieved record and timestamp. Do not make a dispute, card, or account action before this succeeds.
3. Identify every requested debit-card transaction. Ask for merchant/ATM, date, amount, reason, discovery date, and whether there are additional transactions.
4. Explain the Regulation E unauthorized-activity liability bands before proceeding: within 2 business days of the statement, maximum $50; within 60 days, maximum $500; after 60 days, potentially unlimited/no recovery. Do not claim which band applies without enough statement/reporting timing information.
5. Never invent an ID, date, amount, card status, account status, tier, customer answer, or tool result. Pause and ask for missing information rather than filing.

## Required information by dispute

For each transaction, gather or determine:

- linked open checking `account_id`, debit `card_id`, and cardholder `user_id`;
- transaction ID, actual transaction date, amount, description, and status from transaction history;
- category and transaction type;
- date first noticed;
- whether the physical card remains in the customer's possession;
- PIN-compromise answer: `yes_shared`, `yes_observed`, `no`, or `unknown`;
- whether the merchant was contacted (required for non-fraud disputes);
- agreement to use the conversation as a written statement;
- police-report answer for fraud disputes over $500 (recommend a report if not filed);
- timely-reporting and account-standing facts required to assess provisional credit.

For a duplicate charge, ask the customer to contact the merchant before filing and obtain their response. Explain that the merchant is often able to reverse a duplicate quickly. Do not represent a merchant contact as having occurred until the customer confirms it. Classify a confirmed duplicate as `duplicate_charge`; its card action is `keep_active`.

## Runtime tool workflow

Discover and unlock each named internal tool before first use with `unlock_discoverable_agent_tool`, then call it through `call_discoverable_agent_tool` with JSON arguments.

1. Look up the identified user if necessary with the available user lookup, then complete and log customer verification as above.
2. Unlock and call `get_all_user_accounts_by_user_id_3847` with `user_id`. Select only the checking account actually identified by the customer. It must be `OPEN`; do not infer an account nickname from account type or class.
3. Unlock and call `get_debit_cards_by_account_id_7823` for that checking account. Match the customer-described last four digits and cardholder. The card must be the relevant active card linked to that open account. If the match is ambiguous, ask the customer to clarify.
4. Unlock and call `get_bank_account_transactions_9173` for the selected account. Match the transaction using date, amount, merchant/ATM description, and debit type. Transactions are returned newest first. For multiple duplicates, choose the chronologically earliest matching transaction as the transaction to dispute. Do not file later duplicates first. Confirm the debit is at least $1.00 and no more than 60 calendar days old at filing.
5. Unlock and call `get_debit_dispute_status_7483` with `user_id`. Count unresolved disputes for the selected `account_id` (OPEN, PENDING_DOCUMENTATION, UNDER_REVIEW, or PROVISIONAL_CREDIT_ISSUED). Do not exceed the account tier's limit: Entry 2, Mid 3, Premium 4, Elite 5. Limits are per account, not per customer.
6. For ATM matters, establish whether the ATM was Rho-Bank or third-party before choosing the applicable process. Do not file an ATM claim until this is known.
7. Resolve classification exactly:
   - Fraud suspected and physical/in-store card use: `card_present_fraud`.
   - Fraud suspected and online/phone use: `card_not_present_fraud`.
   - Unauthorized but fraud is not suspected: `unauthorized_transaction`.
   - Use the remaining documented category that directly matches the reported issue.
   - Use transaction types only from: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, `person_to_person`.
8. Determine provisional-credit eligibility. It is required only when all are true: reported within 60 days of the statement, category is unauthorized/fraud, ATM cash discrepancy, or duplicate charge; written statement is provided; and the checking account is open with no holds/restrictions. It is not required for the listed service/amount/ATM-deposit categories, where merchant contact is absent for a non-fraud claim, where PIN was voluntarily shared, or for a card-not-present claim on an account under 30 days old. Do not substitute transaction age for the statement-reporting test.
9. Run `scripts/assess_debit_dispute.py` with collected facts as a local consistency check. Resolve every reported error before filing.
10. Unlock and call `file_debit_card_transaction_dispute_6281` once per eligible transaction using all required arguments. Use dates in `MM/DD/YYYY`; use the actual positive dollar amount. Record each dispute's own mapped `card_action`.
11. Only after every dispute for a card is filed, perform the one actual card action at the highest severity across that card's disputes: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`. A keep-active outcome requires no card-action call. For a freeze outcome, unlock and use `freeze_debit_card_3892`; for a close/reissue outcome, use the normal available card closure/reissue tooling after verifying its required confirmation and card details. Never treat the filing metadata field as the action itself.
12. Tell the customer the filing result, disputed amount, card status/action, whether provisional credit is required/eligible, and applicable expected timing. Qualifying standard accounts receive provisional credit within 10 business days; accounts opened under 30 days may take 20 business days. With provisional credit, investigation normally has 45 business days, or 90 for international/POS outside the US/new accounts.

If a prerequisite fails, explain the specific limitation and do not file. If a tool returns an unknown/ambiguous result, do not repeat an action that may have succeeded; inspect status/history or escalate appropriately.

## Filing argument mapping

`file_debit_card_transaction_dispute_6281` requires:

```json
{
  "transaction_id": "matched transaction ID",
  "account_id": "linked open checking ID",
  "card_id": "matched debit card ID",
  "user_id": "verified cardholder ID",
  "dispute_category": "allowed category",
  "transaction_date": "MM/DD/YYYY",
  "discovery_date": "MM/DD/YYYY",
  "disputed_amount": 0.0,
  "transaction_type": "allowed transaction type",
  "card_in_possession": true,
  "pin_compromised": "yes_shared|yes_observed|no|unknown",
  "contacted_merchant": true,
  "police_report_filed": false,
  "written_statement_provided": true,
  "provisional_credit_eligible": true,
  "card_action": "mapped action"
}
```

Card-action mapping: fraud categories → `close_and_reissue`; `unauthorized_transaction` → `freeze_pending_investigation`; all other documented categories → `keep_active`.

## Local checker

`scripts/assess_debit_dispute.py` reads one JSON object from standard input and writes one JSON object to standard output. It performs no banking actions and does not replace runtime lookups or customer verification.

Input fields: `transaction_date`, `current_date` (both `MM/DD/YYYY`), `amount`, `category`, `transaction_type`, `account_status`, `account_has_holds`, `tier`, `open_dispute_count`, `written_statement_provided`, `contacted_merchant`, `pin_compromised`, `reported_within_60_days_of_statement`, `account_age_days`, and optional `card_in_possession`, `fraud_suspected`, `atm_network_known`.

Example invocation by an executor:

```sh
python3 scripts/assess_debit_dispute.py <<'JSON'
{"transaction_date":"MM/DD/YYYY","current_date":"MM/DD/YYYY","amount":10.0,"category":"duplicate_charge","transaction_type":"pin_purchase","account_status":"OPEN","account_has_holds":false,"tier":"Entry","open_dispute_count":0,"written_statement_provided":true,"contacted_merchant":true,"pin_compromised":"no","reported_within_60_days_of_statement":true,"account_age_days":31,"card_in_possession":true,"fraud_suspected":false}
JSON
```

Validate that `ready_to_file` is true, `errors` is empty, the returned category/action match the proposed filing, and any `provisional_credit_eligible` result is supported by known facts. `warnings` identify facts still requiring human/customer confirmation.
