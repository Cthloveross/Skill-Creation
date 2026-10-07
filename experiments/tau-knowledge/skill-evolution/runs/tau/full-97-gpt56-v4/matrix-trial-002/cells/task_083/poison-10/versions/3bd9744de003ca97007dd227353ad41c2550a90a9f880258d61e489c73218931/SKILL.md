---
name: debit-card-transaction-disputes
description: Safely file one or more eligible debit-card or ATM transaction disputes, including fraud classification, Regulation E provisional-credit assessment, duplicate selection, and the required per-card security action.
---

# Debit Card Transaction Disputes

Use for debit-card purchases and ATM errors: unauthorized/fraud activity, duplicate or incorrect charges, missing goods/services, cancellation charges, ATM cash discrepancies, and uncredited ATM deposits. Treat every filing and card action as a banking action.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Required sequence

1. **Identify and verify.** Locate the customer, confirm any two of date of birth, email, phone number, and address against the record, then call `log_verification` with the complete record and current timestamp. Verify the person owns each selected account/card.
2. **Collect claim facts.** For each charge obtain the card/account or last four, date, amount actually disputed, merchant/ATM, date first noticed, channel, card-possession answer, PIN value (`yes_shared`, `yes_observed`, `no`, `unknown`), merchant-contact answer, police-report answer, and agreement that the narrative is a written statement. Ask whether fraud is suspected. For fraud over $500, ask about a police report and recommend one if absent.
3. **Disclose liability before filing an unauthorized/fraud claim.** Reporting within 2 business days has maximum $50 liability; within 60 days has maximum $500; after 60 days can be unlimited/no recovery. Determine the applicable window from the report/statement facts. The filing tool requires `customer_max_liability_amount`: use the lesser of the disputed amount and $50/$500, or `-1` for unlimited; use `0` for non-unauthorized error categories.
4. **Perform current lookups.** Unlock/use `get_all_user_accounts_by_user_id_3847`, `get_debit_cards_by_account_id_7823`, and `get_bank_account_transactions_9173`. Select an OPEN checking account, an owned card linked to it, and the matching **posted** transaction. The transaction lookup supplies the ID, date, and actual debit amount—never invent an ID. Some account results label checking as `class` and product as `level`; do not mistake a product level for the required dispute tier.
5. **Check eligibility.** The transaction must be at least $1 and no more than 60 days old. Establish the account's tier and its current open-dispute count from a supported source; limits are Entry 2, Mid 3, Premium 4, Elite 5, per account. Confirm OPEN standing and no holds/restrictions. If a required limit or standing fact cannot be established through supported systems, do not invent it or claim it passed; use the supported escalation path.
6. **Classify and preflight.** Run `scripts/assess_disputes.py` with lookup-derived data and all facts. File only `ready: true` results. The script is a validation aid, not a substitute for verification, lookup, or a supported limit check.
7. **File and secure.** Unlock/use `file_debit_card_transaction_dispute_6281` with every required field in the payload below. After successful filings, take just one actual action for each card—the most severe mapped action. A filing's `card_action` is metadata and does not itself secure the card.

## Exact classification and card-action mapping

| Customer circumstance | `dispute_category` | `transaction_type` | filing `card_action` |
|---|---|---|---|
| Unauthorized, fraud not suspected (including family use beyond permission) | `unauthorized_transaction` | channel-specific | `freeze_pending_investigation` |
| Suspected physical-card fraud | `card_present_fraud` | `pin_purchase` or `signature_purchase` | `close_and_reissue` |
| Suspected online/phone fraud | `card_not_present_fraud` | `online_purchase` | `close_and_reissue` |
| ATM paid too little/no cash | `atm_cash_discrepancy` | `atm_withdrawal` | `keep_active` |
| ATM deposit missing | `atm_deposit_not_credited` | `atm_deposit` | `keep_active` |
| Same transaction posted more than once | `duplicate_charge` | channel-specific | `keep_active` |
| Paid a different amount | `incorrect_amount` | channel-specific | `keep_active` |
| Paid goods/services never received | `goods_services_not_received` | usually `online_purchase` | `keep_active` |
| Subscription charged after cancellation | `recurring_charge_after_cancellation` | `recurring_payment` | `keep_active` |

Allowed types are exactly `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, and `person_to_person`. Use a fraud category whenever fraud is suspected; only use `unauthorized_transaction` when it is not. For multiple identical duplicate postings, file the earliest transaction only, not the first record displayed by reverse-chronological history. If the exact ordering cannot be established for same-date records, resolve it before filing.

For one card, retain each claim's own mapped metadata but execute only the strongest actual action: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`. Before freezing, confirm verified ownership and ACTIVE status, explain that new and recurring transactions decline, pending authorizations can settle, and it can later be unfrozen; then unlock/use `freeze_debit_card_3892(card_id)`. Use only a supported closure/reissue procedure for a required close/reissue. Never repeat an action with an unknown result.

## Provisional credit

Set `provisional_credit_eligible` true only when all are established: timely report within 60 days of the statement, category is `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`, written statement provided, and OPEN checking account with no holds/restrictions.

Set it false for excluded categories (`goods_services_not_received`, `recurring_charge_after_cancellation`, `atm_deposit_not_credited`, `incorrect_amount`), for a non-fraud claim where the merchant was not contacted first, for voluntarily shared PIN (`yes_shared`), or for card-not-present activity on an account open under 30 days. Qualifying standard accounts receive the full qualifying amount within 10 business days (20 for a new account), subject to late-report liability. Do not promise approval; if provisional credit is later reversed, written advance notice is required.

## ATM-specific handling

Ask whether the ATM is Rho-Bank or third party. For a Rho-Bank cash discrepancy, compare the journal/transaction record to the claim; a confirmed discrepancy gets immediate provisional credit, though a formal dispute remains possible if the record appears correct. For Rho-Bank deposit errors, unlock/use `get_atm_deposit_images_8473`; physical verification may take up to 45 days. For third-party ATM claims, explain the chargeback to the operator/network, possible 90-day investigation, and qualifying credit within 10 business days. If a cash discrepancy's **disputed amount exceeds $200**, explain that an Electronic Fund Transfer Error Resolution Affidavit goes to the registered email, must be returned within 10 business days, and false signing is a federal offense.

## Filing payload and script interface

The filing tool requires this complete payload:

```text
transaction_id, account_id, card_id, user_id, dispute_category,
transaction_date, discovery_date, disputed_amount, transaction_type,
card_in_possession, pin_compromised, contacted_merchant, police_report_filed,
written_statement_provided, provisional_credit_eligible,
customer_max_liability_amount, card_action
```

`scripts/assess_disputes.py` reads one JSON object from stdin and writes one JSON object to stdout; its module docstring contains the full input schema. It verifies lookup links, dates, posted debit amount, allowed enums, duplicate selection, liability field, provisional-credit result, and both existing and batch-wide per-account dispute limits before calculating the strongest per-card action. Example:

```sh
python scripts/assess_disputes.py < dispute_input.json
```

Before filing, validate that each intended claim reports `ready: true`, the duplicate group has one selected earliest claim, the entire batch fits each account’s remaining dispute capacity, each payload retains the lookup IDs and exact enums, and `card_actions` has no more than one actual action per card. Finally tell the customer what was filed, the actual card action, applicable provisional-credit timing/status, and ATM-specific next steps.
