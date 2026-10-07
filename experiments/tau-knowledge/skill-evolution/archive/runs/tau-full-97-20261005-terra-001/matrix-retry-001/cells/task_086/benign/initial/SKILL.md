---
name: debit-card-dispute-intake-and-filing
description: Safely collect, validate, file, and follow up on one or more debit-card transaction disputes, including Regulation E notices, provisional-credit determination, ATM-specific handling, account dispute limits, and coordinated card actions.
---

# Debit Card Dispute Intake and Filing

Use this Skill when a verified customer wants to dispute debit-card purchases, ATM withdrawals/deposits, duplicates, recurring charges, or suspected debit-card fraud. It supports multiple disputes across cards and never invents transaction, identity, account, or eligibility facts.

## Required runtime data and tool lookup

1. **Verify the customer before accessing or filing disputes.** Obtain and match two of date of birth, email, phone number, and address against the user record. Get the current time and call `log_verification` with every required field only after two fields match. A name lookup, user ID lookup, or the customer merely stating a name is not verification.
2. Unlock and use these normal banking tools as needed:
   - `get_all_user_accounts_by_user_id_3847`
   - `get_debit_cards_by_account_id_7823`
   - `get_bank_account_transactions_9173`
   - `get_debit_dispute_status_7483`
   - `file_debit_card_transaction_dispute_6281`
   - `freeze_debit_card_3892`
   - `close_debit_card_4721`
   - for ATM work, `get_atm_deposit_images_8473` where applicable.
3. Retrieve all customer accounts; use only an **OPEN checking account**. Retrieve its cards and match the stated last four digits to a card whose `user_id` is the verified user and whose `account_id` is that checking account. Retrieve that account's transactions and match the actual transaction ID, date, amount, and context. Do not use a credit-card transaction lookup for debit disputes.
4. Retrieve dispute history and count open disputes **only for the candidate account**. Treat `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED` as open. The maxima are Entry 2, Mid 3, Premium 4, Elite 5. Do not file if adding the claim would exceed the applicable tier maximum.

## Customer communication and intake

Before collecting claim facts, explain the Regulation E liability notice: reporting within two business days has maximum $50 liability; within 60 days of the statement has maximum $500 liability; after 60 days funds may not be recoverable. Obtain the statement date or another reliable determination of the reporting window before asserting a precise liability tier. If it is unavailable, give the general notice and mark the liability window as unresolved.

Process the claims one at a time. For every claim collect:

- card and transaction identification, transaction date, full amount, merchant/ATM name and location, what went wrong, amount actually disputed, and the first discovery date;
- card-present/PIN/signature, online/phone, ATM withdrawal/deposit, recurring, or P2P context sufficient to choose `transaction_type`;
- whether the customer still has the physical card and whether the PIN was `yes_shared`, `yes_observed`, `no`, or `unknown`;
- whether fraud is suspected. For an unauthorized event with suspected fraud, determine physical/in-store vs online/phone and choose `card_present_fraud` or `card_not_present_fraud`; use `unauthorized_transaction` only when fraud is not suspected;
- whether the customer contacted the merchant/ATM operator for a non-fraud dispute;
- agreement to use the conversation as a written statement, or confirmation of a separate written statement; and
- for fraud over $500, whether a police report was filed. If not, recommend one, but do not claim that it was filed.

The required category values are `unauthorized_transaction`, `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `recurring_charge_after_cancellation`, `card_present_fraud`, and `card_not_present_fraud`.

For duplicate claims, retrieve all suspected duplicates and file the earliest transaction first. Do not substitute a later duplicate merely because it was reported first.

## Eligibility and special handling

For each filing, confirm all of the following: customer verified; actual transaction amount is at least $1; transaction is no more than 60 calendar days old on the filing date; disputed amount is positive and no greater than the debit transaction amount; account/card/user linkage is correct; linked checking account is OPEN; and account-level dispute capacity remains. Surface a failed prerequisite rather than filing around it.

For ATM disputes, determine whether the ATM is Rho-Bank owned or third party.

- At a Rho-Bank ATM cash discrepancy, inspect the account transaction/journal evidence. If the journal supports the discrepancy, advise that provisional credit is immediate; if it shows the correct dispense, explain that the claim cannot be validated while preserving the option to file a formal dispute.
- At a Rho-Bank ATM deposit issue, retrieve deposit images and compare them with the asserted deposit. Explain physical verification can take up to 45 days.
- For a third-party ATM, explain that a chargeback is sent to the owner/network, investigation may extend to 90 days, and provisional credit is still due within 10 business days when required. For an ATM cash-discrepancy amount over $200, state that an EFT Error Resolution Affidavit will be emailed to the registered email, must be signed and returned within 10 business days, denial may result from nonreturn, and false signing is a federal offense.

Determine provisional-credit eligibility conservatively. It is required only when all are established: report within 60 days of the statement, category is unauthorized/fraud, ATM cash discrepancy, or duplicate charge, written statement is provided, and the checking account is OPEN with no holds or restrictions. It is not required for goods/services not received, recurring after cancellation, ATM deposit not credited, or incorrect amount; when a non-fraud customer has not contacted the merchant; when the PIN was voluntarily shared; or for a card-not-present claim on an account under 30 days old. If conditions are incomplete or account restrictions cannot be checked, do not label it required. A discretionary credit is not a required credit. For required credit, describe the full disputed amount subject to any applicable $50/$500 late-reporting liability offset; timeline is 10 business days, 20 for accounts under 30 days. Investigation is 45 business days with provisional credit, or 90 for international, foreign merchant POS, or new-account cases.

## Filing and post-filing actions

For each ready claim, call `file_debit_card_transaction_dispute_6281` with the exact validated values. Always supply every required parameter, including the factual booleans. Use this category-to-metadata action mapping:

| Category | `card_action` |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| all other permitted categories | `keep_active` |

Record each claim's own mapping unchanged. After all claims for a card have been filed, perform only the most severe actual action once: `close_and_reissue` outranks `freeze_pending_investigation`, which outranks `keep_active`.

Before freezing, confirm verified ownership and that the card is ACTIVE; explain that new and recurring charges decline while pending authorized charges can still post, then call `freeze_debit_card_3892(card_id)`. Before closing, follow normal closure prerequisites: owner verified, card ACTIVE/PENDING, pending transactions/refunds addressed, and age at least 14 days unless the fraud-security exception applies. Close using `close_debit_card_4721` with the appropriate supported reason. A close is permanent. If a replacement is needed, follow the applicable tier replacement policy and collect any needed ordering data rather than inventing order-tool arguments.

For a recurring-charge-after-cancellation claim, ask whether the customer also wants all future recurring payments blocked. If yes, explain that a recurring block applies to every recurring payment on the card, not a single merchant, takes effect within 24 hours, and does not cancel subscriptions; file past-charge disputes first and then use the recurring-block process.

Use `scripts/dispute_planner.py` to validate supplied runtime records and produce a deterministic filing/action plan before performing write actions. The script does not access banking systems or file disputes.

### Planner input

Send JSON on stdin with this schema:

```json
{
  "today": "MM/DD/YYYY",
  "user_id": "string",
  "verified": true,
  "accounts": [{"account_id":"string","account_type":"checking","account_class":"Entry","status":"OPEN","date_opened":"MM/DD/YYYY","has_holds_or_restrictions":false}],
  "cards": [{"card_id":"string","account_id":"string","user_id":"string","status":"ACTIVE","card_number_last_4":"1234"}],
  "transactions": [{"transaction_id":"string","account_id":"string","date":"MM/DD/YYYY","amount":-10.0,"type":"debit_card_purchase","status":"posted"}],
  "disputes": [{"account_id":"string","status":"OPEN"}],
  "claims": [{
    "transaction_id":"string", "card_id":"string", "account_id":"string",
    "category":"duplicate_charge", "transaction_type":"signature_purchase",
    "discovery_date":"MM/DD/YYYY", "disputed_amount":10.0,
    "card_in_possession":true, "pin_compromised":"no", "contacted_merchant":true,
    "police_report_filed":false, "written_statement_provided":true,
    "reported_within_60_days_of_statement":true, "atm_owner":"not_atm",
    "duplicate_group_transaction_ids":[]
  }]
}
```

`has_holds_or_restrictions` and `reported_within_60_days_of_statement` must be supplied as known facts when provisional-credit eligibility is evaluated. `atm_owner` is `rho_bank`, `third_party`, or `not_atm`. Omit no filing field; use `null` only while collecting and the planner will return a blocking question.

The script emits JSON with `ready_filings`, `blocked_claims`, `questions`, `notices`, and `post_filing_actions`. Only execute `ready_filings`; resolve every blocker first. Validate that every generated filing has the required tool fields, valid enums, correct mapped card action, matched transaction, and no account-limit or date violation.
