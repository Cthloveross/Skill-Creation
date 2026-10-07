---
name: debit-card-dispute-intake-and-filing
description: Safely intake, validate, file, and follow up on debit-card transaction disputes, including Regulation E disclosures, provisional-credit analysis, ATM handling, and required card actions. Use when a verified customer reports unauthorized, duplicate, ATM, merchant, amount, recurring-charge, or debit-card transaction problems.
---

# Debit Card Dispute Intake and Filing

Use this workflow for debit-card disputes only. Do not file a dispute, freeze a card, close a card, order a replacement, or block recurring payments until the applicable prerequisites below are satisfied.

## 1. Verify the customer and locate records

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

1. Obtain an identifier (full name, email, or user ID), look up the user, and verify **two of four** identity fields: date of birth, email, phone number, and address.
2. Get the current timestamp and call `log_verification` only after two fields have been confirmed. Do not treat knowing a name alone as verification.
3. Unlock and use these internal tools as needed:
   - `get_all_user_accounts_by_user_id_3847` to find checking accounts, account class/tier, status, opening date, and restrictions/holds if returned.
   - `get_debit_cards_by_account_id_7823` for each relevant checking account to identify the card by last four digits and confirm its linked `account_id`, `user_id`, and status.
   - `get_bank_account_transactions_9173` to locate the exact transaction ID and transaction facts.
   - `get_debit_dispute_status_7483` to identify existing disputes and count unresolved/open disputes for each account.
4. Never infer a card ID, account ID, transaction ID, account tier, merchant contact, transaction channel, statement date, or customer consent from a card nickname or last four digits alone.

## 2. Gather a complete case record

For every proposed dispute, collect and confirm:

- linked checking account and debit card;
- exact transaction, transaction ID, date, amount, merchant/ATM, and transaction type;
- disputed amount (not necessarily the full transaction amount, such as an ATM partial-dispense shortage);
- date the customer first noticed the issue;
- whether fraud is suspected and, if so, whether the transaction was physically present or online/phone;
- whether the customer retains the physical card;
- PIN status: `yes_shared`, `yes_observed`, `no`, or `unknown`;
- for a non-fraud merchant dispute, whether they attempted merchant resolution;
- whether they agree to a written statement; the conversation may serve as that statement only when the customer expressly agrees;
- for fraud above $500, whether a police report was filed; if not, recommend filing one.

For multiple requested disputes, keep a separate record for every transaction. For duplicate transactions, identify and dispute the earliest/first duplicate transaction rather than a later duplicate.

Before proceeding with an unauthorized-activity report, explain the Regulation E exposure based on the date the customer noticed the unauthorized activity relative to the statement: within 2 business days, maximum $50; within 60 days, maximum $500; after 60 days, potentially unlimited liability and possible inability to recover funds. Obtain the relevant statement date or reporting interval rather than guessing it.

If any required fact is absent, ask focused follow-up questions and do not file a partial or speculative dispute.

## 3. Validate eligibility and choose values

For each dispute, verify all of the following:

1. The customer is verified and owns the card/account.
2. The debit card is linked to an **OPEN checking account**.
3. The transaction is at least $1.00.
4. The transaction is no more than 60 days old at filing.
5. The account has not reached its maximum number of open disputes: Entry 2, Mid 3, Premium 4, Elite 5. The limit is per account, not per customer.
6. The transaction in retrieved history matches the customer’s claimed date, amount, and card/account.

Use an exact category and transaction type:

| Circumstance | `dispute_category` | `transaction_type` |
|---|---|---|
| Unauthorized but fraud not suspected | `unauthorized_transaction` | applicable channel |
| Fraudulent physical/in-store card use | `card_present_fraud` | `pin_purchase` or `signature_purchase` |
| Fraudulent online/phone use | `card_not_present_fraud` | `online_purchase` |
| ATM dispensed no/wrong cash | `atm_cash_discrepancy` | `atm_withdrawal` |
| ATM deposit missing | `atm_deposit_not_credited` | `atm_deposit` |
| Same transaction charged more than once | `duplicate_charge` | applicable channel |
| Charged a wrong amount | `incorrect_amount` | applicable channel |
| Paid goods/services never arrived | `goods_services_not_received` | applicable channel |
| Charge continued after cancellation | `recurring_charge_after_cancellation` | `recurring_payment` |

The other valid transaction types are `person_to_person`, `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, and `recurring_payment`. Do not use `unauthorized_transaction` when fraud is suspected: choose `card_present_fraud` or `card_not_present_fraud` based on channel.

Use the category-specific `card_action` in each filing:

- `close_and_reissue`: `card_present_fraud`, `card_not_present_fraud`
- `freeze_pending_investigation`: `unauthorized_transaction`
- `keep_active`: all other permitted categories

## 4. Analyze provisional credit and special cases

Set `provisional_credit_eligible` true only when the requirements for required provisional credit are met: timely reporting within 60 days of the statement, an eligible category (`unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`), a written statement, and an OPEN unrestricted account. It is not required for goods/services-not-received, recurring-after-cancellation, ATM-deposit-not-credited, or incorrect-amount cases; when applicable it is also not required when merchant contact has not occurred for a non-fraud dispute, when the PIN was voluntarily shared, or for a card-not-present transaction on an account younger than 30 days.

Required provisional credit is for the full disputed amount, subject to any documented late-reporting liability offset. State the expected timing: 10 business days normally; 20 business days for new accounts. Investigation is generally up to 45 business days with provisional credit, or up to 90 days for international transactions, non-US merchant POS transactions, or new accounts.

For ATM disputes, ask whether the ATM was Rho-Bank owned or third party.

- For Rho-Bank cash discrepancies, review relevant transaction/journal information. A confirmed discrepancy receives immediate provisional credit; an unconfirmed claim may still be formally disputed.
- For Rho-Bank deposit issues, unlock `get_atm_deposit_images_8473` and compare available images to the claim.
- For third-party ATM cash discrepancies, explain the chargeback/network process and possible 90-day investigation. For an amount over $200, tell the customer an Electronic Fund Transfer Error Resolution Affidavit will be emailed, must be returned within 10 business days, and failure to return it can lead to denial.
- A retained Rho-Bank ATM card is not itself a transaction dispute; offer retrieval or replacement unless there are separate unauthorized transactions.

For a recurring charge after cancellation, filing addresses past charges only. If the customer also wants future recurring payments blocked, explain that the block applies to **all** recurring/subscription payments on the card, takes effect within 24 hours, does not cancel subscriptions, and then use `set_debit_card_recurring_block_7382` with explicit customer agreement.

## 5. File only validated cases

Unlock `file_debit_card_transaction_dispute_6281` and make one call per validated transaction with:

```text
transaction_id, account_id, card_id, user_id, dispute_category,
transaction_date (MM/DD/YYYY), discovery_date (MM/DD/YYYY), disputed_amount,
transaction_type, card_in_possession, pin_compromised, contacted_merchant,
police_report_filed, written_statement_provided,
provisional_credit_eligible, card_action
```

Do not submit cases that fail a filing prerequisite. Clearly explain the unmet requirement and any available next step. Record returned dispute IDs and communicate that an investigation will occur; do not promise an outcome.

## 6. Perform the post-filing card action once per card

After all filings for a given card are complete, choose the most severe actual action for that card: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`. Individual filing metadata must remain the category-mapped value, even if a different dispute on the same card drives the actual action.

- For `freeze_pending_investigation`, verify the card is ACTIVE and owned by the customer, explain that new and recurring transactions will decline while pending but already-authorized transactions can settle, then call `freeze_debit_card_3892` once.
- For `close_and_reissue`, comply with the close-card prerequisites: ownership, ACTIVE/PENDING card status, pending transaction/refund review, and minimum 14-day card age. Fraud-related closure bypasses the age requirement. Unlock `close_debit_card_4721`, close using the fraud-suspected reason, and explain the closure is permanent and recurring payment details must be updated.
- If replacement ordering is needed, use the account tier, replacement history, timing/waiting rules, selected shipping, and selected design to determine allowed options and exact fees. Inform the customer that all delivery, design, and applicable excess-replacement fees are automatically debited from the linked checking account, obtain needed selections/confirmation, then unlock and use `order_debit_card_5739` with exact `delivery_fee` and `design_fee`. Do not invent a shipping method, design, or fee.
- `keep_active` needs no card-state change.

## Helper script

`scripts/assess_dispute_cases.py` provides local, deterministic intake validation and a proposed category/card-action map. It does not access bank records, make banking actions, decide statement timeliness, or replace required tool lookups.

Input JSON:

```json
{
  "as_of": "MM/DD/YYYY",
  "cases": [
    {
      "transaction_date": "MM/DD/YYYY",
      "discovery_date": "MM/DD/YYYY",
      "disputed_amount": 1.0,
      "category": "duplicate_charge",
      "transaction_type": "signature_purchase",
      "fraud_suspected": false,
      "physical_present": false,
      "account_open": true,
      "open_disputes": 0,
      "tier": "Entry",
      "written_statement_provided": false,
      "merchant_contacted": true,
      "pin_compromised": "no",
      "account_age_days": 30
    }
  ]
}
```

It emits `results`, each containing `errors`, `warnings`, `suggested_category`, `card_action`, and `provisional_credit_required_if_timely_reported`. Review its output alongside live account, card, transaction, dispute-history, and customer-provided evidence.
