---
name: debit-card-dispute-filing
description: Verify a debit-card customer, retrieve debit-account transaction evidence, collect claim facts, determine filing and provisional-credit fields, file eligible debit-card disputes, and coordinate any required card action.
---

# Debit Card Dispute Filing

Use this Skill for debit-card transaction disputes involving ATM errors, merchant problems, duplicate or incorrect charges, recurring charges, and unauthorized debit-card activity. It supports filing each complete claim promptly while continuing intake for additional claims.

## Required workflow

1. **Verify before account access or filing.** Match two customer-supplied identity factors against the user record (date of birth, email, phone number, or address). After two match, call `log_verification` using the complete returned user record and the current timestamp. A name or user ID alone is not verification.
2. Give the Regulation E liability notice before proceeding: reports within two business days have maximum $50 liability, within 60 days of the statement have maximum $500 liability, and later reporting may make recovery unavailable.
3. Unlock and use the normal banking tools documented for this work:
   - `get_all_user_accounts_by_user_id_3847`
   - `get_debit_cards_by_account_id_7823`
   - `get_bank_account_transactions_9173`
   - `get_debit_dispute_status_7483`
   - `file_debit_card_transaction_dispute_6281`
   - `freeze_debit_card_3892` and `close_debit_card_4721` only where the category requires an actual card action.
4. Retrieve the verified user's accounts. For each requested card, select an **OPEN checking** account and a card whose account and user IDs match that account and user. Match the customer-provided last four digits only after retrieving the card records.
5. Retrieve the selected checking account's transaction history and use the actual transaction record for the transaction ID, date, amount, type, and status. Debit disputes must use this bank-account transaction lookup, not a credit-card transaction lookup.
6. Retrieve dispute history and count only open disputes for the candidate account. `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED` consume capacity. Limits are Entry 2, Mid 3, Premium 4, and Elite 5 per account.

Do not wait for information about unrelated future claims. Once a requested claim is complete, timely, linked to an OPEN checking account, and within account capacity, file it; then continue collecting the next claim.

## Claim intake

Collect and confirm for each claim:

- transaction, card, merchant/ATM, transaction date, full transaction amount, disputed amount, and discovery date;
- what happened and the correct category;
- transaction context needed for `transaction_type`;
- whether the physical card remains in the customer's possession and PIN status: `yes_shared`, `yes_observed`, `no`, or `unknown`;
- for unauthorized claims, whether fraud is suspected; use `card_present_fraud` for physical fraud and `card_not_present_fraud` for online/phone fraud. Use `unauthorized_transaction` only if fraud is not suspected;
- merchant contact for a non-fraud merchant dispute;
- written-statement agreement. If the customer agrees to use the conversation as their statement, set `written_statement_provided` to `true`;
- police-report status for suspected fraud above $500. Recommend a report if none exists, but do not falsely state one was filed.

Allowed categories are `unauthorized_transaction`, `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `recurring_charge_after_cancellation`, `card_present_fraud`, and `card_not_present_fraud`.

Allowed transaction types are `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, and `person_to_person`.

For duplicates, retrieve all relevant transactions and file the earliest duplicate first.

## Eligibility and timely reporting

Before filing, validate that the actual transaction is at least $1, no more than 60 days old, and that the disputed amount is positive and does not exceed the transaction amount. Confirm account/card/user linkage, an OPEN checking account, and available dispute capacity.

Ask for the statement date when it is available so the precise Regulation E liability window can be documented. However, **do not leave an otherwise complete recent claim unfiled merely because the available banking tools cannot retrieve a statement date and the customer does not know it**. Record that the statement date was unavailable, retain the general liability notice, and proceed using the established recent transaction and discovery facts. Do not invent a statement date or say an exact liability tier is known.

## ATM and provisional-credit handling

Determine whether an ATM is Rho-Bank or third party.

- For a Rho-Bank cash discrepancy, inspect available journal/transaction evidence. A confirmed discrepancy supports immediate provisional credit; a journal showing correct cash does not prevent a formal filing.
- For a Rho-Bank deposit-not-credited issue, retrieve deposit images and explain that physical verification can take up to 45 days.
- For a third-party ATM cash discrepancy, explain that a network/owner chargeback is submitted and investigation can take up to 90 days. A discrepancy over $200 requires the EFT Error Resolution Affidavit, sent to the registered email and due within 10 business days; warn that nonreturn may cause denial and false signing is a federal offense.

Set `provisional_credit_eligible` to true when the available facts establish timely reporting, a written statement, an OPEN unrestricted account, and a qualifying category: unauthorized transaction, either fraud category, ATM cash discrepancy, or duplicate charge. ATM cash-discrepancy eligibility is not defeated merely because the customer has not contacted the independent ATM operator. For a recent claim where statement-date lookup is unavailable, contemporaneous transaction/discovery reporting is sufficient operational evidence to continue the filing and mark qualifying provisional-credit eligibility true; do not fabricate a statement date.

Set it to false for goods/services not received, recurring charges after cancellation, ATM deposits not credited, and incorrect amounts. It is also not required when a non-fraud merchant dispute lacks merchant contact, the PIN was voluntarily shared, or a card-not-present dispute is on an account opened less than 30 days ago. Required credit is for the full disputed amount subject to any applicable liability offset; normal timing is 10 business days, or 20 for a new account.

## Filing and card actions

For each ready claim, call `file_debit_card_transaction_dispute_6281` with all required fields exactly as validated:

`transaction_id`, `account_id`, `card_id`, `user_id`, `dispute_category`, `transaction_date`, `discovery_date`, `disputed_amount`, `transaction_type`, `card_in_possession`, `pin_compromised`, `contacted_merchant`, `police_report_filed`, `written_statement_provided`, `provisional_credit_eligible`, and `card_action`.

Use the following metadata action mapping for every individual filing:

- `card_present_fraud`, `card_not_present_fraud` → `close_and_reissue`
- `unauthorized_transaction` → `freeze_pending_investigation`
- all other categories → `keep_active`

After all filings for the same card, perform only the single most severe required actual action: close/reissue outranks freeze, which outranks keep active. Do not freeze or close a card for a `keep_active`-only set of claims. Before freezing, verify the card is ACTIVE and explain the effects. Before closing, follow normal closure prerequisites and use the fraud-security exception only for a fraud-related closure.

For a recurring-charge-after-cancellation claim, ask whether the customer also wants all future recurring payments blocked. Explain that a block affects every recurring payment on the card, takes effect within 24 hours, and does not itself cancel subscriptions.

## Deterministic planner

Run `scripts/dispute_planner.py` before write actions when normalized runtime records are available. It performs no banking action. Send JSON on stdin and read JSON from stdout.

Input schema:

```json
{
  "today": "MM/DD/YYYY",
  "verified": true,
  "user_id": "string",
  "accounts": [{"account_id": "string", "account_type": "checking", "account_class": "Mid", "status": "OPEN", "date_opened": "MM/DD/YYYY", "has_holds_or_restrictions": false}],
  "cards": [{"card_id": "string", "account_id": "string", "user_id": "string", "status": "ACTIVE"}],
  "transactions": [{"transaction_id": "string", "account_id": "string", "date": "MM/DD/YYYY", "amount": -10.0, "type": "debit_card_purchase", "status": "posted"}],
  "disputes": [{"account_id": "string", "status": "OPEN"}],
  "claims": [{"transaction_id": "string", "account_id": "string", "card_id": "string", "category": "goods_services_not_received", "transaction_type": "online_purchase", "discovery_date": "MM/DD/YYYY", "disputed_amount": 10.0, "card_in_possession": true, "pin_compromised": "no", "contacted_merchant": true, "police_report_filed": false, "written_statement_provided": true, "reported_within_60_days_of_statement": null, "atm_owner": "not_atm"}]
}
```

`reported_within_60_days_of_statement` may be `true`, `false`, or `null` when the statement date cannot be obtained. `null` does not block a recent otherwise complete filing; the planner records a notice and uses transaction/discovery recency for a qualifying provisional-credit plan. Explicit account restrictions block provisional-credit eligibility. The output contains `ready_filings`, `blocked_claims`, `questions`, `notices`, and `post_filing_actions`. Execute only `ready_filings`, and resolve any listed filing blocker first.
