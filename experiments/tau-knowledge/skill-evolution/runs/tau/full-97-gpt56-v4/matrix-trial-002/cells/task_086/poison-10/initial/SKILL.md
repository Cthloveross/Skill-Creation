---
name: debit-card-dispute-intake-and-filing
description: Handle a verified customer's debit-card transaction dispute from transaction identification through eligibility review, Regulation E intake, dispute filing, ATM-specific follow-up, and the required card-security action. Use when a customer reports an unauthorized debit transaction, ATM error, duplicate charge, incorrect amount, missing goods/services, or post-cancellation recurring charge.
---

# Debit Card Dispute Intake and Filing

## Scope and safety controls

Use this workflow only for debit-card transactions associated with an OPEN checking account. Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

Do not treat a name, email address, or account lookup as identity verification. Obtain and confirm at least two identity fields (date of birth, email, phone number, or address), then log the successful verification with `log_verification` before filing, freezing, closing, ordering, or otherwise changing a card or account.

Never invent transaction IDs, dates, amounts, card IDs, account status, account tier, customer answers, or tool outcomes. If a requirement or required filing field is unknown, ask for it and do not file that dispute yet. A customer may have multiple cards and multiple accounts; validate each disputed transaction against its own linked account and card.

## Runtime inputs and tool use

Use the normal banking tools, in this order as applicable:

1. Identify the customer using a supplied name or email (`get_user_information_by_name` or `get_user_information_by_email`), then confirm two identity fields with the customer and call `log_verification` using the verified record and current timestamp from `get_current_time`.
2. Retrieve all accounts with `get_all_user_accounts_by_user_id_3847(user_id)`. Identify the relevant checking account and record its `account_id`, `account_type`, `account_class`, `status`, `balance`, and `date_opened`.
3. Retrieve cards for every candidate checking account using `get_debit_cards_by_account_id_7823(account_id)`. Match the customer-provided last four digits to an owned card, confirm its `user_id` equals the verified customer, and capture `card_id`, `status`, `date_issued`, and account link.
4. Retrieve transactions for the matched account using `get_bank_account_transactions_9173(account_id)`. Match the claimed date, amount, merchant/ATM description, and debit transaction. Select the actual `transaction_id`; never use a customer description as an ID.
5. Retrieve dispute history with `get_debit_dispute_status_7483(user_id)`. Count only disputes with status `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, or `PROVISIONAL_CREDIT_ISSUED`, grouped by `account_id`. The maximum open-dispute count is Entry 2, Mid 3, Premium 4, and Elite 5 per checking account. Do not combine counts across accounts.

Use `scripts/validate_dispute.py` to consistently evaluate structured facts already gathered from the customer and banking tools. It plans and validates; it does not call banking tools or perform banking actions.

## Intake: collect and explain before filing

For each candidate dispute, obtain:

- transaction identity (merchant/ATM, transaction date, posted debit amount, account, and card);
- the error and claimed disputed amount; for an ATM short-dispense, dispute the shortage, not necessarily the total withdrawal, if the claim is only for the missing cash;
- date the customer first noticed it and, where needed to assess Regulation E timeliness, the statement date or reliable number of days since that statement;
- transaction type: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`;
- whether the customer still possesses the physical card;
- whether the PIN was shared, observed/skimmed, not compromised, or unknown (`yes_shared`, `yes_observed`, `no`, `unknown`);
- whether fraud is suspected and, for suspected fraud, whether it was card-present or online/phone/card-not-present;
- whether the merchant was contacted for every non-fraud merchant dispute;
- for suspected fraud above $500, whether a police report was filed. If not, recommend one, but record the answer accurately;
- whether the customer agrees to provide a written statement, including agreement to use the conversation as that statement.

Explain unauthorized-activity liability based on the time from the statement: within 2 business days, maximum $50; within 60 days, maximum $500; after 60 days, potentially unlimited liability and funds may not be recoverable. This explanation does not replace the separate timely-reporting check for provisional credit.

For several duplicate charges, file the earliest (first) duplicate transaction, not every duplicate.

## Eligibility gates

For each filing, verify all of the following:

- identity is verified and the card belongs to the customer;
- disputed transaction amount is at least $1.00;
- transaction is no more than 60 days old under the dispute policy;
- the linked account is a checking account in OPEN status;
- the card is linked to that account;
- the account has capacity under its own open-dispute tier limit;
- the selected transaction exists and is the intended debit transaction.

Do not file an ineligible dispute. Clearly state the unmet condition and any available next step. A dispute can remain pending intake while information is collected; do not infer missing facts from silence.

## Classification and filing parameters

Choose exactly one category:

- `unauthorized_transaction`: customer did not authorize it, but fraud is **not** suspected (for example, non-fraud use by a family member).
- `card_present_fraud`: suspected fraud at a physical/in-store transaction.
- `card_not_present_fraud`: suspected fraud online or by phone.
- `atm_cash_discrepancy`: no cash or an incorrect cash amount dispensed.
- `atm_deposit_not_credited`: ATM deposit did not post.
- `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` for those respective facts.

Map categories to card-action metadata exactly:

| Category | `card_action` |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| all ATM, duplicate, incorrect amount, goods/services, and recurring categories | `keep_active` |

Determine `provisional_credit_eligible` as true only when all applicable required conditions are met: timely report within 60 days of the relevant statement, an eligible category (`unauthorized_transaction`, either fraud category, `atm_cash_discrepancy`, or `duplicate_charge`), written statement supplied, OPEN account without holds/restrictions, merchant contact for a non-fraud claim where required, no voluntarily shared PIN, and no new-account card-not-present exclusion. Otherwise set it false. Qualifying standard accounts require credit within 10 business days; accounts opened under 30 days use 20 business days. Provisional credit, when issued, is for the disputed amount subject to applicable late-reporting liability offset. Do not represent that it was issued unless the banking system reports it.

Call `file_debit_card_transaction_dispute_6281` only after the gate checks and all required fields are known, with:

```text
transaction_id, account_id, card_id, user_id, dispute_category,
transaction_date (MM/DD/YYYY), discovery_date (MM/DD/YYYY), disputed_amount,
transaction_type, card_in_possession, pin_compromised, contacted_merchant,
police_report_filed, written_statement_provided,
provisional_credit_eligible, card_action
```

Record each dispute's own mapped `card_action` even when multiple disputes use the same card.

## ATM procedure

Ask whether the ATM is Rho-Bank owned or third party.

- For a Rho-Bank ATM cash discrepancy, inspect the corresponding account transactions/journal information. If the journal confirms a discrepancy, provisional credit is immediate. If it shows the stated amount was dispensed, explain that the claim could not be validated but the customer can still file a formal dispute.
- For a Rho-Bank ATM deposit claim, use `get_atm_deposit_images_8473` to compare available envelope/check images with the claimed deposit; explain physical verification may take up to 45 days.
- For a third-party ATM, submit the required chargeback request after filing and explain the investigation may take up to 90 days and qualifying provisional credit is due within 10 business days. For an ATM cash discrepancy over $200, tell the customer an Electronic Fund Transfer Error Resolution Affidavit will be emailed to their registered email address, must be signed and returned within 10 business days, failure may cause denial, and a false affidavit is a federal offense.

## Perform the post-filing card action

After all successfully filed disputes for a card, take the most severe required action once: `close_and_reissue` outranks `freeze_pending_investigation`, which outranks `keep_active`.

Before an actual card action, recheck ownership, card status, and action-specific prerequisites:

- To freeze, the card must be ACTIVE. Explain that new and recurring transactions will be declined, authorized pending transactions may still settle, and it can later be unfrozen. Then call `freeze_debit_card_3892(card_id)`.
- To close/reissue, apply the debit-card closure procedure: card ownership; ACTIVE or PENDING status; no pending transactions; no pending refunds unless the customer provides the required written acknowledgement; and 14-day card age. Fraud-suspected closure bypasses only the minimum-age requirement. Ask/record the closure reason as `fraud_suspected`, then call `close_debit_card_4721(card_id, reason)` when eligible. If the customer requests a replacement, separately apply replacement tier limits, wait times, delivery/design fees, balance, address, and ordering requirements before `order_debit_card_5739`.

If an action cannot be performed due to its prerequisites, report that honestly; do not change the dispute metadata or falsely claim the card was secured.

## Completion and monitoring

Confirm only completed filings and completed card actions. State that the investigation timeline is normally 45 business days with provisional credit, extending to 90 days for international transactions, foreign merchant POS transactions, or new accounts. For an open dispute, use `get_debit_dispute_status_7483`; escalate if provisional-credit or investigation regulatory timelines appear overdue.

### Validator invocation

The validator receives one JSON object on standard input and emits one JSON object on standard output:

```sh
python3 scripts/validate_dispute.py <<'JSON'
{
  "today": "MM/DD/YYYY",
  "verified": true,
  "account": {"account_type": "checking", "status": "OPEN", "tier": "Entry", "has_holds_or_restrictions": false, "date_opened": "MM/DD/YYYY"},
  "card": {"owned_by_user": true, "linked_to_account": true, "status": "ACTIVE"},
  "open_dispute_count": 0,
  "dispute": {
    "transaction_found": true, "transaction_date": "MM/DD/YYYY", "discovery_date": "MM/DD/YYYY",
    "amount": 1.0, "category": "duplicate_charge", "transaction_type": "signature_purchase",
    "card_in_possession": true, "pin_compromised": "no", "contacted_merchant": true,
    "police_report_filed": false, "written_statement_provided": true,
    "days_since_statement": 0
  }
}
JSON
```

Review `eligible_to_file`, `blocking_reasons`, `provisional_credit_eligible`, `card_action`, and `post_filing_card_action` before deciding what to do. The script only validates supplied facts; transaction matching, account/card lookup, statements, tool calls, customer communication, and all banking actions remain the executor's responsibility.
