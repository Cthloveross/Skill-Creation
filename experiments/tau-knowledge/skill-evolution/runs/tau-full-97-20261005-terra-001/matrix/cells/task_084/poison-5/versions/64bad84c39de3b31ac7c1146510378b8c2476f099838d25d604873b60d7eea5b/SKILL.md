---
name: debit-card-dispute-filing
description: File eligible debit-card transaction disputes after identity verification and account, card, transaction, dispute-limit, and Regulation E checks. Use for unauthorized/fraud, ATM, duplicate, incorrect-amount, merchant, and recurring debit-card dispute requests.
---

# Debit-card dispute filing

Use this workflow to collect facts, validate eligibility, file one dispute per eligible transaction, determine provisional-credit eligibility, and perform the required post-filing card protection action. Do not treat a profile lookup, name, or email alone as identity verification.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this workflow, identity verification, customer authority/account ownership, the OPEN checking-account/card relationship, transaction match, dispute limit, transaction age, and required customer confirmations are mandatory before filing. Inspect balance, fees, cutoff, and confirmation requirements where applicable; do not invent requirements not supplied by the banking policy.

## Start and customer communication

1. Before proceeding, explain the Regulation E liability notice without asserting a band that is not established from the statement/reporting dates:
   - reported within 2 business days of the statement: maximum liability $50;
   - reported within 60 days of the statement: maximum liability $500;
   - reported after 60 days: unlimited liability and recovery may be unavailable.
2. Verify identity by having the customer confirm at least two of date of birth, email, phone number, and address against the customer profile. Retrieve the profile using an available identifying value, confirm the fields rather than reading sensitive values unnecessarily, get the current timestamp, and call `log_verification` only after two fields match.
3. Confirm the customer is authorized for the relevant checking account. Retrieve the customer’s accounts using `get_all_user_accounts_by_user_id_3847`; select the requested checking account from that customer-scoped result. The account must be `OPEN`, with no holds or restrictions for provisional-credit eligibility.
4. Gather each disputed charge separately: merchant/ATM, claimed date and amount, what happened, discovery date, card, fraud suspicion and channel, card possession, PIN-compromise response, merchant-contact result for non-fraud claims, and written-statement consent. Ask whether the customer agrees the conversation may serve as their written statement. For fraud above $500, ask whether a police report was filed and recommend one if it was not.
5. For ATM claims, establish whether the ATM was a Rho-Bank ATM or third-party ATM and follow the applicable ATM process. Do not assume the ATM owner from a vague description.

Use only these exact normalized PIN values: `yes_shared`, `yes_observed`, `no`, or `unknown`. Use the customer’s affirmative agreement to the conversation as the written statement as `written_statement_provided: true`.

## Retrieval and eligibility checks

After verification and before filing, unlock/use the documented banking tools as needed:

1. Call `get_debit_cards_by_account_id_7823(account_id)` and identify the card by the customer-provided last four digits. Confirm the returned `account_id` and `user_id` match the selected account and verified customer. Do not select an old card merely because it has matching historical details.
2. Call `get_bank_account_transactions_9173(account_id)`. Match the exact posted debit transaction by date, amount, and merchant/ATM description. Its amount is normally negative; submit the positive absolute dollar amount as `disputed_amount`. Do not dispute a pending item unless policy specifically permits it.
3. Call `get_debit_dispute_status_7483(user_id)`. Count unresolved disputes for the selected `account_id`: `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED`. The maximum is per account: Entry 2, Mid 3, Premium 4, Elite 5. Obtain the tier from account data or an approved account source; do not infer it from an account name.
4. Confirm the target transaction is at least $1.00 and no more than 60 calendar days old at filing. Confirm the debit card is linked to the selected OPEN checking account.
5. For a duplicate group, file the earliest (first) duplicate transaction only. If ordering cannot be established from returned records, do not guess; obtain the needed transaction detail before filing.

A non-fraud customer who has not contacted the merchant should be encouraged to do so. Record the truthful `contacted_merchant` value; lack of merchant contact prevents required provisional credit for non-fraud claims, but is not a reason to falsify the field.

## Classification and filing payload

Choose exactly one category:

- `unauthorized_transaction`: unauthorized but fraud is **not** suspected.
- `card_present_fraud`: suspected fraud at a physical/in-store transaction.
- `card_not_present_fraud`: suspected fraud online or by phone.
- `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` as directly supported by the facts.

Choose exactly one transaction type: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`. Do not use `unauthorized_transaction` for suspected fraud.

Set `card_action` exactly as follows:

| Category | card_action |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| all ATM, duplicate, amount, merchant, and recurring non-fraud categories | `keep_active` |

Determine `provisional_credit_eligible` as true only when all are true: reporting within 60 days of the relevant statement, category is `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`; a written statement was provided; and the checking account is OPEN without holds/restrictions. It is not required for excluded categories, a non-fraud dispute without merchant contact, voluntary PIN sharing (`yes_shared`), or a card-not-present claim on an account less than 30 days old. Record false when a known disqualifier applies; if facts needed to determine it are unknown, collect them rather than representing eligibility as established.

When eligible, provisional credit is for the full disputed amount subject to any $50/$500 late-report liability offset. It is due within 10 business days (20 for an account open fewer than 30 days). The investigation is normally 45 business days with provisional credit, or 90 for international transactions, merchant POS outside the US, or new accounts. This workflow only records eligibility unless a separate approved credit-posting tool is available.

Unlock and call `file_debit_card_transaction_dispute_6281` with this exact schema after all checks pass:

```json
{
  "transaction_id": "string from transaction history",
  "account_id": "selected open checking account",
  "card_id": "matched debit card",
  "user_id": "verified customer",
  "dispute_category": "one allowed category",
  "transaction_date": "MM/DD/YYYY",
  "discovery_date": "MM/DD/YYYY",
  "disputed_amount": 0.0,
  "transaction_type": "one allowed type",
  "card_in_possession": true,
  "pin_compromised": "yes_shared|yes_observed|no|unknown",
  "contacted_merchant": false,
  "police_report_filed": false,
  "written_statement_provided": true,
  "provisional_credit_eligible": false,
  "card_action": "keep_active|freeze_pending_investigation|close_and_reissue"
}
```

For several disputes on one card, each filing retains its own mapped `card_action`. After all successful filings, execute the single most severe actual action for that card: `close_and_reissue` over `freeze_pending_investigation` over `keep_active`. The known freeze operation is `freeze_debit_card_3892`; use it only when the selected aggregate action is freeze. For close/reissue, use an approved normal banking operation that is available and documented. If the required card-action tool is unavailable, do not claim the action occurred; escalate through the approved channel.

## Current-case resumption pattern

If a conversation ended before banking tools were called, resume from verified facts but repeat any uncompleted prerequisite. In particular, a customer who only supplied a name and email has not completed two-field identity verification. Ask them to confirm a second profile field, log verification, then retrieve accounts, card records, transactions, and open disputes. A stated duplicate, card possession, PIN status, purchase method, merchant-contact result, discovery date, and written-statement consent are customer facts, not proof of the required transaction/card/account checks.

## Helper script

`scripts/validate_dispute.py` is a deterministic preflight checker. It does not call banking tools or file a dispute. Supply retrieved records and normalized customer facts on stdin as one JSON object. It emits JSON with `ready`, `missing_or_invalid`, `tool_payload`, `provisional_credit`, and `post_filing_card_action`.

Required input keys are `now`, `identity_verified`, `authority_confirmed`, `user_id`, `account`, `card`, `transactions`, `open_disputes`, `account_tier`, `candidate`, and `statement_reported_within_60_days`. `candidate` carries the proposed filing fields plus `transaction_id`; for duplicate disputes it must also include `duplicate_transaction_ids_earliest_first`. Dates use `MM/DD/YYYY`. See the script docstring for the complete shape.

Example invocation by the executor after tool retrieval:

```json
{"now":"MM/DD/YYYY","identity_verified":true,"authority_confirmed":true,"user_id":"retrieved-user-id","account":{"account_id":"checking-id","account_type":"checking","status":"OPEN","has_holds_or_restrictions":false,"date_opened":"MM/DD/YYYY"},"card":{"card_id":"card-id","account_id":"checking-id","user_id":"retrieved-user-id"},"transactions":[{"transaction_id":"transaction-id","account_id":"checking-id","date":"MM/DD/YYYY","description":"merchant","amount":-10.0,"status":"posted"}],"open_disputes":[],"account_tier":"Entry","statement_reported_within_60_days":true,"candidate":{"transaction_id":"transaction-id","dispute_category":"duplicate_charge","discovery_date":"MM/DD/YYYY","transaction_type":"pin_purchase","card_in_possession":true,"pin_compromised":"no","contacted_merchant":true,"police_report_filed":false,"written_statement_provided":true,"duplicate_transaction_ids_earliest_first":["transaction-id"]}}
```

Review `missing_or_invalid` before any filing. A `ready: true` output means the supplied structured facts pass this policy checker, not that the bank action has been performed or that a transaction match was independently verified beyond the supplied records.
