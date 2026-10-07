---
name: debit-card-dispute-intake-and-filing
description: Verify a customer and safely file eligible debit-card transaction disputes, determine Regulation E provisional-credit eligibility, and perform the required aggregate card security action. Use for debit-card purchases, ATM events, recurring payments, and P2P debit-card disputes.
---

# Debit Card Dispute Intake and Filing

Use this Skill when a verified customer asks to dispute one or more debit-card transactions. It supports the normal banking tools; its Python helper only evaluates supplied facts and **never files, freezes, or closes a card**.

## Required disclosures and intake

Before filing, explain the Regulation E unauthorized-transaction liability exposure:

- Reported within 2 business days of the statement: maximum $50 liability.
- Reported within 60 days of the statement: maximum $500 liability.
- Reported after 60 days: potentially unlimited liability and funds may not be recoverable.

Collect or confirm, for every claimed transaction:

- Merchant/ATM/recipient, date, full transaction amount, claimed amount, and reason.
- Date first noticed, relevant statement date (needed to assess reporting timeliness), and transaction channel.
- Whether fraud is suspected; for fraud, whether the transaction was physical/in-store or online/phone/card-not-present. P2P fraud normally uses `card_not_present_fraud` with transaction type `person_to_person`.
- Whether the physical card remains in the customer's possession and PIN-compromise choice: `yes_shared`, `yes_observed`, `no`, or `unknown`.
- For non-fraud merchant disputes, whether the customer contacted the merchant.
- For suspected fraud over $500, whether a police report was filed; if not, recommend one, but do not treat this as a filing blocker.
- Consent to use the conversation as the written statement. Set `written_statement_provided` true only when the customer agrees.
- For an ATM claim, whether it was a Rho-Bank ATM or a third-party ATM, because the processes differ.

For duplicate charges, identify all matching entries and dispute the earliest (first) transaction rather than a later duplicate.

## Verify and retrieve live banking facts

1. Identify the customer from their supplied identifier. Verify at least two profile fields (DOB, address, email, or phone) against the retrieved profile.
2. Obtain the current time and call `log_verification` with the complete retrieved profile and timestamp after successful verification.
3. Unlock and use `get_all_user_accounts_by_user_id_3847`. Select the claimed OPEN checking account, retain its account class and date opened, and reject a savings, closed, or restricted/held account.
4. Unlock and use `get_debit_cards_by_account_id_7823` for each relevant checking account. Match the customer, account, and supplied card ending. Keep the exact `card_id`.
5. Unlock and use `get_bank_account_transactions_9173` for each claimed account. Match the exact transaction ID, date, amount, and description. Transaction history is reverse chronological; inspect the complete result when selecting the earliest duplicate.
6. Unlock and use `get_debit_dispute_status_7483` once for the customer. Count unresolved disputes per account before filing. The maximum open disputes are Entry 2, Mid 3, Premium 4, and Elite 5. Resolved and closed disputes do not consume the open-dispute capacity.

Do not guess IDs, transaction details, account tier, card ownership, account status, or a missing statement date. Ask for or retrieve the missing fact. Do not file transactions below $1.00 or more than 60 calendar days old.

## Classification and filing payload

Choose exactly one permitted category:

- Fraud suspected: `card_present_fraud` for physical/in-store use and `card_not_present_fraud` for online, phone, or card-not-present use.
- Unauthorized but fraud is not suspected: `unauthorized_transaction` only.
- ATM cash error: `atm_cash_discrepancy`; ATM deposit missing: `atm_deposit_not_credited`.
- Other cases: `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation`.

Use the corresponding transaction type: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`. For an incorrect amount, the disputed amount is normally the erroneous portion, not necessarily the full posted transaction.

Set each filing's metadata independently:

| Category | `card_action` metadata |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| all other allowed categories | `keep_active` |

Assess provisional credit for each claim. It is required only when all applicable conditions hold: reporting is within 60 days of the statement, category is one of `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`; a written statement exists; and the linked checking account is OPEN without holds/restrictions. It is not required for the other categories, when a non-fraud customer has not contacted the merchant, when `pin_compromised` is `yes_shared`, or for a card-not-present claim on an account younger than 30 days. Required credit is the full disputed amount, subject to any applicable late-report liability offset.

Use `scripts/dispute_plan.py` after normalizing live facts to validate a batch and obtain candidate tool arguments. It does not replace the live checks above. See its input schema below.

For every eligible claim, unlock `file_debit_card_transaction_dispute_6281` and call it with the exact `filing_payload` produced or independently assembled from verified facts. Record the result. If a filing outcome is indeterminate, do not repeat it blindly; retrieve dispute status before deciding whether another action is appropriate.

## Perform the actual card action after all filings

The filing's `card_action` is metadata only. Group successful filings by card and execute only the most severe action once per card:

`close_and_reissue` > `freeze_pending_investigation` > `keep_active`.

- For `keep_active`, no card action tool is needed.
- For a freeze, confirm the card is ACTIVE and belongs to the verified customer, then unlock and call `freeze_debit_card_3892(card_id)`.
- For closure/reissue, obtain the customer's authorization if not already provided. Confirm ownership and ACTIVE or PENDING card status. A fraud-suspected closure bypasses only the 14-day card-age requirement; pending transactions and pending refunds still require the closure procedure to be satisfied. Unlock and call `close_debit_card_4721(card_id, reason='fraud_suspected')` only when eligible. Do not substitute a freeze when closure is required but blocked; explain the blocker and follow escalation/process requirements.

Tell the customer which disputes were filed, the card-protection action taken or blocking condition, whether provisional credit is required/eligible, and relevant timeline: credit within 10 business days (20 for accounts younger than 30 days); investigation generally 45 business days with provisional credit, or 90 for international/POS outside the US or new accounts. Explain that provisional credit can be reversed with at least three business days' written notice if the investigation finds against the customer.

## Helper input/output

Run the helper with JSON on stdin:

```json
{
  "filing_date": "MM/DD/YYYY",
  "user_id": "string",
  "accounts": [{"account_id":"string","account_type":"checking","account_class":"Entry Tier","status":"OPEN","date_opened":"MM/DD/YYYY","has_holds_or_restrictions":false}],
  "cards": [{"card_id":"string","account_id":"string","user_id":"string","status":"ACTIVE","date_issued":"MM/DD/YYYY","pending_transactions":false,"pending_refunds":false}],
  "open_disputes": [{"account_id":"string","status":"OPEN"}],
  "claims": [{"transaction_id":"string","account_id":"string","card_id":"string","transaction_date":"MM/DD/YYYY","transaction_amount":10.0,"disputed_amount":10.0,"discovery_date":"MM/DD/YYYY","statement_date":"MM/DD/YYYY","dispute_category":"duplicate_charge","transaction_type":"pin_purchase","card_in_possession":true,"pin_compromised":"no","contacted_merchant":true,"police_report_filed":false,"written_statement_provided":true,"duplicate_group":"optional-group","duplicate_sequence":1}]
}
```

`transaction_amount` may be a negative ledger debit; validation uses its absolute value. `duplicate_group` and `duplicate_sequence` let the helper retain only the earliest selected duplicate. Output has `claims` with errors/warnings, a `filing_payload` only for validated and capacity-eligible claims, and `card_actions` with the one actual action recommendation per card. A missing `statement_date` does not prevent ordinary filing but prevents a definitive provisional-credit/timeliness determination, so resolve it before setting a definitive provisional-credit flag.
