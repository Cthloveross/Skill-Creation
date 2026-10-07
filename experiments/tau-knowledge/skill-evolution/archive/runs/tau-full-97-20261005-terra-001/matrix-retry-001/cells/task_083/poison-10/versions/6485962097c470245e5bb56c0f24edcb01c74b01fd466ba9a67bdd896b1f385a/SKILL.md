---
name: debit-card-dispute-intake-and-filing
description: Safely intake, validate, file, and follow up on debit-card transaction disputes, including ATM discrepancies, duplicate charges, merchant issues, and fraud/non-fraud unauthorized transactions. Use when a verified customer seeks to dispute one or more debit-card transactions.
---

# Debit Card Dispute Intake and Filing

Use this skill for debit-card dispute work only. Treat lookup results and customer statements as runtime data; do not assume account, card, transaction, tier, or identity details from a prior interaction.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

A name, email, account number, or a lookup result alone is not identity verification. Complete the runtime's required verification (normally confirm two of date of birth, email, phone number, and address), then log it with `log_verification` before filing, freezing, closing, or ordering a card. Confirm the customer is the cardholder/authorized account owner.

## Required data collection and disclosures

1. **Disclose Regulation E timing before proceeding.** Explain the customer’s maximum liability for unauthorized activity reported within 2 business days ($50), within 60 days ($500), and after 60 days (potentially unlimited/no recovery). Prompt reporting is important.
2. Work one transaction at a time if the customer requests that approach. For every proposed dispute, obtain:
   - transaction date, amount, merchant/ATM description, and when the customer first noticed the problem;
   - whether the customer has the physical card;
   - PIN status: `yes_shared`, `yes_observed`, `no`, or `unknown`;
   - whether they contacted the merchant (particularly for non-fraud merchant disputes);
   - agreement to use their account of events/conversation as a written statement;
   - for fraud over $500, whether a police report was filed; recommend one if it was not;
   - for ATM disputes, whether the ATM is Rho-Bank owned or third-party.
3. Retrieve the customer’s accounts with `get_all_user_accounts_by_user_id_3847`. Select an OPEN checking account linked to the transaction/card; capture its account class/tier and opening date.
4. Retrieve cards for that checking account with `get_debit_cards_by_account_id_7823`. Match the selected card ID and, where supplied, last four digits. Confirm returned `user_id` matches the verified customer.
5. Retrieve transactions with `get_bank_account_transactions_9173(account_id)` and match the actual transaction ID, date, debit/credit amount, description, and status. Do not infer a match when several records fit the description.
6. Retrieve history with `get_debit_dispute_status_7483(user_id)`. Count open disputes **per account**, not per customer. Treat `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED` as open; do not count final/closed statuses. Limits are Entry 2, Mid 3, Premium 4, Elite 5.

For each filing, confirm: verified customer/authority; a transaction of at least $1; transaction no more than 60 days old; sufficient per-account dispute capacity; an OPEN linked checking account; and a matched card owned by the customer. Resolve missing or contradictory data before filing.

When duplicate transactions exist, dispute the earliest transaction first. Do not substitute a later duplicate merely because it is easier to locate.

## Category and field selection

Choose only one exact `dispute_category`:

- `unauthorized_transaction`: not authorized, but fraud is **not** suspected (for example, a trusted person used the card without permission).
- `card_present_fraud`: fraud suspected and physical/in-store card use.
- `card_not_present_fraud`: fraud suspected and online/phone/card-not-present use.
- `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` when those facts apply.

Choose only one exact `transaction_type`: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.

Set `card_action` per filing, not per card group:

| Category | Filing `card_action` |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| All ATM, duplicate, amount, goods/services, and recurring categories | `keep_active` |

## ATM-specific handling

For a Rho-Bank ATM cash discrepancy, review the corresponding checking-account transactions/journal evidence. If a discrepancy is confirmed, provisional credit is immediate; if the journal shows the stated amount, explain that the claim is not validated but formal filing remains available. For a Rho-Bank ATM deposit issue, retrieve deposit images using `get_atm_deposit_images_8473` and compare them to the claimed deposit.

For a third-party ATM, submit the dispute/chargeback through the normal filing process. Explain that investigation may extend to 90 days and qualifying provisional credit remains due within 10 business days. For a third-party ATM cash discrepancy exceeding $200, tell the customer that an Electronic Fund Transfer Error Resolution Affidavit will be sent to their registered email, must be signed and returned within 10 business days, and failure to return it may cause denial; false statements are a federal offense. Record/document that disclosure.

## Provisional-credit decision

Set `provisional_credit_eligible` to true only when all applicable required conditions are satisfied:

- timely reporting within 60 days of the statement date;
- category is `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`;
- written statement is provided;
- checking account is OPEN without holds/restrictions;
- any applicable merchant-resolution attempt for a non-fraud merchant dispute has been made;
- PIN was not voluntarily shared; and
- the account is not under 30 days old for a card-not-present transaction.

The excluded categories (`goods_services_not_received`, `recurring_charge_after_cancellation`, `atm_deposit_not_credited`, and `incorrect_amount`) are not required provisional-credit cases. Do not claim eligibility when the statement-reporting timing or account-standing facts are unknown. Qualifying credit is for the disputed amount, subject to applicable late-reporting liability offsets. Standard accounts require credit within 10 business days; accounts open under 30 days require it within 20 business days. Investigations with provisional credit are generally 45 business days, extending to 90 for international, foreign POS, or new-account cases.

## Filing and subsequent card action

After all prerequisites and mandatory tool values are known, use `file_debit_card_transaction_dispute_6281` once per eligible transaction with exactly these fields:

`transaction_id`, `account_id`, `card_id`, `user_id`, `dispute_category`, `transaction_date` (MM/DD/YYYY), `discovery_date` (MM/DD/YYYY), `disputed_amount` (float), `transaction_type`, `card_in_possession` (boolean), `pin_compromised`, `contacted_merchant` (boolean), `police_report_filed` (boolean), `written_statement_provided` (boolean), `provisional_credit_eligible` (boolean), and `card_action`.

After successful filings, group successful disputes by card and perform the single most severe actual action: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`.

- Before `freeze_debit_card_3892`, reconfirm verified ownership and that the card is ACTIVE. Explain that new and recurring charges are declined while pending authorizations may settle.
- Before `close_debit_card_4721`, reconfirm ownership, ACTIVE/PENDING card status, pending-transaction/refund requirements, and closure conditions. Fraud-suspected closure bypasses the minimum-card-age condition, but other relevant closure safeguards still apply. Use reason `fraud_suspected` for fraud closures. Complete replacement ordering only under the applicable replacement-tier, waiting-period, limit, delivery-fee, design-fee, and customer-confirmation requirements.
- Do not freeze or close merely because the filing metadata requests it if the separate action’s safety prerequisites are not met. Explain the blocker and follow the relevant escalation/process path.

## Planning helper

`scripts/plan_disputes.py` performs deterministic preflight validation and creates proposed filing arguments. It does not call banking tools and does not authorize or execute a filing or card action.

It reads one JSON object from stdin and writes one JSON object to stdout. Required top-level fields are `as_of_date` (`MM/DD/YYYY`), `identity_verified` (boolean), `user_id`, `existing_disputes` (list), and `disputes` (list). Each dispute supplies runtime lookup data in `account`, `card`, and `transaction`, plus the filing fields described in the script’s input schema. `account.has_hold_or_restriction` and `timely_reporting` must be explicit for a provisional-credit decision.

Runnable invocation pattern (replace every angle-bracketed value with current runtime data):

```sh
python3 scripts/plan_disputes.py <<'JSON'
{"as_of_date":"<MM/DD/YYYY>","identity_verified":true,"user_id":"<user_id>","existing_disputes":[],"disputes":[<current-dispute-objects>]}
JSON
```

Use the output as a checklist. Only use a `filing_args` object after its `ready_to_file` is true and independently verify the live tool data immediately before the banking action. Validate that each tool response confirms the intended transaction/dispute; retain filing IDs and disclosures in the case record.
