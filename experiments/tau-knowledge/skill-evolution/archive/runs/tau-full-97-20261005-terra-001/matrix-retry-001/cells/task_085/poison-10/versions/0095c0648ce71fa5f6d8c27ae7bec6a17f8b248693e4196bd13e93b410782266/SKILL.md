---
name: debit-card-transaction-dispute
version: 1.0.0
description: Safely prepares and files eligible debit-card transaction disputes, including Regulation E notices, ATM-specific handling, provisional-credit decisions, dispute-limit checks, and required card-action follow-up.
---

# Debit Card Transaction Dispute

Use this skill when a verified customer asks to dispute a debit-card transaction, including unauthorized activity, fraud, ATM cash/deposit errors, duplicate charges, merchant issues, incorrect amounts, cancelled recurring payments, or missing goods/services. Process one issue at a time unless the customer has supplied complete details for several transactions.

## Required checks before filing

Before any banking action, verify customer identity, authority to act, account ownership, product eligibility, account/card/transaction details, applicable limits, and required confirmations. Log identity verification using the runtime's verification-record mechanism when it is available. Do not file until all filing fields and the checks below are supported by current runtime data.

1. Tell the customer the Regulation E liability notice before proceeding with an unauthorized/fraud concern:
   - reported within 2 business days of the statement: maximum liability $50;
   - reported within 60 days of the statement: maximum liability $500;
   - after 60 days: potentially unlimited liability and funds may not be recoverable.
2. Obtain and verify the customer user record, then retrieve all accounts. Select the customer-owned **OPEN checking** account associated with the requested card. Verify there are no holds or restrictions when deciding provisional-credit eligibility.
3. Retrieve debit cards for that account. Verify the chosen card is linked to the account and belongs to the verified user. Do not assume a card label identifies a particular card.
4. Retrieve the account transaction history and match the customer's merchant/ATM, date, and amount to one transaction. Transactions are reverse chronological. Use its `transaction_id`, actual date, and debit amount. The transaction must be at least $1.00 and no more than 60 days old.
5. Retrieve dispute history and count only active/open disputes for the selected **account** (not all of the user's accounts). Active statuses are `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED`. Account-tier limits are Entry 2, Mid 3, Premium 4, and Elite 5.
6. When duplicates are reported, identify and dispute the earliest matching duplicate transaction first.
7. Gather: discovery date, transaction circumstances/type, physical-card possession, PIN-compromise answer, merchant-contact answer, written-statement consent, and (for fraud over $500) police-report status. If the customer agrees that the conversation is their written statement, record `written_statement_provided: true`.

Do not manufacture transaction identifiers, account/card identifiers, dates, merchant contact, or verification outcomes. Ask for missing customer facts and use lookup tools for bank facts.

## Classify the dispute

Use exactly one filing category:

- `unauthorized_transaction` only when the transaction was not authorized but fraud is **not** suspected (for example, an unpermitted family use).
- `card_present_fraud` when fraud is suspected and the physical card was used.
- `card_not_present_fraud` when fraud is suspected for an online or phone/card-not-present transaction.
- `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` when those descriptions apply.

Use one of these transaction types exactly: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.

## ATM procedure

Determine whether the ATM is Rho-Bank owned or third party.

- For a Rho-Bank ATM cash discrepancy, review the matching account transaction/journal information and compare it to the claim. A confirmed discrepancy receives immediate provisional credit. If the journal indicates the amount was correctly dispensed, explain that the claim cannot be validated through the journal but the customer may still formally dispute it.
- For a Rho-Bank ATM deposit-not-credited issue, retrieve deposit images using `get_atm_deposit_images_8473` when that tool is available; physical verification may take up to 45 days.
- If an ATM retained a card, do not file a dispute solely for retention. At a Rho-Bank ATM, offer branch retrieval within 3 business days or replacement. File only if there are also unauthorized transactions.
- For a third-party ATM issue, submit the dispute/chargeback through the normal filing flow and explain that investigation can take up to 90 days. Provisional credit is generally due within the applicable regulatory time frame.
- For an ATM cash discrepancy above $200, tell the customer an Electronic Fund Transfer Error Resolution Affidavit will be emailed to their registered email address, must be signed and returned within 10 business days, may lead to denial if not returned, and that a false affidavit is a federal offense. Record and monitor the documentation requirement.

## Provisional credit

Set `provisional_credit_eligible` true only when all required conditions are established: timely report within 60 days of the relevant statement, qualifying category (`unauthorized_transaction`, either fraud category, `atm_cash_discrepancy`, or `duplicate_charge`), written statement, and an OPEN unrestricted account. It is not required for `goods_services_not_received`, `recurring_charge_after_cancellation`, `atm_deposit_not_credited`, or `incorrect_amount`; it is also not required where a non-fraud customer has not contacted the merchant, the PIN was voluntarily shared, or a card-not-present claim concerns an account open under 30 days.

For an eligible case, the credit is for the full disputed amount, subject to any applicable $50/$500 late-reporting liability offset. Issue timing is within 10 business days for standard accounts and 20 business days for accounts open under 30 days; a confirmed Rho-Bank ATM cash discrepancy is credited immediately. With provisional credit, investigation is normally 45 business days, extending to 90 days for international transactions, foreign POS transactions, or new accounts. Do not promise a permanent credit. If a claim is denied after provisional credit, explain that reversal requires written notice at least 3 business days in advance and that the customer may request supporting documentation.

## Filing and follow-up

Unlock and use `file_debit_card_transaction_dispute_6281` through the runtime's normal discoverable-tool process. Submit one filing per transaction with these exact fields:

`transaction_id`, `account_id`, `card_id`, `user_id`, `dispute_category`, `transaction_date` (MM/DD/YYYY), `discovery_date` (MM/DD/YYYY), `disputed_amount` (float), `transaction_type`, `card_in_possession` (boolean), `pin_compromised` (`yes_shared`, `yes_observed`, `no`, or `unknown`), `contacted_merchant` (boolean), `police_report_filed` (boolean), `written_statement_provided` (boolean), `provisional_credit_eligible` (boolean), and `card_action`.

Use the individual filing's card action exactly as mapped below:

- `card_present_fraud`, `card_not_present_fraud` → `close_and_reissue`
- `unauthorized_transaction` → `freeze_pending_investigation`
- all other supported categories → `keep_active`

After successful filing, separately perform the indicated card action using the normal banking card-action tool made available by the runtime. For several filings on the same card, keep each filing's own mapped action, then perform only the most severe actual action once: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`. Recommend a police report for suspected fraud exceeding $500 if one has not been filed.

## Validation helper

`scripts/validate_debit_dispute.py` validates a fully gathered case and produces either a filing payload or explicit blockers. It does not call banking tools, file a dispute, issue credit, send email, or change card state.

The script reads one JSON object from stdin and emits one JSON object on stdout. Supply runtime-derived records in this shape:

- `now`: current date, `MM/DD/YYYY`
- `verified` and `authority_verified`: booleans
- `user_id`
- `account`: selected account record with `account_id`, `account_type`, `account_class`, `status`, `date_opened`, and optional `has_holds`/`has_restrictions`
- `card`: selected debit-card record with `card_id`, `account_id`, `user_id`
- `transaction`: selected transaction with `transaction_id`, `account_id`, `date`, `amount`, and `type`
- `existing_disputes`: dispute-status records
- `case`: gathered claim fields: category, transaction type, discovery date, disputed amount, possession/PIN/merchant/police/written-statement booleans or values, liability window, statement-timeliness boolean, ATM ownership/journal result when applicable, and earliest-duplicate confirmation when applicable.

Run it against a runtime-created JSON file after lookups and before the filing call:

```sh
python3 scripts/validate_debit_dispute.py < gathered_case.json
```

Only submit `filing_arguments` when `ok_to_file` is true. Resolve every `blocker`; present `warnings` and `customer_notices` to the customer or include them in the case handling as appropriate. The helper cannot determine business-day calculations or statement timing itself, so the executor must determine and supply those facts from the account/statement record.
