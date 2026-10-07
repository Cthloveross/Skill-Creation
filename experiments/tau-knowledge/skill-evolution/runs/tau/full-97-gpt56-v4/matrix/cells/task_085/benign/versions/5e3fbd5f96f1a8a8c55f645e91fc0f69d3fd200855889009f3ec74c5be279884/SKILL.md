---
name: debit-card-atm-dispute
version: 1.1.0
description: Handle a verified customer's debit-card dispute, including ATM cash shortages, by collecting Regulation E facts, locating and validating the linked account/card/transaction, determining provisional-credit treatment, filing the dispute through the authorized tool, and taking the mapped card action.
---

# Debit-card dispute workflow

Use this Skill for debit-card transaction disputes: unauthorized/fraud charges, ATM errors, duplicates, wrong amounts, merchant problems, and charges after cancellation. Work on one transaction at a time. This Skill directs use of normal banking tools; its script never files, credits, freezes, or reissues a card.

## 1. Verify before accessing or filing

1. Use a customer-provided identifier to find the user record. A lookup is not verification.
2. Have the customer confirm two of the four identity fields (date of birth, registered email, phone number, address) and compare each to the record. Do not reveal an unconfirmed value in the question.
3. After two matches, obtain the current time and call `log_verification` using the complete retrieved record and that timestamp.
4. For unauthorized activity, explain the Regulation E exposure before filing: within 2 business days, maximum $50; within 60 days, maximum $500; after 60 days, unlimited liability and recovery may be unavailable. Capture when the customer discovered the issue. Do not label an ATM malfunction as fraud without facts supporting fraud.

## 2. Gather one complete dispute record

Collect the merchant/ATM, transaction date, transaction amount, amount the customer seeks to dispute, discovery date, card possession, PIN status, prior merchant/ATM contact, and consent to use the conversation as a written statement. Ask whether fraud is suspected and, if so, whether the transaction was physical or online/phone. For suspected fraud over $500, ask whether a police report was filed and recommend one if not.

Use only these categories:

- `unauthorized_transaction` only when the transaction was not authorized but fraud is **not** suspected;
- `card_present_fraud` or `card_not_present_fraud` for suspected physical or online/phone fraud respectively;
- `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` as supported by the facts.

Use only these transaction types: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`. An ATM short-dispense is `atm_cash_discrepancy` plus `atm_withdrawal`. For duplicate charges, file the earliest duplicate, not a later duplicate.

Ask the required filing questions explicitly:

- “Do you still have your physical debit card in your possession?”
- “Do you believe your PIN may have been compromised?” Record exactly `yes_shared`, `yes_observed`, `no`, or `unknown`.
- “Have you attempted to resolve this directly with the merchant?”
- “Are you willing to provide a written statement describing what happened? We can use this conversation as your written statement if you agree.”

## ATM-specific handling

Determine whether an ATM was Rho-Bank branded or third-party before describing the process.

- **Rho-Bank cash discrepancy:** retrieve the corresponding account transaction/journal evidence and compare it to the claim. If confirmed, issue provisional credit immediately through the authorized process. If the record shows the correct amount was dispensed, explain that the claim is not validated by the journal but may still be formally disputed.
- **Rho-Bank deposit not credited:** retrieve deposit envelope/check images with `get_atm_deposit_images_8473` and compare them to the expected deposit. Explain that physical verification can take up to 45 days.
- **Rho-Bank card retained:** no transaction dispute is needed solely because the machine retained the card. Offer branch retrieval within 3 business days or closing the old card and ordering a replacement. File a dispute only for separate unauthorized transactions.
- **Third-party ATM:** submit the dispute as a chargeback request to the owner/network. Explain that investigation can take up to 90 days and provisional credit is still required within 10 business days when applicable. For a cash discrepancy **over $200**, tell the customer that an EFT Error Resolution Affidavit will be emailed to their registered email address, must be signed and returned within 10 business days, and that a false affidavit is a federal offense.

## 3. Locate and validate authorized records

After verification, unlock and use these documented tools:

1. `get_all_user_accounts_by_user_id_3847` to find the customer-selected checking account and confirm it is OPEN. Do not choose among multiple plausible accounts based solely on a nickname.
2. `get_debit_cards_by_account_id_7823` to find the card linked to that account and confirm its `user_id` matches the verified customer.
3. `get_bank_account_transactions_9173` to locate the exact transaction ID. Results are reverse chronological; compare the date, description, debit amount, type, and status to the claim. Do not substitute a merely similar transaction.

Before filing, ensure the customer is verified; the checking account is OPEN; the debit card is linked; the transaction and disputed amount are at least $1.00; and the transaction is no more than 60 days old. Check the account-specific open-dispute limit using authorized records: Entry 2, Mid 3, Premium 4, Elite 5. The limit is per account, not per customer. Do not invent a mapping from a product nickname to these tiers. If the declared runtime has no separate authorized count/restriction lookup, do not manufacture one or guess its outcome: submit the documented filing request with the otherwise validated facts so the normal endpoint can apply its server-side eligibility controls. A rejection is not a filing; report it accurately and use normal escalation if needed.

For a Rho-Bank cash discrepancy, use the ATM-specific process above. Never claim journal confirmation or immediate credit unless the relevant authorized result confirms it. Deposit images are not a substitute for cash-discrepancy journal review.

## 4. Decide provisional credit and liability metadata

Required provisional credit applies only when all supported conditions hold: timely reporting within 60 days of the statement, an OPEN unrestricted checking account, a written statement, and category one of `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`. It is not required for `goods_services_not_received`, `recurring_charge_after_cancellation`, `atm_deposit_not_credited`, or `incorrect_amount`; when a non-fraud merchant dispute has not first been taken to the merchant; when the PIN was voluntarily shared; or for a new-account card-not-present dispute. ATM contact is not merchant contact.

For a qualifying standard account, credit is due within 10 business days; a new account may take 20. A Rho-Bank ATM journal-confirmed cash discrepancy is immediate. With provisional credit, the normal investigation deadline is 45 business days; it is 90 days for international transactions, merchants outside the US, or new accounts. Otherwise do not promise more than the tool/result supports. The amount is the full disputed amount, subject to any late-report liability offset. If the investigation rejects the claim, provisional credit can be reversed only after written notice at least 3 business days in advance; the customer may request supporting documentation.

The filing endpoint also requires `customer_max_liability_amount`. Determine the applicable timing band from the customer’s reporting/statement facts: within 2 business days is $50, within 60 days is $500, and after 60 days is `-1` (unlimited). Where a finite maximum is requested for a specific disputed transaction, it cannot exceed that disputed amount. Do not guess a statement date from a transaction date.

## 5. File and perform card handling

Unlock `file_debit_card_transaction_dispute_6281` and call it only with the validated values. The required payload is:

`transaction_id`, `account_id`, `card_id`, `user_id`, `dispute_category`, `transaction_date` (`MM/DD/YYYY`), `discovery_date` (`MM/DD/YYYY`), positive `disputed_amount`, `transaction_type`, `card_in_possession`, `pin_compromised`, `contacted_merchant`, `police_report_filed`, `written_statement_provided`, `provisional_credit_eligible`, `customer_max_liability_amount`, and `card_action`.

Map each filing’s `card_action` exactly:

- fraud categories → `close_and_reissue`
- `unauthorized_transaction` → `freeze_pending_investigation`
- every other allowed category → `keep_active`

The field is metadata. After all disputes for one card are filed successfully, take only the single most severe actual card action: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`. For a most-severe freeze, unlock and call the documented `freeze_debit_card_3892` once for that card. For close/reissue, use the authorized close/reissue tool made available by the normal workflow; do not substitute a freeze. Do not change an individual filing’s mapping because another filing is more severe. A cash-discrepancy-only case stays active. Report only actions, filings, and credit timing actually returned as successful.

## Deterministic preflight helper

Run `python3 scripts/dispute_preflight.py` with one JSON object on stdin. It emits one JSON object on stdout and performs no bank action.

Required core inputs are the proposed filing fields plus: `verified`, `account_status`, `account_restricted`, `card_linked`, `transaction_amount`, `today`, `timely_statement_report`, `account_is_new`, `open_disputes`, `account_tier`, and `liability_band`. `liability_band` is `within_2_business_days`, `within_60_days`, or `after_60_days`. The helper returns `ok_to_file`, `blocking_issues`, `filing_payload`, `provisional_credit_eligible`, and `customer_max_liability_amount`, plus nonblocking `warnings`. It deliberately refuses to derive statement timing, a tier, restrictions, or open-dispute count from missing data.

Example invocation (with a JSON case assembled from authorized records):

```sh
python3 scripts/dispute_preflight.py < case.json
```

Validate that `ok_to_file` is true before treating `filing_payload` as a complete proposed endpoint payload. A false result must be resolved through authorized records or the normal escalation path; do not replace missing facts with guessed values. `warnings` are customer/process follow-ups and do not by themselves mean a filing failed.
