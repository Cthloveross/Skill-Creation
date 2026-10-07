---
name: debit-card-dispute-intake-and-filing
description: Safely intake, validate, file, and follow up on debit-card transaction disputes, including fraud, merchant, duplicate, and ATM disputes. Use when a verified customer asks to dispute one or more debit-card transactions.
---

# Debit Card Dispute Intake and Filing

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Use this workflow for debit-card disputes only. Do not file a claim merely from an opening request; collect and validate the required facts for each transaction. The customer may provide claims one at a time.

## 1. Verify and identify the relevant records

1. Verify identity by confirming two of the four identity fields (date of birth, email, phone number, address), then record the successful verification with `log_verification`. Do not expose stored values for confirmation; let the customer provide them.
2. Obtain the customer's account records with `get_all_user_accounts_by_user_id_3847(user_id)`.
3. For each selected checking account, obtain cards with `get_debit_cards_by_account_id_7823(account_id)` and match the customer-selected card using its last four digits, account ID, and user ID.
4. Obtain account activity with `get_bank_account_transactions_9173(account_id)`. Match the claimed transaction to an actual transaction ID, date, description, and amount. Transaction results are reverse chronological, so do not mistake display order for the earliest duplicate.
5. Obtain existing disputes with `get_debit_dispute_status_7483(user_id)`. Count only disputes whose `status` is `OPEN` for the same account. Limits are per account: Entry 2, Mid 3, Premium 4, Elite 5.
6. Confirm the selected account is a checking account and is `OPEN`, the card belongs to the verified user and linked account, and the transaction is at least $1.00 and occurred no more than 60 days ago. Do not file if a prerequisite fails.

## 2. Give mandatory disclosure and gather claim facts

Before filing, explain the unauthorized-activity liability disclosure applicable to the report timing:

- report within 2 business days: maximum liability $50;
- report within 60 days: maximum liability $500;
- report after 60 days: unlimited liability; the customer may not recover funds.

If the statement/report timing cannot be established, give all three disclosures and obtain the statement date or timing classification before representing an exact liability tier.

For every transaction, collect:

- transaction ID, date, description, and full transaction amount;
- the amount actually disputed (for a partial ATM cash dispense, this is the shortage, not necessarily the withdrawal total);
- discovery date (when the customer first noticed the error);
- the issue type and transaction channel;
- whether the customer still possesses the physical card;
- PIN status exactly as `yes_shared`, `yes_observed`, `no`, or `unknown`;
- whether the merchant was contacted for every non-fraud claim;
- agreement that the conversation may serve as a written statement, or another written-statement status;
- for suspected fraud exceeding $500, whether a police report was filed. If not, recommend one.

Map the facts exactly:

| Customer circumstance | `dispute_category` |
|---|---|
| Unauthorized but fraud is not suspected | `unauthorized_transaction` |
| Suspected fraud, physical/in-store card use | `card_present_fraud` |
| Suspected fraud, online or phone/card-not-present use | `card_not_present_fraud` |
| ATM gave too little or no cash | `atm_cash_discrepancy` |
| ATM deposit missing | `atm_deposit_not_credited` |
| Same charge appeared more than once | `duplicate_charge` |
| Amount differs from expected | `incorrect_amount` |
| Paid goods/services never received | `goods_services_not_received` |
| Charge continued after cancellation | `recurring_charge_after_cancellation` |

Use a matching `transaction_type`: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`. Do not classify fraud as ordinary unauthorized when fraud is suspected. For duplicate transactions, identify all matching duplicates and dispute the earliest transaction first; if their order cannot be determined, resolve that before filing a later duplicate.

For every ATM claim, identify the ATM as Rho-Bank or third-party. For Rho-Bank cash discrepancies, review the relevant account records/journal information before filing; if it confirms a discrepancy, provisional credit is immediate. For Rho-Bank deposit errors, retrieve images with `get_atm_deposit_images_8473` and compare them with the claimed deposit. For a third-party ATM, explain that a chargeback request is sent to the owner/network and may take up to 90 days. For a third-party ATM cash discrepancy over $200, explain that an Electronic Fund Transfer Error Resolution Affidavit will be sent to the registered email address, must be returned within 10 business days, and a false affidavit is a federal offense; missing it can cause denial.

## 3. Determine provisional-credit eligibility

Set `provisional_credit_eligible` to true only when all required conditions are met:

1. timely reporting within 60 days of the statement date;
2. category is `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`;
3. a written statement is provided; and
4. the linked checking account is OPEN and has no hold or restriction.

Do not mark it required when the category is `goods_services_not_received`, `recurring_charge_after_cancellation`, `atm_deposit_not_credited`, or `incorrect_amount`; when a non-fraud customer did not contact the merchant; when the PIN was voluntarily shared; or for card-not-present claims on accounts under 30 days old. Do not infer timely reporting from transaction date alone: use statement/report timing.

For qualifying claims, the temporary credit is the full disputed amount, subject to a late-reporting liability offset. Standard accounts require it within 10 business days; accounts opened less than 30 days require it within 20 business days. A qualifying third-party ATM dispute must also be handled under its stated 10-business-day provisional-credit requirement. Investigation is generally 45 business days after provisional credit, or 90 days for international transactions, out-of-US merchant POS transactions, or new accounts.

## 4. Validate and file

Optionally run `scripts/dispute_plan.py` before filing. It is a deterministic validator and planner; it does not call banking tools and does not replace review of source records.

The script receives one JSON object on stdin and emits one JSON object on stdout.

Input schema (all values are runtime records, not hardcoded data):

```json
{
  "user_id": "string",
  "verified": true,
  "current_date": "MM/DD/YYYY",
  "accounts": [{"account_id":"string","account_type":"checking","account_class":"Entry Tier","status":"OPEN","date_opened":"MM/DD/YYYY","has_holds_or_restrictions":false}],
  "cards": [{"card_id":"string","account_id":"string","user_id":"string","status":"ACTIVE"}],
  "transactions": [{"transaction_id":"string","account_id":"string","date":"MM/DD/YYYY","amount":-12.34,"type":"debit_card_purchase","status":"posted"}],
  "existing_disputes": [{"account_id":"string","status":"OPEN"}],
  "claims": [{
    "transaction_id":"string", "account_id":"string", "card_id":"string",
    "dispute_category":"duplicate_charge", "transaction_type":"signature_purchase",
    "discovery_date":"MM/DD/YYYY", "disputed_amount":12.34,
    "card_in_possession":true, "pin_compromised":"no", "contacted_merchant":true,
    "police_report_filed":false, "written_statement_provided":true,
    "timely_reported_within_60_statement_days":true,
    "atm_owner":"not_applicable",
    "duplicate_group_transaction_ids": []
  }]
}
```

`has_holds_or_restrictions`, timely-reporting status, and ATM owner must be supplied from the case record rather than guessed. The output contains claim-specific `errors`, `warnings`, a safe filing payload when valid, eligibility reasoning, and the one post-filing card action per card. Treat any error as a block on that claim. The script validates dates using the stated `MM/DD/YYYY` format and accepts account-class spelling variants such as `ENTRY` and `Entry Tier`.

For each valid claim, call `file_debit_card_transaction_dispute_6281` with exactly these fields from the validated claim and source records:

```text
transaction_id, account_id, card_id, user_id, dispute_category,
transaction_date, discovery_date, disputed_amount, transaction_type,
card_in_possession, pin_compromised, contacted_merchant,
police_report_filed, written_statement_provided,
provisional_credit_eligible, card_action
```

Record each claim's own `card_action`:

- `card_present_fraud` and `card_not_present_fraud` → `close_and_reissue`
- `unauthorized_transaction` → `freeze_pending_investigation`
- all other permitted categories → `keep_active`

## 5. Apply one most-severe card action after all filings

After all intended claims for the same card have been filed, perform the single most severe action across them: `close_and_reissue` outranks `freeze_pending_investigation`, which outranks `keep_active`. Keep each filing payload's individual action unchanged.

For `freeze_pending_investigation`, re-check verified ownership and confirm the card is ACTIVE, then call `freeze_debit_card_3892(card_id)`. Explain that new and recurring transactions will decline, while already-authorized pending transactions may still settle.

For `close_and_reissue`, follow the debit-card closing workflow: confirm verified ownership, eligible card status, and closure prerequisites, then call `close_debit_card_4721` with the documented fraud-suspected reason. Fraud-suspected closure bypasses the minimum-age restriction, but do not invent a bypass for other documented prerequisites. If a replacement is requested, follow the replacement eligibility, waiting-period, delivery/design choice, and fee-disclosure workflow before ordering; use the runtime's documented order-tool signature rather than guessing unsupported arguments. Inform the customer that any applicable replacement fees are charged to the linked checking account.

## 6. Recurring charges and follow-up

A dispute addresses charges that already occurred. If the customer also wants to stop all future recurring payments, after the past-charge dispute call `set_debit_card_recurring_block_7382(card_id, block_recurring=true)` only after explaining it blocks all recurring payments on the card, takes effect within 24 hours, does not cancel merchant subscriptions, and leaves one-time purchases unaffected.

Confirm each filing, its category, amount, written-statement status, expected provisional-credit handling, required documents, and the actual card action. For later status requests, use `get_debit_dispute_status_7483(user_id)`. Escalate to a supervisor if provisional-credit or investigation timelines appear overdue.
