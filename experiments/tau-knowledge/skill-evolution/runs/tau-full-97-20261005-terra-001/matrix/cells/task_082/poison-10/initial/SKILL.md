---
name: debit-card-dispute-security-handoff
description: Handle or prepare a human handoff for debit-card disputes, lost or stolen debit cards, recurring-payment concerns, and debit-card security issues. Use when a customer reports unauthorized debit activity, ATM errors, duplicates, incorrect amounts, cancelled-subscription charges, a lost/stolen card, or asks for a human specialist for these matters.
---

# Debit Card Dispute, Security, and Human Handoff

Use this workflow to safely collect the facts required for debit-card dispute filing, secure a lost/stolen debit card, distinguish past-charge disputes from future recurring-payment blocks, and create an accurate human-agent escalation when the customer requests one or a security issue requires it.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For identity verification, obtain and verify at least two of the permitted identity fields (date of birth, email, phone number, address) against the customer record, then log the successful verification with the normal verification-record tool and current timestamp. A supplied name alone is not one of those two fields. Do not represent a customer as verified merely because they provided a name or one matching field.

## Triage and escalation

1. Identify all requests separately: each disputed transaction, any request to stop future recurring charges, and any card-loss/stolen-card report or replacement request.
2. If the customer explicitly wants a human to handle the matter, do not file disputes, close a card, order a replacement, or change a recurring-payment setting before the handoff unless the customer clearly changes that request. Gather only information needed for a safe, useful handoff.
3. Select the highest applicable transfer reason. Use `fraud_or_security_concern` for unauthorized activity, suspected fraud, lost/stolen-card security matters, a suspicious/inconsistent identity situation, a bank-initiated fraud alert, or other security concerns requiring specialist handling. This Tier 1 reason takes priority over a generic request for a human and over a billing-dispute reason.
4. Use the normal `transfer_to_human_agents` tool with that reason and a factual summary. The summary must state what is reported, what the customer requested, verification state, actions already completed, and material facts still needed. Never invent transaction identifiers, amounts, dates, card status, verification completion, or an investigation finding.
5. If the customer did not request handoff and the issue can be completed within scope, follow the dispute and card-security procedures below.

Use `scripts/build_handoff.py` to consistently choose an applicable reason and create a summary from runtime facts. Review the resulting summary for accuracy before sending it to the transfer tool.

## Lost or stolen debit cards

After identity verification and before a card action:

1. Retrieve the customer's accounts and identify the affected open checking account.
2. Retrieve all debit cards for that account. Confirm the card ID, cardholder user ID, linked account, status, and ownership. A debit-card closure normally requires an ACTIVE or PENDING card, no pending/processing transactions, and no pending refunds unless the customer provides written acknowledgement that refunds will credit the linked checking account. For a lost, stolen, or fraud-suspected card, the 14-day minimum card-age rule is bypassed; do not treat this as a bypass of the other prerequisites.
3. For a lost or stolen card, use the normal card-security/closure process with the applicable reason (`lost`, `stolen`, or `fraud_suspected`). Explain that the old card is permanently deactivated, recurring merchants need updated payment details, and refunds to a closed card credit the linked checking account.
4. If the customer wants a replacement, apply the debit-card-order eligibility checks to the applicable OPEN checking account before ordering: checking product, account age, balance/fees, age, US delivery address, no pending order, and no impermissible active-card condition. Confirm delivery and design choices and applicable fees.
5. For a lost/stolen report, retrieve the customer’s credit-card accounts. If any are active, ask whether that credit card was also in the missing wallet and offer a replacement with a new number. If none exist, record that the check found none. Do not claim that a credit card exists or was protected without the lookup result.
6. If a card was reported stolen but the customer says they did not report it, use enhanced verification and transfer to security. Do not reactivate a stolen card.

## Collecting and filing debit-card disputes

### Required facts and checks

For each transaction, retrieve transaction history from the relevant account and collect all information below before filing:

- customer, card, and checking-account IDs; account/card ownership and OPEN checking-account status;
- transaction ID, transaction date, amount (at least $1.00), description, and transaction type;
- discovery date and whether reporting was timely relative to the statement;
- dispute category and, for an unauthorized claim, whether fraud is suspected and whether the use was card-present or card-not-present;
- whether the customer still has the physical card and whether the PIN was shared, observed/skimmed, not compromised, or unknown;
- whether the customer contacted the merchant (required for non-fraud disputes);
- police-report status (ask for fraud disputes over $500 and recommend a report if none exists);
- whether the customer agrees to provide a written statement, including use of the conversation as that statement;
- ATM operator (Rho-Bank or third party) for ATM disputes; and
- the account’s current open-dispute count and tier limit.

Inform the customer about liability before proceeding: reported within 2 business days of the statement has maximum $50 liability; within 60 days has maximum $500 liability; after 60 days liability may be unlimited and recovery may not be possible.

Disputes must be within 60 days old, be at least $1.00, use a debit card linked to an OPEN checking account, and remain within the per-account open-dispute limit: Entry 2, Mid 3, Premium 4, Elite 5. For duplicates, dispute the earliest transaction in the duplicate set.

### Category and action mapping

Use exactly one category:

- `unauthorized_transaction`: unauthorized but fraud is not suspected;
- `card_present_fraud`: fraud suspected for an in-store/physical transaction;
- `card_not_present_fraud`: fraud suspected for online/phone use;
- `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` as applicable.

Map the dispute’s metadata card action exactly as follows:

- `card_present_fraud` or `card_not_present_fraud` → `close_and_reissue`
- `unauthorized_transaction` → `freeze_pending_investigation`
- all other supported categories → `keep_active`

For a card with multiple filings, retain the mapped action on every individual filing. After all filings, perform the actual card action once at the highest severity for that card: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`.

### Provisional credit

Set provisional-credit eligibility to true only when all of these are true: timely statement reporting; category is unauthorized transaction, card-present fraud, card-not-present fraud, ATM cash discrepancy, or duplicate charge; written statement is provided; and the checking account is OPEN with no holds/restrictions. It is not required for goods/services-not-received, recurring-after-cancellation, ATM-deposit-not-credited, or incorrect-amount categories; when the customer did not contact the merchant for a non-fraud dispute; when the PIN was voluntarily shared; or for a card-not-present transaction on an account less than 30 days old.

For qualifying cases, provisional credit is for the full disputed amount subject to applicable late-reporting liability offset. Standard accounts receive it within 10 business days; accounts opened less than 30 days receive it within 20 business days. Explain that a provisional credit can be reversed after an adverse investigation, with required advance written notice.

### Filing sequence

1. Unlock and use the normal account, debit-card, transaction-history, dispute-status, and debit-dispute-filing tools required by the runtime.
2. Validate all collected data using `scripts/dispute_plan.py`; do not file any item the script marks not ready. Resolve every reported missing or invalid field with the customer or required lookup.
3. File each ready dispute with the normal `file_debit_card_transaction_dispute_6281` tool using the returned `tool_args` exactly after confirming them against the live lookup results.
4. Apply the one, highest-severity actual card action per card using the normal card-action workflow. The `card_action` filing parameter alone does not perform the action.
5. If a charge already occurred after cancellation and the customer also wants future protection, file the past-charge dispute first, then explain that a recurring block affects every recurring/subscription charge on the card, takes effect within 24 hours, does not cancel subscriptions, and does not affect one-time purchases. Only then use the normal recurring-block action if the customer consents.

## Runtime helpers

Both helpers read one JSON object from stdin and emit one JSON object to stdout. They make no banking changes.

- `scripts/build_handoff.py`: Inputs are `issues` (boolean flags), `requested_actions` (array of strings), `verification_state` (string), optional `reported_disputes` (array of category/description strings), and optional `actions_completed` (array). It returns `{reason, summary, warnings}`. Send `reason` and reviewed `summary` to `transfer_to_human_agents`.
- `scripts/dispute_plan.py`: Inputs are `filing_date` (`MM/DD/YYYY`), `customer`, `accounts`, `cards`, `open_disputes_by_account`, and `disputes`. It returns item-level validation results, filing-ready `tool_args`, and the required aggregate actual action by card.

A runnable invocation uses runtime-supplied JSON, for example:

```sh
printf '%s' "$CASE_JSON" | python3 scripts/dispute_plan.py
```

Validation is meaningful only when `CASE_JSON` contains the complete schema described in the script’s module docstring and comes from the live customer interaction and authorized lookups. Inspect `ready`, `errors`, and `missing_fields`; only items with `ready: true` can be filed.
