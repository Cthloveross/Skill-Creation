---
name: debit-card-transaction-dispute
version: 1.1.0
description: Investigate and file one or more verified-customer debit-card transaction disputes, including Regulation E notice, account/card/transaction validation, ATM handling, provisional-credit assessment, and required card actions. Use for debit-card unauthorized use, ATM errors, duplicate charges, incorrect amounts, undelivered goods/services, and recurring charges after cancellation.
---

# Debit Card Transaction Dispute

Use this Skill to process each reported debit-card transaction and submit every eligible confirmed filing. Scripts only plan; the execution agent must use normal banking tools to file disputes and perform any required card action.

## Required runtime tools

Use these tools as appropriate:

- `get_all_user_accounts_by_user_id_3847(user_id)`
- `get_debit_cards_by_account_id_7823(account_id)`
- `get_bank_account_transactions_9173(account_id)`
- `get_debit_dispute_status_7483(user_id)`
- `file_debit_card_transaction_dispute_6281(...)`
- `freeze_debit_card_3892(card_id)`
- `close_debit_card_4721(card_id, reason)`
- `get_atm_deposit_images_8473(...)` for a Rho-Bank ATM deposit-not-credited case, when available.

Unlock discoverable internal tools before calling them. Do not invent an ATM-network chargeback tool or its parameters. For a third-party ATM, file the dispute and then use an available supported chargeback workflow; escalate only if that separate operational action cannot be performed.

## 1. Verify the customer

A lookup by name or email locates a record but is not identity verification. Before filing, freezing, closing, or disclosing account activity, confirm at least two of date of birth, email, phone number, and address. Retrieve the customer record and current time, then call `log_verification` with all required identity fields and the returned timestamp.

If verification fails, do not file or take card action. Use the appropriate human-transfer reason only when a specialist is actually needed: `account_ownership_dispute` for an identity/ownership failure requiring specialist handling, or `fraud_or_security_concern` for an actual fraud/account-compromise concern.

## 2. Give the Regulation E notice, then continue gathering facts

For an unauthorized-activity report, explain the reported-time liability brackets before proceeding:

- within 2 business days of the statement: maximum $50;
- within 60 days of the statement: maximum $500;
- after 60 days: potentially unlimited liability and funds may not be recoverable.

Record the customer's timeliness statement. Do not use calendar days as a substitute for business days for the two-day bracket.

**Do not require an exact statement date to submit an otherwise confirmed dispute.** The filing tool has no statement-date field. If the customer affirmatively reports the issue within 60 days and the transaction and discovery dates are known, proceed with the filing after ordinary pre-filing checks. Lack of an exact statement date may prevent a definitive determination that provisional credit is required, but it is not a reason to abandon, transfer, or defer the dispute itself. Do not characterize such a customer as having unlimited liability merely because the statement date is unavailable.

Customers may provide facts gradually and may ask to address one transaction at a time. Respect that request, but once all necessary facts for a transaction are confirmed, file it rather than reopening unrelated questions.

## 3. Match and validate records

For each card/account involved:

1. Retrieve the customer's accounts. Select the linked `checking` account and verify it is `OPEN`.
2. Retrieve its debit cards. Match any supplied last four digits, verify card ownership and account linkage, and retain the actual `card_id`.
3. Retrieve account transactions. Match the posted debit by date, amount, merchant/ATM description, and transaction type. Use the returned transaction ID and date; use the absolute posted debit amount or the actual supported shortage/error amount, not an assumed amount.
4. Retrieve dispute history. Count non-final disputes for the same account (`OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED`). Limits are per account: Entry 2, Mid 3, Premium 4, Elite 5.
5. Confirm the amount is at least $1, the transaction is no more than 60 days old, no open dispute already targets it, and the account limit has not been reached.

Do not substitute a similarly named transaction. For duplicates, identify and file the earliest transaction in the duplicate set, not a later duplicate. If a true filing prerequisite fails, explain it and do not file that claim; do not prevent other independent eligible claims from being processed.

## 4. Collect a complete record per transaction

Retain distinct facts for each claim; do not reuse an answer across cards or transactions unless the customer expressly confirms it applies to both.

Collect:

- matched transaction, account, card, date, and amount;
- `discovery_date` in `MM/DD/YYYY`;
- dispute circumstances and whether fraud is suspected;
- physical-card possession;
- PIN state: `yes_shared`, `yes_observed`, `no`, or `unknown`;
- whether the merchant or ATM operator was contacted;
- whether the customer agrees that the conversation is their written statement;
- police-report status for suspected fraud over $500 (recommend a report if none was filed);
- the customer's within-60-statement-days report; and
- account opening date and any holds/restrictions for provisional-credit assessment.

Use only these categories:

- `unauthorized_transaction` for unapproved activity where fraud is **not** suspected, including a family member using the card beyond permission;
- `card_present_fraud` for suspected fraud with physical/in-store card-present use;
- `card_not_present_fraud` for suspected online, phone, or other card-not-present fraud;
- `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` when applicable.

Use only these transaction types: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, and `person_to_person`. Ask if a classification is genuinely ambiguous; do not recategorize family-member use as stranger fraud merely because the charge was unapproved.

## 5. ATM-specific procedure

Determine and record whether the ATM was Rho-Bank branded or third-party.

- For a Rho-Bank cash discrepancy, review available transaction/journal evidence against the claim. If confirmed, credit is immediate; if the journal is correct, explain the result but allow a formal dispute.
- For a Rho-Bank deposit-not-credited case, retrieve available deposit images and explain that physical verification can take up to 45 days.
- For a retained card at a Rho-Bank ATM, offer retrieval within three business days or closure/replacement. No dispute is needed unless another unauthorized transaction exists.
- For a third-party ATM, submit the dispute and required chargeback through the available network workflow. Explain the investigation can take up to 90 days.

An Electronic Fund Transfer Error Resolution Affidavit is required only for a **third-party ATM cash discrepancy whose disputed amount exceeds $200**. For such a claim, state that it will be emailed to the registered address, must be signed and returned within 10 business days, failure to return it may cause denial, and false signing is a federal offense. Do not request or require this affidavit for a dispute amount of $200 or less.

## 6. Provisional-credit assessment

Set `provisional_credit_eligible` to `true` only when all required conditions are established:

1. the customer reported within 60 days of the statement;
2. the category is `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`;
3. a written statement was provided; and
4. the checking account is OPEN with no holds or restrictions.

Set it `false` when eligibility is disproved or an exclusion applies: an ineligible category, a non-fraud claim with no merchant contact, voluntarily shared PIN (`yes_shared`), or a card-not-present claim on an account less than 30 days old. If statement-based timeliness or another eligibility fact remains unknown, submit an otherwise ready filing with `provisional_credit_eligible: false`; clearly avoid promising required provisional credit until that fact is resolved. This does not block filing.

For a qualifying claim, provisional credit is the full disputed amount less any applicable late-report liability offset. It is due within 10 business days after filing, or 20 business days for an account open less than 30 days. Investigation is normally 45 business days when provisional credit is issued, with 90-day extensions for international transactions, eligible foreign POS transactions, or new accounts. Explain that adverse findings can reverse credit after at least three business days' written notice.

## 7. File every ready confirmed dispute

Submit one filing for each ready transaction using exactly these tool arguments:

`transaction_id`, `account_id`, `card_id`, `user_id`, `dispute_category`, `transaction_date`, `discovery_date`, `disputed_amount`, `transaction_type`, `card_in_possession`, `pin_compromised`, `contacted_merchant`, `police_report_filed`, `written_statement_provided`, `provisional_credit_eligible`, and `card_action`.

Per-filing `card_action` metadata is fixed:

| Category | Filing `card_action` |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| all other supported categories | `keep_active` |

When multiple claims use the same card, retain each filing's own mapped metadata. After all filings for that card, take one actual action using the most severe action: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`.

Before freezing, recheck verification, ownership, and `ACTIVE` card status; explain that new and recurring transactions will decline while pending items can settle. Before closing/reissuing, check verified ownership, `ACTIVE` or `PENDING` status, pending transactions/refunds, and the card-age rule. Fraud-suspected closures bypass the 14-day age requirement. If an actual card-action prerequisite fails, preserve the submitted filing and explain or escalate the card-action limitation rather than undoing or withholding the dispute.

## Planner helper

`scripts/dispute_planner.py` validates one prepared case deterministically. It reads one JSON object from stdin and writes one JSON object to stdout. It makes no bank calls and never files a dispute.

Input schema:

```json
{
  "now_date": "MM/DD/YYYY",
  "verified": true,
  "account": {"account_id": "...", "account_type": "checking", "account_class": "Premium Tier", "status": "OPEN", "date_opened": "MM/DD/YYYY", "has_holds_or_restrictions": false},
  "card": {"card_id": "...", "account_id": "...", "user_id": "...", "status": "ACTIVE"},
  "user_id": "...",
  "transaction": {"transaction_id": "...", "account_id": "...", "date": "MM/DD/YYYY", "amount": -10.0, "type": "debit_card_purchase", "status": "posted"},
  "existing_disputes": [{"account_id": "...", "transaction_id": "...", "status": "OPEN"}],
  "case": {"category": "duplicate_charge", "transaction_type": "signature_purchase", "discovery_date": "MM/DD/YYYY", "disputed_amount": 10.0, "card_in_possession": true, "pin_compromised": "no", "contacted_merchant": true, "police_report_filed": false, "written_statement_provided": true, "timely_reported_within_60_statement_days": true, "atm_owner": "third_party", "duplicate_candidates": []}
}
```

Output includes filing blockers, missing facts, account-limit data, provisional-credit assessment, notices, mapped card action, and complete `filing_arguments` when ready. `timely_reported_within_60_statement_days` is needed to determine required provisional credit, not to decide whether an otherwise confirmed dispute may be filed. When unknown, output filing arguments still contain the required boolean `provisional_credit_eligible: false`.
