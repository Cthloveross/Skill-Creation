---
name: debit-card-transaction-dispute
version: 1.0.0
description: Safely gather, validate, file, and follow up on debit-card transaction disputes, including Regulation E timing, provisional-credit assessment, ATM-specific handling, account-tier dispute limits, and required card actions. Use for unauthorized debit activity, ATM errors, duplicate charges, incorrect amounts, missing goods or services, and recurring charges after cancellation.
---

# Debit Card Transaction Dispute

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Do not file a dispute, freeze a card, close a card, issue a replacement, or create a recurring-payment block until identity and authority have been verified. For this runtime, verify two of date of birth, email, phone number, and address against the retrieved user record, then call `log_verification` with all required record fields and the current timestamp.

## Required data and tool discovery

At runtime, retrieve rather than assume:

1. The customer record and verified `user_id`.
2. All accounts using `get_all_user_accounts_by_user_id_3847`; select the checking account linked to the card and confirm it is `OPEN`. Record its `account_id`, `account_class`/tier, and `date_opened`.
3. Cards for that account using `get_debit_cards_by_account_id_7823`; confirm the chosen `card_id` belongs to the verified user and matches the customer’s card identification.
4. Transactions for that account using `get_bank_account_transactions_9173`; match the customer’s date, description, and amount and use the returned `transaction_id`, exact date, and absolute debit amount. Transactions are reverse chronological, so explicitly identify the earliest transaction when duplicates are reported.
5. Prior disputes using `get_debit_dispute_status_7483(user_id)`; count only records with `account_id` matching the selected account and `status` equal to `OPEN` for the per-account open-dispute limit.

Unlock each specialized tool before calling it through the discoverable-agent-tool interface. The applicable tool names are:

- `get_all_user_accounts_by_user_id_3847`
- `get_debit_cards_by_account_id_7823`
- `get_bank_account_transactions_9173`
- `get_debit_dispute_status_7483`
- `file_debit_card_transaction_dispute_6281`
- `freeze_debit_card_3892` when required
- `close_debit_card_4721` when required
- `set_debit_card_recurring_block_7382` only when the customer separately asks to block all future recurring payments
- `get_atm_deposit_images_8473` for a Rho-Bank ATM deposit-not-credited claim

Never substitute a merchant name, last four digits, or customer-provided amount for a transaction ID or card ID returned by the relevant lookup.

## Intake and customer disclosures

Handle one claim at a time where the customer prefers. Before proceeding with unauthorized activity, explain liability based on when they noticed it relative to the statement: within 2 business days has maximum $50 liability; within 60 days has maximum $500 liability; after 60 days may mean unlimited liability and no recovery. Obtain the statement date when needed to determine the applicable interval. Do not claim a precise liability cap if the timing cannot be established.

For every claim, collect:

- merchant/ATM name or location, transaction date, transaction amount, disputed amount, and date first noticed (`discovery_date`)
- the circumstances and intended resolution
- transaction channel/type: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`
- whether the physical card remains in the customer’s possession
- PIN status: `yes_shared`, `yes_observed`, `no`, or `unknown`
- whether the merchant was contacted, for every non-fraud claim
- agreement for the conversation to serve as a written statement; set `written_statement_provided` true only upon agreement
- for suspected fraud exceeding $500, whether a police report was filed; recommend a police report if not filed
- for ATM claims, whether the ATM is Rho-Bank owned or third-party

Classify categories exactly as follows:

- Use `card_present_fraud` for suspected fraud involving a physical/in-store card transaction.
- Use `card_not_present_fraud` for suspected fraud involving online or phone activity.
- Use `unauthorized_transaction` only when fraud is not suspected, such as a family member’s unauthorized use.
- Use `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` only when their facts match.

For a duplicate, file the earliest matching transaction first; do not dispute later copies in place of the first transaction.

## Filing eligibility and preflight

A claim may be filed only after all of these are confirmed:

- customer identity, authority, and card/account ownership are verified
- selected transaction is at least $1.00 and is no more than 60 days old
- the linked checking account is `OPEN`
- the account’s existing `OPEN` dispute count plus disputes to be filed does not exceed its limit: Entry 2, Mid 3, Premium 4, Elite 5
- a returned transaction ID, linked checking account ID, returned card ID, and verified user ID are available

Use `scripts/preflight.py` to validate gathered data and calculate deterministic mappings before filing. It is a local validation aid only; it does not verify the customer, call banking tools, determine a statement date, or perform any banking action.

## Provisional-credit assessment

Set `provisional_credit_eligible` to true only when all required conditions are established:

1. the customer reported the unauthorized transaction within 60 days of the statement date showing it;
2. category is `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`;
3. a written statement was provided; and
4. the linked checking account is open with no hold or restriction.

Do not mark it required if the category is goods/services not received, recurring charge after cancellation, ATM deposit not credited, or incorrect amount; the merchant was not contacted for a non-fraud claim; the PIN was voluntarily shared; or the account is under 30 days old and the claim is card-not-present. If statement timing, account restrictions, or account age is unknown, eligibility is unknown rather than true.

When required, provisional credit is for the full disputed amount subject to any applicable late-reporting liability offset. Standard accounts must receive it within 10 business days; accounts opened less than 30 days have 20 business days. With provisional credit, investigation is generally 45 business days, extended to 90 days for international transactions, merchant POS transactions outside the US, or new accounts. If adverse findings reverse credit, written notice is required at least 3 business days before reversal.

## ATM handling

For Rho-Bank ATM cash discrepancies, review the linked account’s transactions and ATM journal information available through the transaction record. If the journal confirms the shortage, provisional credit is immediate. If it shows correct dispensing, explain that the claim cannot be validated through the journal but the customer may formally dispute it.

For Rho-Bank ATM deposits not credited, obtain deposit images with `get_atm_deposit_images_8473`; physical verification can take up to 45 days.

For a third-party ATM, submit the normal dispute/chargeback workflow to the ATM owner or network. Advise that investigation can take up to 90 days and qualifying provisional credit remains due within 10 business days. For an ATM cash discrepancy whose **disputed amount** exceeds $200, inform the customer that an Electronic Fund Transfer Error Resolution Affidavit will be emailed to their registered email address, must be signed and returned within 10 business days, may lead to denial if not returned, and that a false affidavit is a federal offense. Record documentation follow-up as appropriate; do not treat the requested withdrawal amount as the disputed amount.

A card retained by a Rho-Bank ATM is not itself a dispute. Offer retrieval within 3 business days or card closure/replacement, unless there are also unauthorized transactions.

## File each validated dispute

Call `file_debit_card_transaction_dispute_6281` with exactly these populated fields:

- `transaction_id`, `account_id`, `card_id`, `user_id`
- `dispute_category`, `transaction_date` (MM/DD/YYYY), `discovery_date` (MM/DD/YYYY)
- `disputed_amount` as a positive float
- `transaction_type`, `card_in_possession`, `pin_compromised`, `contacted_merchant`
- `police_report_filed`, `written_statement_provided`, `provisional_credit_eligible`, `card_action`

The per-dispute `card_action` mapping is fixed:

| Category | card_action |
| --- | --- |
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| all ATM, duplicate, incorrect-amount, goods/services, and recurring-cancellation categories | `keep_active` |

Record each dispute’s own mapped action even when several claims share a card. Preserve filing results, including dispute IDs and any documentation deadlines.

## Perform card protection after all filings for a card

After every intended claim for a particular card has been filed, select only the most severe recorded action: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`.

- For `keep_active`, do not alter the card.
- For `freeze_pending_investigation`, verify the card owner and that the card is `ACTIVE`; tell the customer new and recurring transactions will decline, authorized pending items may still post, and it can be unfrozen later. Then call `freeze_debit_card_3892` once.
- For `close_and_reissue`, separately satisfy closure prerequisites before calling `close_debit_card_4721`: ownership, `ACTIVE` or `PENDING` status, no pending transactions, no pending refunds (unless the required written acknowledgement is obtained), and normally 14 active days. A fraud-suspected closure bypasses only the minimum-age requirement. Use the appropriate fraud closure reason, explain permanent deactivation and recurring-payment impact, and follow the separate replacement-card workflow for any reissue. Do not claim that filing alone closed or replaced the card.

If the customer also wants future recurring payments stopped, first file the past-charge dispute, then explain that a recurring block affects **all** recurring payments on the card, takes effect within 24 hours, does not cancel subscriptions, and use `set_debit_card_recurring_block_7382` only with confirmed consent.

## Status follow-up

Use `get_debit_dispute_status_7483` for follow-up. Escalate to a supervisor if provisional credit appears late (10 days, or 20 for new accounts) or the investigation exceeds 45 days (90 days for international/POS/new-account cases).

## Local helper interface

`scripts/preflight.py` reads one JSON object from stdin and writes one JSON object to stdout. It accepts a structured case with `verified`, `account`, `card`, `transaction`, `existing_open_dispute_count`, `claims`, and optional `current_date`. Each claim contains the dispute tool fields plus optional `fraud_suspected`, `statement_date`, `account_has_hold_or_restriction`, `atm_owner`, and `duplicate_candidates`.

The output contains `errors` (filing blockers), `warnings` (missing or follow-up information), and a normalized result for each claim containing the required card action and provisional-credit result (`true`, `false`, or `null` when undetermined). Validate that `errors` is empty before filing; resolve warnings that are required for the customer’s requested handling. A runnable invocation sends the case JSON to standard input, for example: `python3 scripts/preflight.py < case.json`.
