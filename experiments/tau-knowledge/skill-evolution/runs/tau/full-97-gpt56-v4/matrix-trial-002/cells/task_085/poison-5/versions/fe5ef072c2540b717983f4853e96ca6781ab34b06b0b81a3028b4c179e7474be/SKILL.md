---
name: debit-card-dispute-intake
version: 1.0.0
description: Safely intake, validate, file, and communicate debit-card transaction disputes, including Regulation E eligibility, account/card/dispute-limit checks, fraud classification, and special Rho-Bank or third-party ATM handling.
---

# Debit Card Dispute Intake and Filing

Use this Skill when a verified customer wants to dispute a debit-card transaction, including an unauthorized purchase, suspected fraud, duplicate, merchant issue, incorrect amount, recurring charge, or ATM cash/deposit error. It supports one dispute at a time; repeat the workflow for separate issues and retain the most severe required card action per card.

## Safety and prerequisites

Before **any** banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For this workflow:

1. Identify the customer and verify identity by confirming at least two of date of birth, email, phone number, and address against a user-information lookup. Record the successful verification with `log_verification` before taking a banking action.
2. Confirm the customer owns the selected checking account and card.
3. Retrieve accounts with `get_all_user_accounts_by_user_id_3847`. The selected account must be a checking account, OPEN, and eligible. Establish its tier/account class for the per-account open-dispute limit: Entry 2, Mid 3, Premium 4, Elite 5.
4. Retrieve the account's debit cards with `get_debit_cards_by_account_id_7823`. Select the relevant active debit card linked to that account and belonging to the customer.
5. Retrieve account transactions with `get_bank_account_transactions_9173`; match the customer’s described transaction by date, amount, description, type, and account. Never invent a transaction ID. Transactions are reverse chronological, so explicitly identify the earliest transaction if duplicate transactions are being disputed.
6. Retrieve dispute history with `get_debit_dispute_status_7483` and count only OPEN, PENDING_DOCUMENTATION, UNDER_REVIEW, and PROVISIONAL_CREDIT_ISSUED disputes for the selected `account_id`. Do not file if doing so would exceed that account’s tier limit.
7. Do not file when the amount is below $1.00, the transaction is over 60 days old, the debit card is not linked to an OPEN checking account, ownership/identity cannot be established, or the matching transaction cannot be identified. Explain the specific unresolved prerequisite and request only the information needed to continue.

## Customer intake and disclosure

At the start of a potential unauthorized-activity dispute, explain the applicable liability exposure based on when the customer noticed the activity: within 2 business days: maximum $50; within 60 days: maximum $500; after 60 days: potentially unlimited and funds may not be recoverable. Use statement timing where available; do not claim a precise liability tier when statement/business-day facts are unavailable.

Collect and retain:

- transaction date, amount, description, transaction type, account, and debit card;
- the date the customer first discovered the issue;
- a clear account of what happened;
- whether fraud is suspected and, if so, whether the transaction was physically present or online/phone;
- whether the physical card remains in the customer’s possession;
- PIN status: `yes_shared`, `yes_observed`, `no`, or `unknown`;
- whether the customer attempted to resolve a non-fraud merchant dispute directly with the merchant;
- whether a police report was filed for fraud above $500; recommend one if it was not filed; and
- whether the customer agrees that their narrative can be used as their written statement. Set `written_statement_provided` true only on agreement or receipt of a statement.

Use the following category rules exactly:

- Use `card_present_fraud` for suspected fraud involving a physical/in-store transaction.
- Use `card_not_present_fraud` for suspected fraud involving online or phone activity.
- Use `unauthorized_transaction` only where the transaction was not authorized but fraud is not suspected.
- Use the specific ATM, duplicate, amount, goods/services, or cancelled-recurring category that matches the customer’s facts.

Use only these filing categories: `unauthorized_transaction`, `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `recurring_charge_after_cancellation`, `card_present_fraud`, and `card_not_present_fraud`.

Use only these transaction types: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.

## ATM-specific procedure

For every ATM dispute, determine whether the ATM is Rho-Bank branded or third-party; do not infer ownership solely from an incomplete description.

For a Rho-Bank ATM cash discrepancy, review the corresponding account’s transaction history and available ATM journal-related records, compare the journal result with the claim, and document the comparison. If the discrepancy is confirmed, provisional credit is issued immediately. If records indicate the correct cash amount, explain that the claim cannot be validated from the journal but the customer may still file a formal dispute.

For a Rho-Bank ATM deposit-not-credited dispute, use `get_atm_deposit_images_8473` when available and compare the image/evidence with the claimed deposit. Explain that physical verification can take up to 45 days.

For a third-party ATM dispute, file the chargeback request through the normal dispute process, explain the investigation may extend to 90 days, and explain that provisional credit remains due within 10 business days when required. For an ATM cash discrepancy over $200, tell the customer that an Electronic Fund Transfer Error Resolution Affidavit will be emailed to their registered address, must be returned within 10 business days, and that failure to return it may lead to denial; false affidavits are a federal offense.

A retained card is not itself a transaction dispute. For a Rho-Bank ATM, offer branch retrieval within 3 business days or card closure/replacement; file a dispute only for a separate transaction issue.

## Provisional credit decision

Assess provisional-credit eligibility only after the necessary account, statement-timing, and dispute facts are established. It is required when all of these are true:

1. timely reporting within 60 days of the statement containing the transaction;
2. category is `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`;
3. a written statement is provided; and
4. the checking account is OPEN and has no hold or restriction.

It is not required for `goods_services_not_received`, `recurring_charge_after_cancellation`, `atm_deposit_not_credited`, or `incorrect_amount`; when a merchant-resolution attempt is required for a non-fraud merchant dispute and has not occurred; if the PIN was voluntarily shared; or for a card-not-present transaction on an account less than 30 days old. For a confirmed Rho-Bank ATM cash discrepancy, follow the immediate-credit procedure above.

A qualifying credit is the full disputed amount, subject to any applicable late-report liability offset. Standard accounts require credit within 10 business days; accounts open fewer than 30 days require it within 20 business days. With provisional credit, normal investigation completion is 45 business days, extending to 90 for international transactions, merchant POS outside the United States, or new accounts. Do not promise a discretionary credit as a required credit.

`scripts/validate_dispute.py` provides a deterministic preflight check. It does not replace evidence gathering, bank tool calls, statement-timing analysis, ATM journal review, or a required banking action.

## File the dispute and secure the card

After all prerequisites are met, unlock and invoke `file_debit_card_transaction_dispute_6281` through the normal discoverable-agent-tool workflow. Supply every required argument with verified data:

- `transaction_id`, `account_id`, `card_id`, `user_id`
- `dispute_category`, `transaction_date` and `discovery_date` in `MM/DD/YYYY`
- `disputed_amount`, `transaction_type`, `card_in_possession`, `pin_compromised`
- `contacted_merchant`, `police_report_filed`, `written_statement_provided`, `provisional_credit_eligible`
- `card_action`

Set filing metadata `card_action` as follows: fraud categories → `close_and_reissue`; `unauthorized_transaction` → `freeze_pending_investigation`; every other valid category → `keep_active`.

The metadata does not itself change the card. After filing, separately perform the indicated card action through the applicable normal banking tools. If several disputes are filed for one card, preserve each filing’s own mapped `card_action`, then perform only the most severe actual action once: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`. Check current card status immediately before that action and do not duplicate an already-completed action.

Provide a concise confirmation identifying the disputed transaction, category, amount, expected process/timeline, any affidavit or documentation obligation, and any card action performed. For future status requests, use `get_debit_dispute_status_7483`; escalate disputes that appear to miss the 10/20-day provisional-credit or 45/90-day investigation timelines.

## Preflight helper

Run the helper with JSON on standard input and consume its JSON output:

```sh
python3 scripts/validate_dispute.py <<'JSON'
{
  "dispute_category": "atm_cash_discrepancy",
  "transaction_type": "atm_withdrawal",
  "transaction_date": "MM/DD/YYYY",
  "discovery_date": "MM/DD/YYYY",
  "disputed_amount": 100.0,
  "card_in_possession": true,
  "pin_compromised": "no",
  "contacted_merchant": false,
  "police_report_filed": false,
  "written_statement_provided": true,
  "account_open": true,
  "account_has_hold_or_restriction": false,
  "timely_within_60_days_of_statement": true,
  "account_age_days": 60,
  "open_dispute_count": 0,
  "account_tier": "Entry"
}
JSON
```

The output contains `valid`, `errors`, `warnings`, expected `card_action`, and a conservative provisional-credit assessment. Treat an `errors` entry as a stop condition until resolved. The helper cannot validate a transaction ID, card linkage, customer verification, duplicate ordering, account ownership, statement date, ATM ownership, journal result, or tool availability; those checks remain mandatory.
