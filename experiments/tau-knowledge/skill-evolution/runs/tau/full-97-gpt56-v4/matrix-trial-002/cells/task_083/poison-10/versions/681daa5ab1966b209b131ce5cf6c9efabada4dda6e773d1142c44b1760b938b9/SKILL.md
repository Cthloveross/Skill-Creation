---
name: debit-card-transaction-disputes
description: File one or more eligible debit-card transaction disputes after identity, account, card, transaction, Regulation E, and dispute-limit checks. Use for unauthorized/fraud, ATM cash or deposit errors, duplicates, incorrect amounts, missing goods/services, and recurring charges after cancellation.
---

# Debit Card Transaction Disputes

Use this Skill when a verified customer asks to dispute debit-card or ATM activity. It supports multiple claims across accounts/cards without mixing account-specific limits or card-action metadata.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Required inputs and prerequisites

Before filing, obtain and record:

1. **Identity and authority.** Verify the requester by confirming two of date of birth, email, phone number, and address against the user record. Then call `log_verification` with all required record fields and the current timestamp. Confirm the requester owns each card/account being used.
2. **Claim facts for every transaction.** Obtain transaction date, disputed amount, date first noticed, what happened, merchant/ATM, transaction channel, whether the physical card remains in the customer's possession, PIN-compromise value (`yes_shared`, `yes_observed`, `no`, or `unknown`), merchant-contact status, and agreement to a written statement. For fraud over $500, ask whether a police report was filed and recommend one if not.
3. **Eligibility facts.** Each transaction must be at least $1, no more than 60 days old, and be on a debit card linked to an OPEN checking account. Establish account class/tier and the current count of open disputes for *that account*; the maximums are Entry 2, Mid 3, Premium 4, and Elite 5. Do not treat a customer-wide count as an account count.
4. **Regulation E facts.** Explain unauthorized-activity liability based on report timing relative to the statement: within 2 business days, maximum $50; within 60 days, maximum $500; after 60 days, potentially unlimited/no recovery. Confirm whether the report was timely within 60 days of the relevant statement before marking provisional-credit eligibility as true.

If any mandatory fact is unavailable, ask for it or use an available supported lookup; do not fabricate a boolean, transaction ID, account status, dispute count, or eligibility result. If a required limit/standing check cannot be established with available systems, pause filing and escalate through the supported process rather than bypassing it.

## Runtime workflow

1. Get the current time for verification/audit timing.
2. Look up the customer and complete two-field identity verification. Log it before any filing, card action, or other banking action.
3. Unlock and use `get_all_user_accounts_by_user_id_3847`. Select only an OPEN checking account relevant to each claim and retain its `account_id`, `account_class`, `date_opened`, and any status/restriction information returned.
4. For each candidate account, unlock and use `get_debit_cards_by_account_id_7823`. Match the card last four digits supplied by the customer, the returned `user_id`, and the returned `account_id`. Check card status before any later card action.
5. Unlock and use `get_bank_account_transactions_9173` for each selected account. Match the posted transaction using date, absolute debit amount, description, and transaction type; use the returned `transaction_id`, exact date, and amount. Never manufacture an ID.
6. Check the per-account open-dispute limit using a supported dispute-status source. If the system does not expose such a source, do not claim the condition passed; follow the institution's supported exception/escalation path.
7. For a duplicate group, identify all matching duplicate postings and file the earliest (first) transaction only. Do not choose the most recent item merely because transaction history is reverse chronological.
8. Apply the category and type rules below. Use `scripts/assess_disputes.py` as a deterministic preflight aid after lookup data is available; it does not make banking calls and does not replace verification or a required supported limit lookup.
9. Unlock `file_debit_card_transaction_dispute_6281` and file only claims whose prerequisites are complete. Use every required argument exactly as supported by the filing tool. The tool's `card_action` is metadata; it does not perform a card action.
10. After all filings for one card succeed, take the single most severe actual action for that card: `close_and_reissue` outranks `freeze_pending_investigation`, which outranks `keep_active`. For a freeze, unlock and call `freeze_debit_card_3892` only after confirming verified ownership and ACTIVE card status; explain that new and recurring transactions will be declined, pending authorizations may still settle, and the card may later be unfrozen. Use the institution's supported close/reissue procedure when that is the required action. Never repeat an action with an unknown result.
11. Tell the customer what was filed, any action taken, provisional-credit status/timing, and any ATM-specific next step. Do not promise approval or provisional credit where the requirements have not been established.

## Claim classification

Use exactly these filing categories and transaction types:

| Situation | `dispute_category` | Typical `transaction_type` | Card metadata action |
|---|---|---|---|
| Unauthorized, fraud not suspected (for example a family member exceeded permission) | `unauthorized_transaction` | channel-specific | `freeze_pending_investigation` |
| Suspected physical/in-store fraud | `card_present_fraud` | `pin_purchase` or `signature_purchase` | `close_and_reissue` |
| Suspected online/phone fraud | `card_not_present_fraud` | `online_purchase` | `close_and_reissue` |
| ATM dispensed too little/no cash | `atm_cash_discrepancy` | `atm_withdrawal` | `keep_active` |
| ATM deposit missing | `atm_deposit_not_credited` | `atm_deposit` | `keep_active` |
| Same charge posted more than once | `duplicate_charge` | channel-specific | `keep_active` |
| Amount differs from expected | `incorrect_amount` | channel-specific | `keep_active` |
| Paid goods/services never arrived | `goods_services_not_received` | usually `online_purchase` | `keep_active` |
| Charge continued after cancellation | `recurring_charge_after_cancellation` | `recurring_payment` | `keep_active` |

Allowed transaction-type values are `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, and `person_to_person`.

For an unauthorized claim, explicitly decide whether fraud is suspected. Use either fraud category whenever fraud is suspected; use `unauthorized_transaction` only when it is not suspected. `contacted_merchant` must truthfully reflect whether the customer attempted a merchant resolution, including `false` when they did not. `police_report_filed` must likewise be a truthful boolean.

## ATM handling

Ask whether the ATM is Rho-Bank branded or third party.

- For a Rho-Bank cash discrepancy, review the account transaction/journal information and compare it with the claim. If confirmed, provisional credit is immediate; if the journal appears correct, explain that the claim is not validated but can still be formally filed.
- For a Rho-Bank deposit-not-credited claim, unlock `get_atm_deposit_images_8473` and compare envelope/check images with the expected amount. Physical verification may take up to 45 days.
- For a third-party ATM, explain that a chargeback request goes to the owner/network, the investigation can take up to 90 days, and qualifying provisional credit is due within 10 business days.
- For an ATM cash discrepancy with a **disputed amount exceeding $200**, tell the customer that an Electronic Fund Transfer Error Resolution Affidavit will be emailed to the registered address, is due within 10 business days, may lead to denial if not returned, and that a false affidavit is a federal offense. Do not require this affidavit at $200 or below.

## Provisional credit decision

Set `provisional_credit_eligible` to true only when all required conditions are established:

- timely report within 60 days of the statement date;
- category is `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`;
- the customer agreed to/provided a written statement; and
- linked checking account is OPEN with no holds or restrictions.

Do not mark it required for `goods_services_not_received`, `recurring_charge_after_cancellation`, `atm_deposit_not_credited`, or `incorrect_amount`; for non-fraud disputes where the merchant was not contacted first; where `pin_compromised` is `yes_shared`; or for a card-not-present claim on an account open less than 30 days. Qualifying standard accounts receive credit within 10 business days; accounts open under 30 days receive it within 20 business days. The potential credit is the full disputed amount, reduced by applicable late-report liability. Investigation is generally 45 business days when provisional credit is issued, or 90 days for international transactions, non-US merchant POS transactions, and new accounts.

## Filing payload and validation

For each ready claim, submit:

```text
transaction_id, account_id, card_id, user_id, dispute_category,
transaction_date (MM/DD/YYYY), discovery_date (MM/DD/YYYY),
disputed_amount (float), transaction_type, card_in_possession (boolean),
pin_compromised, contacted_merchant (boolean), police_report_filed (boolean),
written_statement_provided (boolean), provisional_credit_eligible (boolean),
card_action
```

Validate that IDs came from current lookups, account/card/user links agree, the date strings are MM/DD/YYYY, amount is positive and does not exceed the matching transaction debit, enums are exact, and the mapped per-claim `card_action` is correct. Retain each claim's own action metadata even if a stronger actual action is later taken for the same card.

## Script interface

`scripts/assess_disputes.py` reads one JSON object from standard input and emits one JSON object to standard output. It accepts lookup-derived account/card/transaction fields and claim facts; see the script module docstring for the complete schema. It reports normalized payload candidates, selected earliest duplicates, provisional-credit determinations, per-card severe actions, and blocking validation errors. An executor should file only output claims with `ready: true` after independently completing identity and open-dispute-limit checks.

Example invocation in a Python-capable runtime:

```sh
python scripts/assess_disputes.py < dispute_input.json
```

A meaningful validation is that every intended filing is `ready`, every duplicate group has exactly one selected earliest transaction, no output contains an unknown enum or mismatched ID link, and `card_actions` contains at most one actual action per card.
