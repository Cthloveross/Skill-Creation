---
name: debit-card-transaction-dispute
version: 1.1.0
description: Verify, review, and file eligible debit-card transaction disputes through the banking runtime, including ATM cash discrepancies, account-level dispute limits, journal review, provisional-credit handling, and card-action follow-up.
---

# Debit Card Transaction Dispute

Use this skill when a customer wants to dispute a debit-card transaction, including an ATM error, unauthorized use, fraud, duplicate transaction, incorrect amount, recurring charge, merchant issue, or missing goods/services. Handle one transaction at a time unless complete information is available for several transactions.

## Non-negotiable execution rule

A verified customer who has supplied the material claim facts is requesting a banking action, not merely information. Do **not** say that account, card, transaction, dispute, or filing access is unavailable before using the documented banking tools. Do not stop after gathering the statement. Complete the required lookup and filing sequence in the same workflow unless a lookup establishes a real eligibility blocker or required facts are genuinely missing.

After verification, use the runtime's normal banking tools. Tools documented below as discoverable must first be unlocked with `unlock_discoverable_agent_tool`, then invoked with `call_discoverable_agent_tool`. Use the exact documented tool name and JSON arguments. Never invent account, card, transaction, or dispute identifiers.

## Identity, authority, and customer statement

Before any banking action, verify identity, authority, account ownership, product eligibility, account/card/transaction details, applicable limits, and required confirmations. Confirm at least two profile fields against the customer and, when available, record the successful verification with `log_verification` using the current time.

Gather or retain these facts for each claim:

- transaction date, merchant/ATM, original transaction amount, and disputed amount;
- date the customer discovered the issue;
- whether the physical card remains in the customer's possession;
- PIN-compromise response: `yes_shared`, `yes_observed`, `no`, or `unknown`;
- whether the customer contacted the merchant or ATM operator;
- written-statement consent. When the customer agrees that the conversation is their written statement, set `written_statement_provided` to `true`;
- police-report status only for suspected fraud over $500. For a non-fraud claim, record `police_report_filed` as `false` because it is not applicable.

For an unauthorized or fraud report, give the Regulation E notice before proceeding: reporting within two business days of the statement limits liability to $50; within 60 days limits it to $500; after 60 days liability may be unlimited and recovery may not be available.

## Required lookup-and-filing sequence

Perform these calls in order **after identity verification and before filing**. This sequence is required even if the customer has named an account or card.

1. Unlock and call `get_all_user_accounts_by_user_id_3847` with `{"user_id": "<verified user id>"}`.
   - Select a customer-owned account that is `OPEN`, has `account_type` checking, and corresponds to the account the customer identified.
   - Retain its `account_id`, `account_class`, `status`, balance, opening date, and any holds/restrictions. Do not select a savings account.
2. Unlock and call `get_debit_cards_by_account_id_7823` with `{"account_id": "<selected checking account id>"}`.
   - Select the card that belongs to the verified user, is linked to the selected account, and is active when a currently usable card is required. Match any customer-supplied card label or last four digits only when runtime records support the match.
3. Unlock and call `get_bank_account_transactions_9173` with `{"account_id": "<selected checking account id>"}`.
   - Locate the posted transaction matching the customer's date, amount, description, and type. Use the actual transaction's `transaction_id`, date, and full transaction amount; the disputed amount may be only part of that amount.
   - For an ATM claim, inspect the returned matching transaction and any journal fields/evidence included in the account-history response. This is the required Rho-Bank ATM journal review.
4. Unlock and call `get_debit_dispute_status_7483` with `{"user_id": "<verified user id>"}`.
   - Count only disputes for the selected `account_id` whose status is `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, or `PROVISIONAL_CREDIT_ISSUED`.
   - Do not file if that account has reached its tier limit: Entry 2, Mid 3, Premium 4, Elite 5.
5. Unlock `file_debit_card_transaction_dispute_6281` and call it only after steps 1–4 establish eligibility. Supply all required arguments from the selected runtime records and customer statement.

If a lookup returns no matching account, card, or transaction, explain the specific result and ask only the minimum question needed to resolve it. If a matching transaction is found but is ineligible, explain the relevant blocker. Do not replace lookup results with guessed IDs or decline merely because a tool is discoverable.

## Transaction eligibility and classification

The selected transaction must be at least $1.00 and within 60 days. For duplicates, identify and file the earliest matching duplicate first.

Use exactly one of these dispute categories:

- `unauthorized_transaction`: unauthorized, but fraud is not suspected;
- `card_present_fraud`: suspected fraud involving a physical/card-present transaction;
- `card_not_present_fraud`: suspected online, phone, or other card-not-present fraud;
- `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation`: when their ordinary descriptions apply.

Use exactly one transaction type: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.

For an ATM that dispensed less cash than requested, classify it as `atm_cash_discrepancy` with `transaction_type: "atm_withdrawal"`. File against the full posted ATM withdrawal, while setting `disputed_amount` to the documented cash shortfall.

## ATM handling

Determine whether the ATM is Rho-Bank owned or third party.

- **Rho-Bank cash discrepancy:** review the matching account transaction/journal evidence before filing. If the journal confirms the shortage, treat the discrepancy as confirmed and provide immediate provisional-credit handling. If it records the requested amount as dispensed, tell the customer the claim is not journal-validated, but they may still file a formal dispute.
- **Rho-Bank deposit not credited:** retrieve `get_atm_deposit_images_8473` when it is made available, compare the images to the claimed deposit, and explain physical verification may take up to 45 days.
- **Retained card:** card retention alone is not a transaction dispute. At a Rho-Bank ATM, offer branch retrieval within three business days or card replacement. File only when there is also an unauthorized transaction or another disputeable transaction error.
- **Third-party ATM:** submit through the ordinary dispute flow/chargeback process and explain that investigation may take up to 90 days. Provisional credit remains subject to the applicable requirements.
- **ATM cash discrepancy over $200:** tell the customer an Electronic Fund Transfer Error Resolution Affidavit will be emailed to the registered email address. It must be signed and returned within 10 business days; failure to return it may cause denial; a false affidavit is a federal offense.

## Provisional credit

Set `provisional_credit_eligible` to a boolean based on runtime findings. Required eligibility requires: timely reporting within 60 days of the relevant statement, a qualifying category (`unauthorized_transaction`, either fraud category, `atm_cash_discrepancy`, or `duplicate_charge`), a written statement, and an OPEN unrestricted checking account.

It is not required for `goods_services_not_received`, `recurring_charge_after_cancellation`, `atm_deposit_not_credited`, or `incorrect_amount`. It is also not required where a conventional non-fraud merchant dispute was not first raised with the merchant, where the customer voluntarily shared the PIN, or for card-not-present fraud on an account open less than 30 days. A customer's lack of prior contact with an ATM operator does not by itself reclassify an ATM cash discrepancy or eliminate the Rho-Bank confirmed-discrepancy procedure.

An eligible credit is the full disputed amount, subject to an applicable late-reporting liability offset. Standard timing is within 10 business days, or 20 business days for an account open less than 30 days. A confirmed Rho-Bank ATM cash discrepancy is handled immediately. Explain that provisional credit is temporary: an adverse investigation outcome may reverse it with written notice at least three business days beforehand, and the customer may request supporting documents.

## Filing payload and post-filing action

Call `file_debit_card_transaction_dispute_6281` with this complete schema:

```json
{
  "transaction_id": "runtime transaction id",
  "account_id": "runtime checking account id",
  "card_id": "runtime debit card id",
  "user_id": "verified user id",
  "dispute_category": "one permitted category",
  "transaction_date": "MM/DD/YYYY",
  "discovery_date": "MM/DD/YYYY",
  "disputed_amount": 0.0,
  "transaction_type": "one permitted type",
  "card_in_possession": true,
  "pin_compromised": "no",
  "contacted_merchant": false,
  "police_report_filed": false,
  "written_statement_provided": true,
  "provisional_credit_eligible": true,
  "card_action": "keep_active"
}
```

Use the mapped `card_action` for each filing:

- `card_present_fraud` or `card_not_present_fraud` → `close_and_reissue`
- `unauthorized_transaction` → `freeze_pending_investigation`
- every other supported category → `keep_active`

After a successful filing, separately perform the mapped card action if the corresponding normal banking card-action tool is available. With multiple disputes on one card, retain each filing's individual action, then perform only the single most severe actual action: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`. Recommend a police report for suspected fraud exceeding $500 when none was filed.

## Transfer requests

If the customer asks to speak with a person instead of continuing the workflow, call `transfer_to_human_agents` immediately with the applicable reason (normally `customer_requests_human_no_specific_reason`) and a concise summary of the verified identity, completed lookups, gathered facts, and any filing status. Do not merely ask whether they want a transfer.

## Optional payload validator

`scripts/validate_debit_dispute.py` performs deterministic validation after runtime lookups. It does not call banking tools, file disputes, grant credit, send emails, or alter cards.

It reads one JSON object from stdin and writes one JSON object to stdout. Input fields are:

- `verified`, `authority_verified`, and `user_id`;
- `account`: selected runtime account record (`account_id`, `account_type`, `account_class`, `status`, optional `has_holds`, `has_restrictions`);
- `card`: selected runtime card record (`card_id`, `account_id`, `user_id`, optional `status`);
- `transaction`: selected runtime transaction record (`transaction_id`, `account_id`, `date`, `amount`, `type`, optional `status`);
- `existing_disputes`: list returned by the dispute-status lookup;
- `case`: customer facts and determinations: `dispute_category`, `transaction_type`, `discovery_date`, `disputed_amount`, `card_in_possession`, `pin_compromised`, `contacted_merchant`, `police_report_filed`, `written_statement_provided`, `timely_reported_on_statement`, plus `atm_owner` and `journal_review` for ATM cash discrepancies.

Example invocation after collecting runtime data:

```sh
python3 scripts/validate_debit_dispute.py < gathered_case.json
```

Use `filing_arguments` only when `ok_to_file` is true. Resolve every returned blocker before filing. The executor, not the validator, must determine statement timing and interpret journal evidence from the actual tool results.
