---
name: debit-card-dispute-filing
version: 1.1.0
description: File eligible debit-card transaction disputes and perform required post-filing card protection actions. Use for duplicate charges, incorrect amounts, ATM errors, unauthorized debit activity, and suspected debit-card fraud.
---

# Debit Card Dispute Filing

Use this Skill for debit-card disputes only, including debit-card purchases and debit-card-linked P2P activity. It supports multiple disputes across checking accounts and cards. Do not use it for credit-card disputes.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Required information

Before a filing, obtain or confirm:

- Verified customer identity and authority. Match at least two profile fields, obtain the current time, and create the `log_verification` audit record before any banking write.
- The linked `OPEN` checking account, debit card, and posted debit transaction.
- Transaction date, discovery date, full transaction amount, and requested disputed amount.
- A clear explanation, correct category, and transaction type.
- Whether the customer retains the physical card and PIN-compromise status: `yes_shared`, `yes_observed`, `no`, or `unknown`.
- Whether the merchant was contacted for non-fraud claims. This is required filing information, but its absence alone is not a reason to decline an otherwise eligible non-fraud filing.
- A written-statement answer. The customer may authorize use of their statements in the conversation.
- For fraud above $500, whether a police report was filed. Recommend a report if absent, but do not block filing solely for that reason.
- ATM operator classification for ATM claims.

For unauthorized activity, explain Regulation E exposure before filing: reported within two business days may limit liability to $50; within 60 days of the statement may limit it to $500; after 60 days liability may be unlimited. Do not infer a statement date that is unavailable.

## Retrieval and eligibility sequence

1. Locate the user and compare supplied identity answers to the profile. After two fields match, call `log_verification` with all profile fields and the current timestamp.
2. Unlock and call `get_all_user_accounts_by_user_id_3847(user_id)`. Select checking accounts owned by the customer with status `OPEN`.
3. For each relevant account, unlock and call `get_debit_cards_by_account_id_7823(account_id)`. Match the card’s last four digits, account, and `user_id`.
4. Unlock and call `get_bank_account_transactions_9173(account_id)`. Match merchant, date, debit amount, account, and transaction ID. This response contains all posted and pending transactions; inspect it before any card closure.
5. Unlock and call `get_debit_dispute_status_7483(user_id)`. Count unresolved disputes per account. `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED` consume capacity.
6. Complete practical read-only checks before writes, then file supported claims rather than transferring merely because some optional or unavailable data cannot improve a decision.

A claim requires verified ownership, an `OPEN` linked checking account, a matching debit-card transaction of at least $1, a positive amount no greater than the posted debit, and a transaction no more than 60 days old.

### Dispute capacity

Caps are per account: Entry 2, Mid 3, Premium 4, Elite 5. Use the observed `account_class` when available and account for earlier filings in the same batch.

If the precise tier mapping is unavailable but the number of existing open disputes plus proposed filings is below the published universal minimum cap of 2, the claim has demonstrable capacity. File up to that conservative minimum; do not treat missing tier detail as a blocker. If more claims compete than conservative capacity permits, honor an explicit customer priority and explain which remaining claims need follow-up.

### Duplicate and classification rules

For a duplicate group, file exactly one dispute against the earliest transaction. Do not make the customer choose between identical duplicate records. Use transaction date; for same-date records with no timestamps, preserve the transaction-history record order and select the chronologically earliest record (the later item in a reverse-chronological response). Never file both copies.

Use exactly one category:

| Situation | Category |
|---|---|
| Unauthorized, fraud not suspected | `unauthorized_transaction` |
| ATM paid too little/no cash | `atm_cash_discrepancy` |
| ATM deposit missing | `atm_deposit_not_credited` |
| Same purchase charged more than once | `duplicate_charge` |
| Charged more or less than intended | `incorrect_amount` |
| Goods/services not received | `goods_services_not_received` |
| Recurring charge after cancellation | `recurring_charge_after_cancellation` |
| Suspected fraud at physical merchant | `card_present_fraud` |
| Suspected online/phone fraud | `card_not_present_fraud` |

Do not use `unauthorized_transaction` when fraud is suspected. Use one transaction type: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`. For an overcharge, file only the erroneous difference, not automatically the entire posted debit.

## Provisional credit

Always include `provisional_credit_eligible` in every filing payload. Set it to `true` only when required eligibility is established: report within 60 days of the statement date, an eligible category (`unauthorized_transaction`, either fraud category, `atm_cash_discrepancy`, or `duplicate_charge`), written statement, and an `OPEN` account explicitly known to have no holds or restrictions.

Set it to `false` when eligibility is excluded or cannot be established from available statement-date/account-standing facts. In particular, it is not required for `incorrect_amount`, goods/services, recurring-cancellation, or ATM-deposit claims; it is also not required where the customer voluntarily shared a PIN, where non-fraud merchant contact was absent, or for a new-account card-not-present claim. Do not promise provisional credit when its requirement cannot be established.

## Filing procedure

Run `scripts/assess_debit_disputes.py` to produce deterministic capacity, duplicate, action, and provisional-credit advice. It is advisory only; live tool lookups remain authoritative.

For every eligible selected claim, unlock and call `file_debit_card_transaction_dispute_6281` with every field below:

```json
{
  "transaction_id": "matched transaction ID",
  "account_id": "matched checking account ID",
  "card_id": "matched card ID",
  "user_id": "verified user ID",
  "dispute_category": "permitted category",
  "transaction_date": "MM/DD/YYYY",
  "discovery_date": "MM/DD/YYYY",
  "disputed_amount": 0.0,
  "transaction_type": "permitted type",
  "card_in_possession": true,
  "pin_compromised": "no",
  "contacted_merchant": false,
  "police_report_filed": false,
  "written_statement_provided": true,
  "provisional_credit_eligible": false,
  "card_action": "keep_active"
}
```

Map filing metadata exactly: both fraud categories → `close_and_reissue`; `unauthorized_transaction` → `freeze_pending_investigation`; all other categories → `keep_active`. Preserve each filing result and never state that a failed call filed a dispute.

## Required actual card action

After all intended filings for each card, perform one actual action at the highest severity: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`. Filing metadata alone does not secure a card.

- For `freeze_pending_investigation`, verify ownership and `ACTIVE` card status, explain that new and recurring charges decline while pending items may settle, then unlock and call `freeze_debit_card_3892(card_id)`.
- For fraud `close_and_reissue`, verify ownership and that the card is `ACTIVE` or `PENDING`. Check the retrieved complete transaction history for pending/processing transactions and pending refunds. If none are present, unlock and call `close_debit_card_4721(card_id, reason="fraud_suspected")` after the fraud filing. Fraud bypasses the 14-day card-age requirement, but not pending-transaction or pending-refund checks.
- Explain that closure permanently deactivates the card and recurring payments need updating. Recommend changing online-banking credentials after suspected fraud.
- A replacement is a separate order. Before `order_debit_card_5739`, review tier replacement limits/history and waiting period, then obtain delivery choice, design, confirmed address, balance for automatic fees, and explicit fee confirmation. Do not order a replacement without those choices.

## Script interface

`scripts/assess_debit_disputes.py` reads one JSON object from stdin and emits one JSON object to stdout, using only the Python standard library. It does not call banking tools.

Input fields: `current_date` (`MM/DD/YYYY`), `user_verified` (boolean), `user_id`, `accounts`, `cards`, `transactions`, `existing_disputes`, and `proposed_disputes`. Transactions require `transaction_id`, `account_id`, `date`, `amount`, and optional `history_index` where zero is most recent. Proposals require IDs, category, amount, discovery date, transaction type, PIN/contact/written-statement answers, `fraud_suspected`, `reported_within_60_days_of_statement`, and optional `duplicate_group`.

Example:

```json
{"current_date":"MM/DD/YYYY","user_verified":true,"user_id":"runtime user","accounts":[],"cards":[],"transactions":[],"existing_disputes":[],"proposed_disputes":[]}
```

Review each output’s `eligible_to_file`, `blockers`, `warnings`, `card_action`, and `provisional_credit_eligible`. Validate the live data immediately before each write action.
