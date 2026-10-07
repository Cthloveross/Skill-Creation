---
name: debit-card-dispute-filing
description: Verify a customer and file eligible debit-card transaction disputes, including duplicate charges, after validating the checking account, debit card, transaction, per-account open-dispute limit, and Regulation E provisional-credit conditions.
---

# Debit-card dispute filing

Use this skill for debit-card disputes involving unauthorized activity, fraud, ATM errors, duplicate charges, incorrect amounts, merchant issues, and recurring charges. It supports the executor in completing banking actions; it does not itself perform them.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For a debit-card dispute, verification, customer authority, account/card ownership, an OPEN linked checking account, transaction eligibility, account-specific dispute limit, and required dispute facts must be established before filing. Do not treat a profile lookup, a stated name, or an email alone as identity verification.

## Customer communication and fact collection

1. Before proceeding, give the Regulation E liability notice. Do not claim a particular band unless statement/reporting timing establishes it:
   - within 2 business days of the statement: maximum liability $50;
   - within 60 days of the statement: maximum liability $500;
   - after 60 days: unlimited liability and recovery may be unavailable.
2. Retrieve the profile using a customer-provided identifying value. Have the customer confirm at least two profile fields from date of birth, email, phone number, and address. Obtain the current timestamp and call `log_verification` only after two fields match.
3. Obtain each disputed charge's merchant or ATM, date, amount, error description, discovery date, card identifier, fraud assessment and channel where applicable, card possession, PIN-compromise status, merchant-contact result for non-fraud claims, and written-statement consent.
4. Record affirmative consent for the conversation to serve as the statement as `written_statement_provided: true`. Normalize PIN status exactly as `yes_shared`, `yes_observed`, `no`, or `unknown`.
5. For fraud above $500, ask whether a police report was filed and recommend one when it was not. For ATM disputes, establish whether the ATM was bank-owned or third-party; do not assume this from an ambiguous description.

If the conversation already contains completed identity verification and all customer facts, do not unnecessarily repeat them. Continue directly with the outstanding retrieval and filing prerequisites.

## Required retrieval sequence before any filing

Unlock each documented discoverable banking tool before calling it when the runtime requires unlocking. Perform the following checks for every selected checking account/card combination:

1. Retrieve customer accounts with `get_all_user_accounts_by_user_id_3847(user_id)`. Select only a customer-owned checking account that is `OPEN`. Preserve the account's tier/class information and any holds or restrictions.
2. Retrieve cards using `get_debit_cards_by_account_id_7823(account_id)`. Match the customer-supplied card identifier, and confirm its `account_id` and `user_id` match the selected account and verified customer. Do not select a closed historical card when an active matching card is available.
3. Retrieve the history with `get_bank_account_transactions_9173(account_id)`. Match a posted debit by transaction ID, account, date, amount, and merchant/ATM description. Transaction history is returned in **reverse chronological order**. Amounts are negative for debits, but the filing's `disputed_amount` is the positive absolute amount.
4. **Before filing**, retrieve existing disputes with `get_debit_dispute_status_7483(user_id)`. Count unresolved statuses only for the selected `account_id`: `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED`.
5. Enforce the per-account limit: Entry 2, Mid 3, Premium 4, Elite 5. Obtain the actual tier from returned account data or an approved account source; never infer a tier from an account nickname. Do not file if the applicable limit is reached.
6. Confirm the transaction is posted, is a debit of at least $1.00, occurred no more than 60 calendar days before filing, and is on the selected OPEN checking account linked to the selected debit card.

For duplicate charges, dispute only the earliest/first transaction. Determine chronology from the returned records, not from the customer's wording. Since history is reverse chronological, when otherwise-identical duplicate records appear in returned order, the later-listed record is the earlier transaction and is the one to file.

## Classification, provisional credit, and filing

Use exactly one supported dispute category:

- `unauthorized_transaction` only when a transaction was unauthorized but fraud is not suspected.
- `card_present_fraud` for suspected physical/in-store fraud.
- `card_not_present_fraud` for suspected online/phone fraud.
- `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` when directly supported by the facts.

Use exactly one transaction type: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.

Set `card_action` as follows:

| Category | card_action |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| ATM, duplicate, incorrect-amount, merchant, and recurring non-fraud categories | `keep_active` |

A duplicate charge is eligible for required provisional credit only when all applicable conditions are met: timely statement reporting, qualifying category, written statement, and an OPEN unrestricted account. A non-fraud customer who has not contacted the merchant may be encouraged to do so, but merchant contact is **not** a filing prerequisite. Record the truthful `contacted_merchant: false`; for that non-fraud situation, record `provisional_credit_eligible: false` because provisional credit is not required. Do not make filing wait for merchant contact.

After all preceding checks pass, call `file_debit_card_transaction_dispute_6281` with this complete schema:

```json
{
  "transaction_id": "matched earliest eligible transaction ID",
  "account_id": "selected checking account ID",
  "card_id": "matched debit card ID",
  "user_id": "verified customer ID",
  "dispute_category": "allowed category",
  "transaction_date": "MM/DD/YYYY",
  "discovery_date": "MM/DD/YYYY",
  "disputed_amount": 0.0,
  "transaction_type": "allowed transaction type",
  "card_in_possession": true,
  "pin_compromised": "yes_shared|yes_observed|no|unknown",
  "contacted_merchant": false,
  "police_report_filed": false,
  "written_statement_provided": true,
  "provisional_credit_eligible": false,
  "card_action": "keep_active|freeze_pending_investigation|close_and_reissue"
}
```

Use actual normalized facts rather than the illustrative booleans in the schema. For a non-fraud claim, `police_report_filed` remains a required boolean field even though a police report is not required.

## Post-filing card handling

The filing's `card_action` is metadata; complete the corresponding banking protection action separately when it is required. For several successful filings on one card, retain each filing's mapped action, then take only the most severe actual action once: `close_and_reissue` over `freeze_pending_investigation` over `keep_active`. Use `freeze_debit_card_3892` only for the aggregate freeze action. For `keep_active`, do not freeze or reissue the card. If a required close/reissue operation is unavailable, do not claim it occurred; escalate through an approved channel.

## Deterministic preflight helper

Run `scripts/validate_dispute.py` after retrieval and before the filing call when structured validation is useful. The script receives one JSON object on stdin and emits one JSON object on stdout. It makes no banking calls and does not file a dispute.

Required input fields are `now`, `identity_verified`, `authority_confirmed`, `user_id`, `account`, `card`, `transactions`, `open_disputes`, `account_tier`, `statement_reported_within_60_days`, and `candidate`. Dates use `MM/DD/YYYY`; `transactions` are the retrieved account records; and, for a duplicate, `candidate.duplicate_transaction_ids_earliest_first` must contain IDs in established earliest-first order.

Example executor input shape:

```json
{
  "now": "MM/DD/YYYY",
  "identity_verified": true,
  "authority_confirmed": true,
  "user_id": "retrieved-user-id",
  "account": {"account_id": "checking-id", "account_type": "checking", "status": "OPEN", "has_holds_or_restrictions": false, "date_opened": "MM/DD/YYYY"},
  "card": {"card_id": "card-id", "account_id": "checking-id", "user_id": "retrieved-user-id"},
  "transactions": [{"transaction_id": "transaction-id", "account_id": "checking-id", "date": "MM/DD/YYYY", "amount": -10.0, "status": "posted"}],
  "open_disputes": [],
  "account_tier": "Entry",
  "statement_reported_within_60_days": true,
  "candidate": {"transaction_id": "transaction-id", "dispute_category": "duplicate_charge", "discovery_date": "MM/DD/YYYY", "transaction_type": "pin_purchase", "card_in_possession": true, "pin_compromised": "no", "contacted_merchant": false, "police_report_filed": false, "written_statement_provided": true, "duplicate_transaction_ids_earliest_first": ["transaction-id"]}
}
```

Inspect `missing_or_invalid` and do not file unless `ready` is true. A ready result validates only the supplied records; it does not prove that banking actions have occurred.
