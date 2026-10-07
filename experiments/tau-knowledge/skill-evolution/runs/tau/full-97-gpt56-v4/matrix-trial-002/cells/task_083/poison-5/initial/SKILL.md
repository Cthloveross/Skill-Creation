---
name: debit-card-dispute-and-replacement-workflow
description: Safely handles a verified customer's debit-card transaction disputes, including multi-card claims, ATM-specific processing, provisional-credit assessment, card security actions, and a requested replacement card. Use when a customer reports unauthorized, duplicate, ATM, merchant, amount, recurring-payment, or missing-goods debit-card transactions.
---

# Debit Card Dispute and Replacement Workflow

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety

Use this workflow only for debit-card transactions. Do not treat a customer name, a supplied account/card suffix, or a previous lookup as identity verification. Before a filing, freeze, close, or order action, verify the customer by confirming two of date of birth, email, phone number, and address, then log the successful verification with `log_verification` and the current timestamp.

Never file from a description alone. Retrieve and match the checking account, debit card, and posted transaction. Do not retry an action with an unknown outcome. If a tool reports an error, an ambiguous result, unavailable required record, or a contradiction, stop the affected action and explain or escalate as appropriate.

## Required discovery and prerequisite checks

1. Obtain the customer's identity and verify it as above. Retrieve the current time with `get_current_time` for the verification record and date-based checks.
2. Unlock and use `get_all_user_accounts_by_user_id_3847` for the verified user. Select only the relevant checking account(s), and confirm for each affected account:
   - `account_type` is `checking` and `status` is `OPEN`;
   - the customer owns the account/card being used;
   - account class/tier, opening date, balance, and any holds/restrictions needed for the intended action.
3. Unlock and use `get_debit_cards_by_account_id_7823` for every affected account. Match the customer-provided last four digits to one card owned by the verified user and record its `card_id`, status, issue date, and linked account. Do not guess when more than one card shares a suffix or the status is unsuitable.
4. Unlock and use `get_bank_account_transactions_9173` for every relevant checking account. Match transaction ID, date, description/merchant or ATM, absolute debit amount, and status. A dispute must be at least $1.00, must be no more than 60 days old under the filing rule, and must refer to an actual debit transaction. A partial dispute may not exceed the transaction's absolute debit amount.
5. Unlock and use `get_debit_dispute_status_7483` for the customer. Count only `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED` disputes on the particular checking account. Do not exceed the account-tier maximum: Entry 2, Mid 3, Premium 4, Elite 5. Limits are per account, not per customer.
6. If the customer reports duplicate transactions, identify all matching duplicates and file only the earliest transaction. Do not file a later duplicate instead.
7. Before filing, tell the customer the applicable Regulation E liability notice using the statement date that displayed the transaction and the reporting timing: within 2 business days, maximum $50; within 60 days, maximum $500; after 60 days, potentially unlimited and funds may not be recoverable. Obtain or verify the statement/reporting dates if this cannot be determined from the conversation and records.

## Collect a complete claim record

For each claim, collect and retain the following before filing:

- claimed transaction and linked `transaction_id`, `account_id`, `card_id`, and `user_id`;
- transaction date and date the customer first noticed the issue, both formatted `MM/DD/YYYY`;
- requested disputed amount, exact transaction circumstances, merchant/ATM information, and transaction type;
- whether the physical card remains in the customer's possession;
- PIN status: `yes_shared`, `yes_observed`, `no`, or `unknown`;
- whether the customer contacted the merchant (required for non-fraud claims) and their response;
- for fraud over $500, whether a police report was filed; if not, recommend one;
- whether the customer agrees to provide a written statement. The conversation may serve as the statement only with explicit agreement;
- for ATM matters, whether the ATM is Rho-Bank branded or third party.

Use these exact filing categories only:

- `unauthorized_transaction` only when the transaction was not authorized but fraud is not suspected, such as a family member using the card without permission;
- `card_present_fraud` for suspected fraud involving an in-person/physical-card transaction;
- `card_not_present_fraud` for suspected fraud involving online or phone/card-not-present use;
- `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` when those facts apply.

Use one exact transaction type: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.

For a non-fraud claim where the merchant has not been contacted, do not file it yet. Explain that the customer should first seek resolution from the merchant, obtain the response, and return with that information. This commonly blocks duplicate-charge, incorrect-amount, missing-goods, and recurring-cancellation filings.

## ATM processing

For a Rho-Bank ATM cash discrepancy, review the corresponding checking-account transaction/journal information. If the records confirm the shortfall, provisional credit is immediate. If records show the correct amount dispensed, explain that the claim could not be validated but the customer may still formally dispute it. For a Rho-Bank deposit-not-credited claim, unlock and use `get_atm_deposit_images_8473` and compare images with the expected deposit; physical verification can take up to 45 days.

For a third-party ATM, state that a chargeback request to the ATM owner/network is required, the investigation can take up to 90 days, and provisional credit is still due within 10 business days when required. For any ATM cash-discrepancy amount above $200, inform the customer that an Electronic Fund Transfer Error Resolution Affidavit will be emailed to their registered email address, must be signed and returned within 10 business days, may cause denial if not returned, and that a false affidavit is a federal offense. Do not claim an affidavit or chargeback was submitted unless the available banking workflow actually confirms it.

## Provisional-credit decision

Set `provisional_credit_eligible` to true only when provisional credit is required under the known facts:

1. timely report within 60 days of the statement date;
2. category is `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`;
3. a written statement has been provided; and
4. the checking account is OPEN without a hold or restriction.

Set it false when a required fact is absent or an exclusion applies. It is not required for `goods_services_not_received`, `recurring_charge_after_cancellation`, `atm_deposit_not_credited`, or `incorrect_amount`; it is also not required if a non-fraud customer has not contacted the merchant, if the PIN was voluntarily shared, or for a card-not-present dispute on an account under 30 days old. A discretionary credit must not be represented as required.

Required credit is the full disputed amount subject to applicable $50/$500 late-reporting liability offset. Required timing is within 10 business days, or 20 for an account opened fewer than 30 days ago. With credit, the investigation is normally 45 business days and may extend to 90 days for international, non-US merchant POS, or new-account matters. If a finding is against the customer, credit may be reversed only with written notice at least three business days beforehand and on request supporting documentation.

## File and apply card security action

For each eligible claim, unlock and call `file_debit_card_transaction_dispute_6281` with all of these arguments:

`transaction_id`, `account_id`, `card_id`, `user_id`, `dispute_category`, `transaction_date`, `discovery_date`, `disputed_amount`, `transaction_type`, `card_in_possession`, `pin_compromised`, `contacted_merchant`, `police_report_filed`, `written_statement_provided`, `provisional_credit_eligible`, and `card_action`.

The per-filing `card_action` must exactly follow this mapping:

| Category | Filing card action |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| all ATM, duplicate, incorrect amount, missing-goods, and recurring-cancellation categories | `keep_active` |

This parameter is metadata; perform the corresponding card action separately only after all eligible filings for a card have completed. For multiple filings on one card, preserve each filing's own mapped value, then perform one actual action at the highest severity: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`.

To freeze, first reconfirm customer ownership and an `ACTIVE` card, explain that new and recurring transactions will be declined while pending authorized transactions can still settle, then unlock and call `freeze_debit_card_3892(card_id)`. A frozen card can later be unfrozen only after confirming ownership, `FROZEN` status, and an OPEN linked checking account.

For `close_and_reissue`, or a separately requested new card number, do not assume closing is automatically permissible. Confirm the customer's closure reason and replacement request. For closure, check ownership, ACTIVE/PENDING status, pending transactions, pending refunds, and the 14-day age rule. Lost, stolen, and fraud-suspected closures bypass only the age rule; pending transactions/refunds must still be addressed according to the closure procedure. Unlock and call `close_debit_card_4721(card_id, reason)` only after checks. State that closure is permanent, recurring payments need updating, and refunds to the closed card credit the checking account.

## Replacement after confirmed closure

A replacement is a separate order. Reconfirm the linked OPEN checking account, customer ownership, age (at least 18), domestic mailing address, sufficient balance for all fees, no existing active/pending-card conflict as applicable, and replacement history. Count only cards with issue reasons `lost`, `stolen`, `fraud`, or `damaged` issued within the preceding 12 months.

Apply tier rules and disclose that all fees are automatically deducted before ordering:

- Entry: maximum 2 replacements, 48-hour post-closure wait, standard only ($0); after the limit, wait or pay $25 excess fee. Design: Classic $0, Premium $10, Custom $25.
- Mid: maximum 3, no wait; Standard $0 or Expedited $15; after limit, wait or pay $15 excess fee. Design: Classic $0, Premium $10, Custom $25.
- Premium: maximum 5, no wait; Standard/Expedited $0, Rush $35; after limit must wait. Design: Classic/Premium $0, Custom $15.
- Elite: unlimited, no wait; Standard/Expedited/Rush $0. Design: all $0. Before 2pm EST, eligible replacements receive same-business-day priority processing.

Confirm the selected permitted delivery option, design, exact delivery and design fee, address, and any excess replacement fee before ordering. Unlock and call `order_debit_card_5739` only with the tool's documented required order fields and exact computed delivery/design fees. Confirm expected delivery and fees after a successful order. Do not invent unsupported tool arguments.

## Deterministic planning helper

`scripts/dispute_plan.py` performs local, non-banking validation and creates a filing-readiness plan. It never calls bank tools or performs an action. Supply JSON on stdin with this shape:

```json
{
  "as_of": "YYYY-MM-DD",
  "account": {"account_type":"checking", "status":"OPEN", "tier":"ENTRY|MID|PREMIUM|ELITE", "opened":"YYYY-MM-DD", "has_hold_or_restriction":false, "open_dispute_count":0},
  "claims": [{"transaction_id":"retrieved ID", "transaction_date":"MM/DD/YYYY", "statement_date":"MM/DD/YYYY", "discovery_date":"MM/DD/YYYY", "reported_date":"MM/DD/YYYY", "transaction_amount":0.0, "disputed_amount":0.0, "category":"allowed category", "transaction_type":"allowed type", "card_in_possession":true, "pin_compromised":"allowed PIN value", "contacted_merchant":true, "written_statement_provided":true, "duplicate_group":"optional matching group", "police_report_filed":false}]
}
```

Run it as `python3 scripts/dispute_plan.py < input.json`. It emits JSON with per-claim errors, whether filing is ready, the mapped card action, provisional-credit requirement, liability band, and only the earliest candidate in a duplicate group. Treat missing statement/report date, unknown account restrictions, unavailable transaction matching, or missing open-dispute count as a blocker to a final banking action even if local syntax validation passes.
