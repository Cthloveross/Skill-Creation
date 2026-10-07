---
name: debit-card-dispute-intake-and-filing
description: Safely identify, validate, and file debit-card transaction disputes, including ATM discrepancies, missing goods or services, duplicate charges, merchant issues, and fraud or non-fraud unauthorized transactions. Use when a verified customer asks to dispute one or more debit-card transactions.
---

# Debit Card Dispute Intake and Filing

Treat account, card, transaction, dispute-history, and customer-statement facts as current runtime data. Never reuse an identity, account ID, card ID, transaction ID, tier, or filing result from another interaction.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Before filing, freezing, closing, or ordering a card, complete the runtime's required identity verification. A name, email address, account number, or lookup result alone is not verification. Normally confirm two of the customer’s date of birth, email, phone number, and address, then create the required `log_verification` audit record. Confirm that the customer is the cardholder or authorized account owner.

## Interaction principles

1. Before proceeding with an unauthorized-activity matter, explain Regulation E reporting timing: reported within 2 business days has maximum $50 liability; within 60 days has maximum $500 liability; after 60 days may mean unlimited liability and no recovery. Encourage prompt reporting.
2. If the customer requests one transaction at a time, honor that request. Do not require all transactions' facts before completing a fully supported current dispute.
3. **File promptly:** after live lookup and all required facts for the current transaction are available, file that transaction immediately. Do not defer it while asking about another transaction, provide a generic inability message, or transfer to a human without a concrete unsupported/blocking condition.
4. After a successful filing and any required disclosure, confirm it, then move to the next transaction. Ask only for the missing transaction-specific facts for that next matter.
5. For duplicate charges, identify and dispute the earliest duplicate transaction first.

## Runtime lookup and preflight sequence

Use the ordinary banking tools directly when available. If a named banking tool is discoverable in the runtime, unlock it first and call it through the discoverable-agent-tool wrapper using JSON arguments. Record and interpret each returned result; tool recommendations do not themselves execute a banking action.

For each account/card involved:

1. Retrieve accounts with `get_all_user_accounts_by_user_id_3847(user_id)`. Select the checking account tied to the transaction and confirm that it is `OPEN`; retain account ID, account class/tier, status, opening date, and any holds or restrictions.
2. Retrieve cards with `get_debit_cards_by_account_id_7823(account_id)`. Match the active card and, when supplied, its last four digits. Confirm card `account_id` is the selected account and returned `user_id` is the verified customer.
3. Retrieve posted account activity using `get_bank_account_transactions_9173(account_id)`. Match the exact transaction record by date, amount, and description; capture its transaction ID and date. Do not guess between ambiguous records.
4. Retrieve `get_debit_dispute_status_7483(user_id)`. Count `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED` disputes per account. The maximum number of open disputes is Entry 2, Mid 3, Premium 4, Elite 5.

Before every filing, establish all of the following:

- verified identity, authority, and ownership;
- transaction amount of at least $1.00 and transaction no more than 60 days old;
- an OPEN linked checking account and a customer-owned, matched debit card;
- available per-account dispute capacity, including disputes filed earlier in this interaction;
- exact transaction ID, transaction date, and transaction amount from the lookup;
- the customer’s discovery date, card-possession answer, PIN status, merchant-contact answer where applicable, and written-statement agreement.

Resolve a missing, contradictory, unmatched, or ineligible fact before filing. Do not treat an otherwise eligible current dispute as blocked merely because later disputes lack their details.

## Required intake facts

For the transaction currently being handled, collect:

- what happened, transaction date, charged amount, and merchant or ATM description;
- the date the customer first noticed the issue;
- whether they still possess the physical card;
- PIN status, exactly one of `yes_shared`, `yes_observed`, `no`, or `unknown`;
- whether they attempted resolution with the merchant for non-fraud merchant disputes;
- agreement that their account of events in this conversation may be used as their written statement;
- whether a police report was filed for fraud over $500; recommend one if it was not;
- for ATM disputes, whether the ATM was Rho-Bank owned or third-party.

An explicit agreement to use the current conversation as the customer’s written statement makes `written_statement_provided` true. A customer’s statement that an online order was card-not-present makes the transaction type `online_purchase`; PIN was not involved in that online purchase, so use `pin_compromised: "no"` if the customer confirms no PIN compromise.

## Category, transaction type, and card-action selection

Use exactly one `dispute_category`:

- `unauthorized_transaction`: unauthorized but fraud is not suspected, such as a trusted person using the card without permission;
- `card_present_fraud`: suspected fraud involving physical/in-store card use;
- `card_not_present_fraud`: suspected fraud involving online, phone, or other card-not-present use;
- `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` when the corresponding facts apply.

Use exactly one `transaction_type`: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.

Set filing metadata `card_action` as follows:

| Category | `card_action` |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `recurring_charge_after_cancellation` | `keep_active` |

A goods or services not received case is a non-fraud merchant dispute: once the customer confirms the goods never arrived and an unsuccessful merchant-contact attempt, file it as `goods_services_not_received`; do not reclassify it as fraud merely because the merchant refused a refund.

## ATM procedures

For a Rho-Bank ATM cash discrepancy, review corresponding checking-account/journal evidence. If the discrepancy is confirmed, provisional credit is immediate. If the journal shows the stated amount, explain that the claim is not validated but that a formal dispute may still be filed. For a Rho-Bank ATM deposit issue, obtain deposit images with `get_atm_deposit_images_8473` and compare them with the claim.

For a third-party ATM, process the filing as a chargeback/dispute and explain that the investigation may extend to 90 days; qualifying provisional credit is still due within 10 business days. Before filing a third-party ATM cash-discrepancy claim exceeding $200, disclose and document that:

- an Electronic Fund Transfer Error Resolution Affidavit will be sent to the registered email;
- it must be signed and returned within 10 business days;
- failure to return it may result in denial; and
- signing a false affidavit is a federal offense.

## Provisional-credit decision

Set `provisional_credit_eligible` true only where every applicable condition is established:

- timely reporting within 60 days of the statement date;
- category is `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`;
- written statement provided;
- linked checking account is OPEN with no holds or restrictions;
- required merchant-resolution attempt for a non-fraud merchant dispute is documented;
- PIN was not voluntarily shared; and
- the account is not under 30 days old for a card-not-present transaction.

Set it false for `goods_services_not_received`, `recurring_charge_after_cancellation`, `atm_deposit_not_credited`, and `incorrect_amount`, since those categories are not required provisional-credit cases. Do not claim eligibility if statement-reporting timing or account standing is unknown. Standard accounts generally require qualifying credit within 10 business days; accounts open fewer than 30 days require it within 20 business days. Qualifying credit is the disputed amount subject to any applicable late-reporting liability offset.

## Filing and actual card action

Once the current case is ready, call `file_debit_card_transaction_dispute_6281` once for that transaction with exactly:

`transaction_id`, `account_id`, `card_id`, `user_id`, `dispute_category`, `transaction_date` (MM/DD/YYYY), `discovery_date` (MM/DD/YYYY), `disputed_amount` (float), `transaction_type`, `card_in_possession` (boolean), `pin_compromised`, `contacted_merchant` (boolean), `police_report_filed` (boolean), `written_statement_provided` (boolean), `provisional_credit_eligible` (boolean), and `card_action`.

Confirm the tool result before telling the customer it was filed. For several transactions on one card, preserve the category-specific `card_action` in each individual filing. After successful filings, perform the single most severe actual action for that card: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`.

`card_action` is filing metadata; it does not itself change card status.

- Before `freeze_debit_card_3892`, reconfirm verified ownership and ACTIVE card status. Explain that new and recurring transactions will be declined while pending authorizations may still settle.
- Before `close_debit_card_4721`, reconfirm ownership, ACTIVE/PENDING status, pending-transaction and refund conditions, and closure conditions. A fraud-suspected closure bypasses the minimum-card-age condition but not other applicable safeguards. Use `fraud_suspected` as the reason for fraud closures.
- Order a replacement only after applying the account-tier replacement limits, waiting periods, exact delivery/design fees, available balance, and customer confirmation.
- If the separate freeze/close safeguards cannot be met, explain that specific blocker; this does not invalidate a dispute filing that was otherwise eligible.

## Planning helper

`scripts/plan_disputes.py` is a deterministic preflight checklist. It does not call bank tools, file disputes, or execute card actions. It accepts one JSON object on stdin and emits one JSON object on stdout.

Top-level input:

```json
{
  "as_of_date": "MM/DD/YYYY",
  "identity_verified": true,
  "user_id": "verified-user-id",
  "existing_disputes": [{"account_id": "...", "status": "OPEN"}],
  "disputes": ["case objects described in the script docstring"]
}
```

Run it with current lookup and customer data:

```sh
python3 scripts/plan_disputes.py <<'JSON'
{"as_of_date":"<MM/DD/YYYY>","identity_verified":true,"user_id":"<user-id>","existing_disputes":[],"disputes":[<current-case-objects>]}
JSON
```

Only use a returned `filing_args` when `ready_to_file` is true, and recheck live tool data immediately before the banking action. Treat `errors` as blockers, complete required disclosures before filing, and use `warnings` to inform the customer or document follow-up. Retain filing results, affidavit disclosures, and card-action results in the case record.
