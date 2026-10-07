---
name: debit-card-dispute-filing
version: 1.2.0
description: File eligible debit-card transaction disputes, determine conservative provisional-credit metadata, and complete the required post-filing debit-card protection action. Use for debit-card duplicate charges, incorrect amounts, ATM errors, unauthorized activity, and suspected debit-card fraud.
---

# Debit Card Dispute Filing

Use this Skill for debit-card disputes, including debit-card purchases and debit-card-linked P2P activity. It supports multiple claims across checking accounts and cards. Do not use it for credit-card disputes.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

## Collect and preserve claim facts

For each claim, separately record the transaction, the customer’s explanation, transaction and discovery dates, full posted amount, requested amount, payment method, card possession, PIN status, merchant-contact answer, and written-statement answer. Do not copy a payment method or other fact from one claim to another.

Obtain or confirm:

- Verified identity and authority. Match at least two profile fields and create the `log_verification` audit record before a banking write.
- The matching customer-owned debit card, linked `OPEN` checking account, and posted debit transaction.
- `card_in_possession`, and a PIN answer of `yes_shared`, `yes_observed`, `no`, or `unknown`.
- Merchant-contact information for non-fraud claims. It is required filing information, but lack of contact alone does not make an otherwise eligible non-fraud claim ineligible.
- A written statement. The customer can authorize use of their statements in the conversation.
- For fraud exceeding $500, whether a police report was filed; recommend one if absent but do not block a filing solely on that basis.
- ATM operator classification for ATM claims.

For unauthorized activity, explain Regulation E reporting exposure before filing: reports within two business days may limit liability to $50; within 60 days of the statement may limit it to $500; after 60 days liability may be unlimited. Do not invent a statement date or liability amount.

### Payment-method accuracy

Use the customer’s stated payment method for the individual transaction:

| Customer fact | `transaction_type` |
|---|---|
| In-store purchase with PIN | `pin_purchase` |
| In-store purchase with signature | `signature_purchase` |
| Online or phone/card-not-present purchase | `online_purchase` |
| Cash withdrawal | `atm_withdrawal` |
| Deposit at ATM | `atm_deposit` |
| Subscription/autopay | `recurring_payment` |
| P2P transfer, including EveryonePay | `person_to_person` |

For example, an incorrect-amount claim described as a signature purchase must be filed as `signature_purchase`, even if another claim on the same card was a PIN purchase. For an overcharge, dispute only the documented erroneous difference, not automatically the full posted debit.

## Retrieval and eligibility sequence

1. Locate the customer profile and compare the supplied identity answers with profile data. Obtain the current time and, after two fields match, call `log_verification` with the complete profile fields and timestamp.
2. Unlock and call `get_all_user_accounts_by_user_id_3847(user_id)`. Identify customer-owned checking accounts with status `OPEN`.
3. For each relevant account, unlock and call `get_debit_cards_by_account_id_7823(account_id)`. Match card last four, linked account, and `user_id`.
4. Unlock and call `get_bank_account_transactions_9173(account_id)`. Match each requested merchant/date/debit amount and retain the transaction ID. Inspect the complete response, including statuses, before a later card closure.
5. Unlock and call `get_debit_dispute_status_7483(user_id)`. Count unresolved disputes by account. `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED` consume capacity.
6. Check each proposed filing immediately before the write. File every supported selected claim; do not transfer merely because an optional fact cannot improve the decision.

A filing requires verified ownership, a linked `OPEN` checking account, a matching debit transaction of at least $1, a positive disputed amount no greater than the posted debit, and a transaction no more than 60 days old.

### Capacity and prioritization

Open-dispute caps are per account: Entry 2, Mid 3, Premium 4, Elite 5. Use the retrieved `account_class` where it maps to a published tier and include earlier successful filings in the same batch.

Where no tier mapping is available, the published minimum cap of two permits a total of fewer than two concurrent unresolved claims on that account. Do not call unknown tier data a blanket blocker. Conversely, do not require or attempt an additional claim when the existing and newly filed claims have already reached that conservative minimum; explain the capacity uncertainty and escalate a customer-requested remaining claim with its complete facts. Do not withdraw or swap an existing dispute without a documented procedure and customer authorization.

When more eligible claims compete for capacity, honor an explicit customer priority where capacity is demonstrable.

### Duplicate and category rules

File exactly one duplicate-charge claim for a duplicate group. The policy calls for the earliest transaction. Transaction history is reverse chronological; use an observable date and response ordering when available. If two records are otherwise indistinguishable, select one according to the returned ordering without claiming that its opaque ID is demonstrably earliest. Never file both copies.

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
| Suspected fraud at a physical merchant | `card_present_fraud` |
| Suspected online/phone/P2P fraud | `card_not_present_fraud` |

Do not use `unauthorized_transaction` where fraud is suspected.

## Provisional-credit metadata

Every filing must include `provisional_credit_eligible`.

Set it to `true` only when all required facts are established: reported within 60 days of the statement date, an eligible category (`unauthorized_transaction`, either fraud category, `atm_cash_discrepancy`, or `duplicate_charge`), a written statement, and an `OPEN` checking account explicitly known to have no holds or restrictions. A customer discovery date alone does not establish statement-date timeliness.

Set it to `false` if eligibility is excluded or cannot be established. It is not required for `incorrect_amount`, goods/services, recurring-cancellation, or ATM-deposit claims; it is also not required if the customer shared a PIN, merchant contact was absent for a non-fraud claim, or the claim is a new-account card-not-present transaction. Do not promise provisional credit unless the required facts are established.

## Filing procedure

Use `scripts/assess_debit_disputes.py` as a deterministic, side-effect-free check of proposal data, duplicate selection, capacity, card-action metadata, payment-method consistency, and provisional-credit eligibility. It does not replace live tool checks.

For every eligible selected claim, unlock and call `file_debit_card_transaction_dispute_6281` with all fields:

```json
{
  "transaction_id": "matched transaction ID",
  "account_id": "matched checking account ID",
  "card_id": "matched debit card ID",
  "user_id": "verified user ID",
  "dispute_category": "permitted category",
  "transaction_date": "MM/DD/YYYY",
  "discovery_date": "MM/DD/YYYY",
  "disputed_amount": 0.0,
  "transaction_type": "the individual claim's stated payment method",
  "card_in_possession": true,
  "pin_compromised": "no",
  "contacted_merchant": false,
  "police_report_filed": false,
  "written_statement_provided": true,
  "provisional_credit_eligible": false,
  "card_action": "keep_active"
}
```

Set card-action metadata exactly: both fraud categories use `close_and_reissue`; `unauthorized_transaction` uses `freeze_pending_investigation`; all other categories use `keep_active`. Preserve each tool result and never state that a failed call filed a claim.

## Required actual card action

After all intended filings for each card, perform one actual action at the highest severity: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`. Metadata alone does not secure the card.

- For `freeze_pending_investigation`, verify ownership and `ACTIVE` status, explain that new and recurring charges will decline while already-authorized items may settle, then unlock and call `freeze_debit_card_3892(card_id)`.
- For fraud `close_and_reissue`, verify ownership and an `ACTIVE` or `PENDING` card. Check the retrieved transaction history for pending/processing transactions and pending refunds. If none exist, after the fraud filing unlock and call `close_debit_card_4721(card_id, reason="fraud_suspected")`. Fraud bypasses the 14-day card-age requirement but not pending-transaction or pending-refund checks.
- Explain that closure is permanent, recurring payments need new payment information, and changing online-banking credentials is recommended after suspected fraud.
- Replacement ordering is separate. Before `order_debit_card_5739`, review replacement history, tier limit, and waiting period; obtain delivery choice, design, confirmed address, balance for automatic fees, and explicit fee confirmation. Do not order without those selections.

If an unresolved, customer-prioritized claim cannot be filed because available capacity is not demonstrable, transfer once using `transfer_to_human_agents` with `reason="specialized_department_required"`. State the merchant, amount, date, intended fraud/category classification, card/account context, existing open dispute(s), newly filed claim(s), and the capacity limitation. Do not imply that the claim was filed.

## Script interface

`scripts/assess_debit_disputes.py` reads one JSON object from stdin and emits one JSON object to stdout using only the Python standard library. It makes no banking calls.

Required input fields are `current_date` (`MM/DD/YYYY`), `user_verified` (boolean), `user_id`, `accounts`, `cards`, `transactions`, `existing_disputes`, and `proposed_disputes`. Transactions require `transaction_id`, `account_id`, `date`, and `amount`; `history_index` is optional, where zero is the most recent item in a reverse-chronological response. Proposals contain the filing fields used below, plus `fraud_suspected`, `reported_within_60_days_of_statement`, and optional `duplicate_group`. Optional `payment_method` accepts `pin`, `signature`, `online`, `atm_withdrawal`, `atm_deposit`, `recurring`, or `person_to_person` and is checked against `transaction_type`.

Example input:

```json
{"current_date":"MM/DD/YYYY","user_verified":true,"user_id":"runtime user","accounts":[],"cards":[],"transactions":[],"existing_disputes":[],"proposed_disputes":[]}
```

Review each assessment’s `eligible_to_file`, `blockers`, `warnings`, `card_action`, and `provisional_credit_eligible`; validate live data again immediately before each write.
