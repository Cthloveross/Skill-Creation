---
name: debit-card-dispute-filing
description: Safely prepare and file one or more debit-card transaction disputes after gathering customer facts, verifying eligibility, determining Regulation E provisional-credit treatment, and applying the correct per-card security action. Use for unauthorized, fraud, ATM, duplicate, incorrect-amount, merchant, recurring-payment, and non-receipt debit-card claims.
---

# Debit Card Dispute Filing

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety boundary

Use this workflow only for debit-card transactions linked to a checking account. Do not file a dispute, freeze a card, or close a card until the applicable prerequisites below are satisfied. A plan from the included script is advisory; the execution agent must obtain live tool results and must not treat a plan as an executed bank action.

## Required runtime data and lookup sequence

1. Identify the customer and verify identity by matching at least two identity fields. Log successful verification with `log_verification` using the current time.
2. Retrieve accounts using `get_all_user_accounts_by_user_id_3847(user_id)`. Identify the checking account for each card, its status, tier/class, opening date, and any holds or restrictions.
3. For every involved account, retrieve cards using `get_debit_cards_by_account_id_7823(account_id)` and match the card's last four digits, `card_id`, and `user_id`.
4. Retrieve transactions for every involved account with `get_bank_account_transactions_9173(account_id)`. Match transaction date, description, amount, type, and status to each claim. Do not guess a transaction ID.
5. Retrieve history using `get_debit_dispute_status_7483(user_id)`. Count only unresolved disputes for the relevant account and reject a claim already filed for the same transaction.
6. Gather any facts still missing before filing: transaction/discovery/statement dates, exact amount disputed, category facts, transaction type, card possession, PIN-compromise choice, merchant-contact result for a non-fraud claim, written-statement consent, and fraud police-report answer for fraud above $500.
7. Run `scripts/plan_debit_disputes.py` on normalized live data. Resolve every `blocking_reasons` and `needs_information` item before filing.

The script input and output are specified below. It is intentionally strict when a required fact cannot be proven from the supplied data.

## Pre-filing eligibility

For each claim, confirm all of the following:

- Customer identity is verified; the card belongs to the customer and is linked to the stated account.
- The account is a checking account, is `OPEN`, and has no hold or restriction for provisional-credit eligibility.
- The disputed amount is at least $1.00 and does not exceed the transaction amount.
- The transaction is no more than 60 calendar days old on the filing date.
- The account has not reached its unresolved-dispute limit: Entry 2, Mid 3, Premium 4, Elite 5. Limits are per account, not per customer.
- There is no existing unresolved or resolved dispute for the same `transaction_id`.
- For a non-fraud category, the customer has attempted to resolve the issue with the merchant. Do not substitute a contact attempt for a customer answer.
- For an ATM claim, establish whether the ATM is Rho-Bank owned or third party.

When duplicate transactions exist, select and dispute the earliest matching transaction first. Do not file the same duplicate claim twice merely because two duplicate postings exist.

## Category and field mapping

Choose exactly one category:

- `unauthorized_transaction`: no fraud suspected, such as unpermitted family use.
- `card_present_fraud`: fraud suspected and the card was used physically.
- `card_not_present_fraud`: fraud suspected and the transaction was online or by phone.
- `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` according to the reported error.

Choose exactly one transaction type: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.

Use the customer’s actual disputed loss, not necessarily the full posted transaction amount. For example, an ATM withdrawal for $200 that dispensed $80 has an $120 cash-discrepancy claim. Preserve the posted transaction amount in the case narrative.

Required filing fields are: `transaction_id`, `account_id`, `card_id`, `user_id`, `dispute_category`, transaction and discovery dates in `MM/DD/YYYY`, `disputed_amount`, `transaction_type`, `card_in_possession`, `pin_compromised` (`yes_shared`, `yes_observed`, `no`, or `unknown`), `contacted_merchant`, `police_report_filed`, `written_statement_provided`, `provisional_credit_eligible`, and `card_action`.

For fraud over $500, ask about a police report and recommend one if none was filed. Record the actual Boolean answer; absence of a report alone is not listed as a filing prohibition.

## Regulation E disclosures and provisional credit

Before filing an unauthorized-activity claim, explain the liability exposure based on reporting timing: within 2 business days, maximum $50; within 60 days of the statement, maximum $500; after 60 days, potentially unlimited liability and unrecoverable funds. Obtain the statement date (or an authoritative timing determination) rather than inventing it.

Provisional credit is required only when all of these are true:

1. Reporting was timely, within 60 days of the statement date.
2. The category is `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`.
3. The customer provided a written statement.
4. The checking account is open with no holds or restrictions.
5. The claim is not excluded because the PIN was voluntarily shared, or because it is a card-not-present claim on an account open less than 30 days.

Merchant non-contact also prevents required provisional credit for a non-fraud claim. Ineligible categories (`goods_services_not_received`, `recurring_charge_after_cancellation`, `atm_deposit_not_credited`, and `incorrect_amount`) may be offered credit only at discretion; do not mark them required.

For required credit, calculate the full disputed amount subject to any applicable $50/$500 liability offset; never exceed the disputed amount. Standard accounts require credit within 10 business days; accounts open fewer than 30 days require it within 20 business days. Explain that a provisional-credit investigation is normally 45 business days and can extend to 90 days for international, non-US merchant POS, or new-account transactions. A later adverse finding can reverse provisional credit with written notice at least three business days before reversal.

## ATM procedures

For a Rho-Bank ATM cash discrepancy, review relevant account transactions and ATM journal information. If confirmed, issue provisional credit immediately; if the journal says the requested amount was dispensed, explain that the claim cannot be validated but the customer may still formally dispute it. For a Rho-Bank ATM deposit claim, retrieve deposit images with `get_atm_deposit_images_8473` and compare them with the claim.

For a third-party ATM, submit the chargeback request to the ATM owner/network and advise that investigation can take 90 days. A third-party ATM cash-discrepancy claim over $200 requires an Electronic Fund Transfer Error Resolution Affidavit: tell the customer it will be emailed to their registered address, is due within 10 business days, may cause denial if not returned, and false signing is a federal offense. This documentation requirement is not an excuse to skip timely filing.

## Filing and card security actions

After all individual claims are eligible, unlock and call `file_debit_card_transaction_dispute_6281` once per eligible claim using the exact planned fields. Record the result for each transaction.

Set each filing's `card_action` without changing it for other claims:

| Category | Filing card action |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| All ATM, duplicate, incorrect-amount, non-receipt, and recurring categories | `keep_active` |

After all claims on the same card have been filed, perform only the highest-severity action for that card: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`. Do not perform a card action when no filing succeeded.

Before `freeze_debit_card_3892`, verify the customer owns the card and it is `ACTIVE`; explain that new and recurring transactions decline, authorized pending transactions may still post, and the card can later be unfrozen. Before `close_debit_card_4721`, satisfy the card-closing procedure, including ownership, card status, pending transaction/refund checks, and minimum-age rule. Fraud-suspected closure bypasses only the minimum card-age requirement. Use reason `fraud_suspected` for fraud-category closure. A close action permanently deactivates the card; handle replacement ordering under the separate replacement-card workflow rather than assuming a reissue was ordered.

## Script interface

Run:

```text
python3 scripts/plan_debit_disputes.py < normalized_input.json
```

The script reads one JSON object from stdin and emits one JSON object to stdout. Required top-level fields are `as_of` (`YYYY-MM-DD`), `identity_verified`, `user_id`, `accounts`, `cards`, `transactions`, `existing_disputes`, and `claims`. Dates in input accept `YYYY-MM-DD` or `MM/DD/YYYY`. Accounts require `account_id`, `account_type`, `account_class`, `status`, and preferably `date_opened`, `has_holds`, and `has_restrictions`. Cards require `card_id`, `account_id`, `user_id`, `card_number_last_4`, and `status`. Transactions require `transaction_id`, `account_id`, `date`, `description`, `amount`, and `status`.

Each claim requires `account_id`, `card_last4` or `card_id`, `transaction_id` (or `duplicate_transaction_ids` for a duplicate), `category`, `transaction_type`, `discovery_date`, `disputed_amount`, `card_in_possession`, `pin_compromised`, `contacted_merchant`, `written_statement_provided`, and `atm_owner` for ATM claims. Supply `statement_date` or `reporting_timing` (`within_2_business_days`, `within_60_days`, `after_60_days`) for liability/provisional analysis. Supply `fraud_suspected`, `police_report_filed`, and `international_or_non_us_pos` when applicable.

Validate the output by ensuring every item to file has an empty `blocking_reasons` list, a complete `filing_arguments` object, and the correct card-specific action. Treat all output `needs_information`, `notices`, and `post_filing` items as mandatory work instructions. The executor must still compare every planned ID and amount to live tool results immediately before each bank action.
