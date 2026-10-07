---
name: debit-card-dispute-intake-and-filing
description: Safely intake, validate, and file one or more debit-card transaction disputes. Use for unauthorized debit-card activity, ATM cash/deposit errors, duplicate charges, incorrect amounts, goods/services not received, and post-cancellation recurring charges.
---

# Debit Card Dispute Intake and Filing

Use this workflow when a customer asks to dispute debit-card transactions. It supports multiple cards and disputes, but complete the evidence and eligibility review for each transaction before filing it. Do not infer missing facts or substitute a credit-card workflow.

**Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.**

## 1. Verify, identify, and retrieve records

1. Verify the customer using two of the four identity fields (date of birth, email, phone number, address), then call `log_verification` with all required identity fields and the current timestamp. A customer merely providing an email address is not verification.
2. Identify the user with the provided identifying information if necessary.
3. Unlock and use `get_all_user_accounts_by_user_id_3847` for the verified user. Select only the checking account associated with the reported card. Confirm account ownership, account ID, tier/class, OPEN status, and whether any hold or restriction exists.
4. For each candidate checking account, unlock and use `get_debit_cards_by_account_id_7823`. Match the card by last four digits and confirm its `card_id`, linked `account_id`, `user_id`, and status.
5. Unlock and use `get_bank_account_transactions_9173(account_id)`. Match every reported item to a debit transaction by date, merchant/ATM/recipient, amount, and transaction ID. Transactions are reverse chronological, so inspect all plausible matches. Do not file without the exact transaction ID.
6. Unlock and use `get_debit_dispute_status_7483(user_id)`. Count only OPEN disputes for the specific checking account. The maximum open-dispute counts are Entry 2, Mid 3, Premium 4, and Elite 5. Limits are per account, not customer.

Stop and explain the blocker rather than filing if verification/authority/ownership cannot be established; the account is not OPEN; no linked card exists; the transaction cannot be matched; the transaction is under $1; it is more than 60 days old; or filing would exceed the account's open-dispute limit.

## 2. Collect facts before filing

Work one card and one transaction at a time if requested. For each item obtain:

- merchant, ATM, or recipient; transaction date; full transaction amount; exact disputed amount; and when the customer first noticed the issue;
- the applicable transaction type: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`;
- what happened and the requested category;
- whether the card remains in the customer's possession and whether the PIN was `yes_shared`, `yes_observed`, `no`, or `unknown`;
- for a non-fraud claim, whether the customer attempted merchant resolution;
- for an unauthorized transaction, whether fraud is suspected and whether it was physically present/in-store or online/phone;
- whether the customer agrees to provide a written statement. The conversation can be the statement only if the customer agrees;
- whether reporting was within 60 days of the statement showing the transaction. Do not equate transaction date with statement date;
- for fraud disputes over $500, whether a police report was filed; if not, recommend one.

For ATM issues, determine whether the ATM is a bank ATM or a third-party ATM and retain that detail for investigation. It does not change the prescribed filing category. For a cash-dispensing error, use the cash amount actually missing as `disputed_amount`, not necessarily the full withdrawal amount.

If duplicate transactions exist, identify the duplicate set and dispute the earliest transaction in that set.

Before proceeding, explain the applicable Regulation E maximum-liability exposure based on when the customer noticed the unauthorized activity: within 2 business days of the statement, $50; within 60 days, $500; after 60 days, potentially unlimited/non-recoverable. Do not state a tier unless the relevant statement timing is known.

## 3. Categorize and determine actions

Use only these filing categories:

- `unauthorized_transaction`: not authorized but fraud is **not** suspected.
- `card_present_fraud`: fraud suspected and a physical/in-store card transaction.
- `card_not_present_fraud`: fraud suspected and an online/phone transaction.
- `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` as their names indicate.

Required category-to-metadata card action:

| Category | `card_action` |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| all ATM, duplicate, incorrect amount, goods/services, and recurring categories | `keep_active` |

Set each filing's `card_action` from this table even if several disputes are filed on the card. After all filings for a card, perform only the most severe actual card action once: close/reissue > freeze > keep active. Do not freeze a card unless it is ACTIVE. For a freeze, disclose that new and recurring transactions will decline, pending authorized transactions may still post, and it can be unfrozen later; then use `freeze_debit_card_3892` only after the dispute succeeds. For close/reissue, use only the normal declared/discovered banking tools and first apply replacement tier, fee, waiting-period, and customer-notice requirements. Never claim an actual card action occurred based only on the `card_action` filing field.

For a recurring charge after cancellation, optionally offer a future recurring-payment block after filing the past-charge dispute. Explain that it blocks **all** recurring payments, takes effect within 24 hours, does not cancel merchant subscriptions, and requires merchant cancellation separately. With customer confirmation, use `set_debit_card_recurring_block_7382` with `block_recurring: true`.

## 4. Provisional-credit decision

Set `provisional_credit_eligible` to true only when all required conditions are met:

1. the report was within 60 days of the statement;
2. category is `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`;
3. a written statement was provided; and
4. the checking account is OPEN with no hold or restriction.

Also do **not** mark it required when the non-fraud customer has not contacted the merchant, the PIN was voluntarily shared (`yes_shared`), or the account is under 30 days old and the transaction is card-not-present. Required provisional credit is the full disputed amount (subject to any documented late-report liability offset). Required timing is within 10 business days, or 20 for an account open under 30 days. Explain that qualifying cases can have a 45-business-day investigation, extended to 90 days for international transactions, POS purchases outside the US, or new accounts; an adverse result can reverse the credit with at least three business days' written notice.

## 5. Validate and file

Use `scripts/validate_debit_dispute.py` before filing. It is a deterministic preflight aid; it does not call bank tools and does not create disputes. Supply retrieved facts rather than guessed values. Resolve every `errors` item; investigate `warnings` before proceeding.

Then unlock and call `file_debit_card_transaction_dispute_6281` once per eligible transaction with all of these exact fields:

`transaction_id`, `account_id`, `card_id`, `user_id`, `dispute_category`, `transaction_date`, `discovery_date`, `disputed_amount`, `transaction_type`, `card_in_possession`, `pin_compromised`, `contacted_merchant`, `police_report_filed`, `written_statement_provided`, `provisional_credit_eligible`, and `card_action`.

Record the returned dispute IDs and summarize what was filed, any requested documentation, card action actually completed, provisional-credit eligibility/timing, and expected investigation timeline. Do not state that a discretionary provisional credit was issued unless a bank action/result confirms it.

## Preflight script

`python3 scripts/validate_debit_dispute.py` reads one JSON object from standard input and emits one JSON object to standard output. It accepts this schema (all dates use `MM/DD/YYYY`):

```json
{
  "today": "MM/DD/YYYY",
  "verified": true,
  "account": {"account_id": "...", "status": "OPEN", "tier": "Entry", "date_opened": "MM/DD/YYYY", "has_hold_or_restriction": false},
  "card": {"card_id": "...", "account_id": "...", "user_id": "...", "status": "ACTIVE"},
  "open_disputes": [{"account_id": "...", "status": "OPEN"}],
  "disputes": [{
    "transaction": {"transaction_id": "...", "account_id": "...", "date": "MM/DD/YYYY", "amount": -12.34, "type": "debit_card_purchase"},
    "dispute_category": "duplicate_charge",
    "transaction_date": "MM/DD/YYYY",
    "discovery_date": "MM/DD/YYYY",
    "disputed_amount": 12.34,
    "transaction_type": "signature_purchase",
    "card_in_possession": true,
    "pin_compromised": "no",
    "contacted_merchant": true,
    "written_statement_provided": true,
    "reported_within_60_days_of_statement": true,
    "fraud_suspected": false,
    "channel": "physical",
    "duplicate_candidates": [{"transaction_id": "...", "date": "MM/DD/YYYY"}]
  }]
}
```

It returns `ok`, `errors`, `warnings`, and `decisions` (including a calculated category card action and provisional-credit determination). `today` is needed for the 60-calendar-day transaction-age check. Unknown statement timing must remain false/unknown operationally and prevents a required-provisional-credit finding.
