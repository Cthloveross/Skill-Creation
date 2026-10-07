---
name: debit-card-transaction-dispute
version: 1.1.0
description: Safely collect, validate, file, protect, or hand off debit-card transaction disputes. Use for unauthorized debit activity, ATM discrepancies, duplicate charges, incorrect amounts, missing goods or services, and recurring charges after cancellation.
---

# Debit Card Transaction Dispute

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Do not file a dispute, change card status, order a replacement, block recurring payments, or transfer account-specific work until identity and authority have been verified. In this runtime, confirm two of date of birth, email, phone number, and address against the retrieved user record, obtain the current timestamp, then call `log_verification` with the complete returned user record and timestamp.

## Discover and validate records

Retrieve, rather than infer, all identifiers and eligibility facts:

1. Retrieve the customer record and establish the verified `user_id`.
2. Use `get_all_user_accounts_by_user_id_3847` to retrieve accounts. Select the card-linked checking account and record `account_id`, `account_type`, `account_class`, `status`, balance, and `date_opened`.
3. Use `get_debit_cards_by_account_id_7823` for that account. Confirm that the selected `card_id` belongs to the verified customer, matches the customer’s card identification, and identify its status.
4. Use `get_bank_account_transactions_9173` for each relevant account. Match each claim to the returned `transaction_id`, date, description, amount, type, and status. A merchant name, card last four, or customer-provided amount is not a substitute for a returned ID.
5. Use `get_debit_dispute_status_7483(user_id)` and count only disputes whose `account_id` matches the selected account and whose status is exactly `OPEN`.

Unlock a discoverable agent tool before calling it. Relevant tools are:

- `get_all_user_accounts_by_user_id_3847`
- `get_debit_cards_by_account_id_7823`
- `get_bank_account_transactions_9173`
- `get_debit_dispute_status_7483`
- `file_debit_card_transaction_dispute_6281`
- `freeze_debit_card_3892`, when required
- `close_debit_card_4721`, when required
- `set_debit_card_recurring_block_7382`, only with separate consent to block every future recurring payment
- `get_atm_deposit_images_8473`, for a Rho-Bank ATM deposit-not-credited claim

Do not map informal account labels, marketing names, fee labels, or colors to Entry, Mid, Premium, or Elite tiers. Use only the returned account class or a documented supported tier lookup. If tier cannot be established, do not file under a guessed dispute limit; explain the limitation and offer or perform a human handoff.

## Intake and disclosures

Work one claim at a time if requested. Collect for each claim:

- merchant or ATM, transaction date, full transaction amount, amount actually disputed, and date first noticed;
- circumstances, expected resolution, and transaction channel;
- whether the physical card remains in the customer’s possession;
- PIN state: `yes_shared`, `yes_observed`, `no`, or `unknown`;
- merchant-contact result for every non-fraud claim;
- consent for this conversation to be a written statement;
- ATM ownership: Rho-Bank or third party; and
- for suspected fraud over $500, whether a police report was filed. Recommend one if it was not.

Before handling unauthorized activity, explain liability based on the time from the statement: within two business days has maximum $50 liability; within 60 days has maximum $500 liability; after 60 days may mean unlimited liability and non-recovery. Obtain a statement date before stating a specific applicable cap.

Use exact dispute categories:

- `card_present_fraud` for suspected physical/in-store card fraud;
- `card_not_present_fraud` for suspected online or phone fraud;
- `unauthorized_transaction` only when fraud is not suspected, including unauthorized family-member use;
- `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` only when facts support that category.

Use transaction types exactly: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`. For duplicates, identify and dispute the earliest matching transaction, not a later duplicate.

## Filing preflight

Before filing, establish all of the following:

- identity, authority, ownership, and card-to-account linkage;
- transaction amount of at least $1.00 and transaction age no more than 60 days;
- linked checking account is `OPEN`;
- returned transaction ID, card ID, account ID, and verified user ID;
- account-tier open-dispute capacity: Entry 2, Mid 3, Premium 4, Elite 5, counting only existing `OPEN` disputes on that account plus proposed filings.

Run `scripts/preflight.py` after gathering the facts. It is a local, deterministic check only: it does not verify identity, call banking services, infer account tier, determine statement timing, or perform banking actions. Do not file if its `errors` is nonempty. Resolve warnings necessary for the requested claim.

## Provisional credit

Set `provisional_credit_eligible` true only if all are established: timely reporting within 60 days of the relevant statement date, qualifying category (`unauthorized_transaction`, either fraud category, `atm_cash_discrepancy`, or `duplicate_charge`), written statement, and an OPEN unrestricted checking account.

It is not required for goods/services-not-received, recurring-cancellation, ATM-deposit, or incorrect-amount categories; where merchant contact was not completed for a non-fraud claim; where PIN was voluntarily shared; or for card-not-present fraud on an account opened less than 30 days ago. If statement timing, restrictions, or required account-age facts are unavailable, use unknown (`null`), not true.

When required, credit is for the full disputed amount subject to a late-report liability offset. The deadline is generally 10 business days, or 20 days for accounts opened less than 30 days ago. Investigation is generally 45 business days with provisional credit, or 90 days for international transactions, foreign merchant POS, or new accounts. Give three business days’ written notice before a reversal after an adverse result.

## ATM handling

For a Rho-Bank ATM cash discrepancy, review transaction and available journal information. If the record confirms the discrepancy, credit is immediate; if it indicates correct dispensing, explain that the claim cannot be validated from the journal but may still be formally disputed. For a Rho-Bank ATM deposit issue, retrieve deposit images; physical verification may take up to 45 days.

For a third-party ATM, follow the chargeback/dispute process to the ATM owner or network, advise that investigation can take up to 90 days, and apply qualifying provisional-credit timing. If an ATM cash-discrepancy **disputed amount** exceeds $200, state that an Electronic Fund Transfer Error Resolution Affidavit will be sent to the registered email, must be returned within 10 business days, failure to return it can lead to denial, and a false affidavit is a federal offense. Do not use the requested withdrawal amount instead of the actual disputed shortage when deciding the affidavit threshold.

## File and protect the card

Call `file_debit_card_transaction_dispute_6281` with all required fields: `transaction_id`, `account_id`, `card_id`, `user_id`, category, transaction and discovery dates in `MM/DD/YYYY`, positive float disputed amount, transaction type, card possession, PIN status, merchant-contact status, police-report status, written-statement status, provisional-credit result, and the mapped `card_action`.

Per-dispute actions are fixed:

| Category | card_action |
| --- | --- |
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| every other supported category | `keep_active` |

Record each claim’s own action. After all intended claims for a card are filed, perform only the most severe actual action: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`.

For a freeze, confirm ownership and `ACTIVE` status; disclose that new and recurring transactions decline, already-authorized pending items can post, and the card can later be unfrozen; then call `freeze_debit_card_3892` once. For closure, separately confirm ownership, `ACTIVE` or `PENDING` status, no pending transactions, no pending refunds unless written acknowledgement is obtained, and normally 14 active days. Fraud closures bypass only the card-age condition. Do not state that filing itself closed or replaced a card.

If the customer separately wants to stop future subscriptions, explain that the block affects all recurring payments, takes effect within 24 hours, does not cancel merchant subscriptions, and requires consent. File an applicable past-charge dispute first, then call `set_debit_card_recurring_block_7382`.

## Required human handoff

If a filing cannot safely proceed because a prerequisite is unavailable or unsupported, explain the blocker and offer a human agent. If the customer explicitly requests, accepts, or confirms that transfer, immediately call `transfer_to_human_agents`; do not merely say a transfer will occur or end the interaction.

Use `customer_requests_human_no_specific_reason` for a customer-accepted general handoff, or `specialized_department_required` when a specialized team is required by the established blocker. Supply a concise, factual `summary` with no guessed identifiers or eligibility conclusions. Include, when known:

- verification completion and verified user identity;
- each account and card identifier/last four, returned account status/class, and any unresolved tier limitation;
- each matched transaction’s ID, date, description, amount, account/card association, category, and disputed portion;
- written-statement consent and any ATM-affidavit consent/deadline;
- duplicate-charge earliest-transaction ordering status;
- merchant-contact status for every non-fraud claim;
- card possession, PIN, fraud, police-report, and proposed card-action facts;
- preflight blockers, provisional-credit facts, and all actions already taken.

For example, describe a partial dispute amount as the actual disputed portion of the matched transaction, rather than implying the full transaction is disputed. A transfer is an operational action, not a substitute for preserving this summary.

## Follow-up

Use `get_debit_dispute_status_7483` to monitor claims. Escalate if provisional credit is late (10 days, or 20 for a new account) or investigation exceeds 45 days, or 90 days for the applicable extended cases.

## Local helper interface

`scripts/preflight.py` reads one JSON object from stdin and writes one JSON object to stdout. Input contains `verified`, `account`, `card`, `transaction`, `existing_open_dispute_count`, `claims`, and optional `current_date` (`MM/DD/YYYY`). `account` includes returned account fields; `card` includes returned card fields; each claim contains dispute fields plus optional `fraud_suspected`, `statement_date`, `account_has_hold_or_restriction`, `atm_owner`, and `duplicate_candidates`.

Output is `{ok_to_file, errors, warnings, claims}`. Each normalized claim contains its mapped action, provisional-credit result (`true`, `false`, or `null`), reasons, and claim-specific errors. Example runnable invocation: `python3 scripts/preflight.py < case.json`.
