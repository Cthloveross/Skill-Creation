---
name: debit-card-transaction-dispute
version: 1.1.0
description: Use for a verified customer who wants to file one or more debit-card transaction disputes. It gathers required facts, validates Regulation E and account/card prerequisites, files eligible claims, and applies the required card action.
---

# Debit-Card Transaction Dispute

Use this Skill for debit-card purchases, ATM errors, unauthorized activity, duplicate charges, incorrect amounts, missing goods/services, or charges after cancellation. Do not use it for credit-card disputes.

## Safety, disclosure, and identity

Before any banking action, verify identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

1. Identify the customer, retrieve the customer record, and have the customer independently confirm **two of four** fields: date of birth, email, phone number, and address. A name, an account email, or values returned by a lookup are not confirmations.
2. After two fields match, get the current time and call `log_verification` with the complete retrieved record and that timestamp. Do not perform account, card, or dispute actions until it succeeds.
3. Before proceeding with an unauthorized-activity matter, disclose the Regulation E liability bands: reported within two business days of the statement, maximum $50; within 60 days, maximum $500; after 60 days, potentially unlimited liability and recovery may not be available. Do not state that a particular band applies without the relevant statement and reporting dates.
4. Never invent customer answers, account/card/transaction IDs, dates, amounts, account status, account tier, or tool results. If a required fact is absent or ambiguous, ask or stop rather than filing.

## Gather facts for every requested transaction

Ask for merchant or ATM, transaction date, amount, reason, date first noticed, and whether other transactions are to be disputed. Obtain or determine:

- the linked checking account, debit card, cardholder, and matched posted debit transaction;
- transaction type, dispute category, and whether fraud is suspected;
- whether the physical card remains in the customer’s possession;
- PIN status: exactly `yes_shared`, `yes_observed`, `no`, or `unknown`;
- whether the merchant has been contacted for a non-fraud claim;
- whether the customer agrees that the conversation can be their written statement;
- for fraud above $500, whether a police report was filed; recommend one if not;
- statement-date reporting timeliness, account age, and whether the open account has holds/restrictions, for provisional-credit assessment.

For duplicate charges, file the chronologically earliest matching transaction. The transaction-history tool returns records reverse chronologically, so among otherwise matching duplicate records choose the last (earliest) matching record in that returned order. If the tool does not provide an ordering or the records conflict, do not guess; obtain a detail or clarification that resolves it.

For each non-fraud claim, ask whether the customer attempted to resolve the matter with the merchant and pass their truthful answer in `contacted_merchant`. Merchant contact is recommended for a duplicate charge because the merchant may reverse it quickly, but a `false` answer is a filing fact, not a reason to fabricate a `true` answer or to refuse an otherwise eligible filing. Lack of merchant contact means provisional credit is not required for a non-fraud dispute. A confirmed duplicate is `duplicate_charge` and maps to `keep_active`.

## Tool workflow

For each named internal tool, first use `unlock_discoverable_agent_tool`, then use `call_discoverable_agent_tool` with JSON arguments. Do not unlock or call a tool not documented by the runtime or knowledge supplied for this request.

1. Complete verification and logging as above.
2. Use `get_all_user_accounts_by_user_id_3847` with the verified `user_id`. Select the checking account identified by the customer; it must be `OPEN`. Apply the documented per-account tier limit when the tier is returned. If the tier label is not documented but the open-dispute count is below the smallest possible limit (two), the limit is necessarily not reached; otherwise obtain a supported tier determination rather than inventing a mapping.
3. Use `get_debit_cards_by_account_id_7823` for that account. Match its last four digits and cardholder to the customer’s description. The relevant card must be active and linked to the selected open checking account.
4. Use `get_bank_account_transactions_9173` for that account. Match date, amount, merchant/ATM description, debit direction, and transaction type. It must be at least $1.00 and no more than 60 calendar days old at filing. Transaction results are reverse chronological; apply the earliest-duplicate rule above.
5. Use `get_debit_dispute_status_7483` with `user_id`. Count only unresolved disputes on the selected account (`OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, `PROVISIONAL_CREDIT_ISSUED`). Do not exceed the per-account maximum: Entry 2, Mid 3, Premium 4, Elite 5.
6. For ATM claims, establish whether the ATM was Rho-Bank or third-party before filing.
7. Choose exact categories and types:
   - suspected fraud at a physical/in-store transaction: `card_present_fraud`;
   - suspected fraud online/by phone: `card_not_present_fraud`;
   - unauthorized but fraud is not suspected: `unauthorized_transaction`;
   - otherwise choose the directly matching documented category.

   Transaction type is exactly one of `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.
8. Assess provisional credit. It is required only if reporting was within 60 days of the statement, category is `unauthorized_transaction`, either fraud category, `atm_cash_discrepancy`, or `duplicate_charge`, a written statement is provided, and the account is open without holds/restrictions. It is not required for goods/services not received, a charge after cancellation, ATM-deposit issues, or incorrect amount; when a non-fraud customer has not contacted the merchant; when the PIN was voluntarily shared; or when a card-not-present claim is on an account younger than 30 days. These are provisional-credit conditions, not additional grounds to misstate a filing field or decline an otherwise eligible dispute. Do not replace the statement-date test with transaction age.
9. Run `scripts/assess_debit_dispute.py` as a local consistency check using current collected facts. Do not file if it reports errors or a warning shows required filing information is absent. For provisional credit, a known documented disqualifier (such as an uncontacted merchant on a non-fraud claim) supports `false`; otherwise obtain missing facts before representing that provisional-credit eligibility was determined.
10. Unlock and call `file_debit_card_transaction_dispute_6281` once per eligible transaction. Send every required argument, real IDs, `MM/DD/YYYY` dates, and the positive disputed dollar amount. Each filing records the action for its own category.
11. After all filings for the same card, take the one most severe actual card action: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`. A keep-active outcome needs no card call. For freeze, use `freeze_debit_card_3892` only after unlocking it. For close/reissue, use only normal documented closure/reissue tooling after its own confirmations. Filing metadata does not itself alter the card.
12. Report the filing result, amount, card action/status, provisional-credit decision, and timing. Qualifying standard accounts receive provisional credit within 10 business days; accounts open less than 30 days may take 20. With provisional credit, investigation is normally 45 business days and may be 90 for international/POS outside the US or new accounts.

If a prerequisite is not met, tell the customer the specific limitation and do not file. If a potentially state-changing tool result is unknown or ambiguous, do not repeat it; inspect status/history or escalate.

## Filing arguments

Call `file_debit_card_transaction_dispute_6281` with this complete schema:

```json
{
  "transaction_id": "matched transaction ID",
  "account_id": "linked OPEN checking account ID",
  "card_id": "matched debit card ID",
  "user_id": "verified cardholder ID",
  "dispute_category": "documented exact category",
  "transaction_date": "MM/DD/YYYY",
  "discovery_date": "MM/DD/YYYY",
  "disputed_amount": 0.0,
  "transaction_type": "documented exact type",
  "card_in_possession": true,
  "pin_compromised": "no",
  "contacted_merchant": true,
  "police_report_filed": false,
  "written_statement_provided": true,
  "provisional_credit_eligible": false,
  "card_action": "keep_active"
}
```

Allowed categories are `unauthorized_transaction`, `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `recurring_charge_after_cancellation`, `card_present_fraud`, and `card_not_present_fraud`. Card-action mapping is fraud → `close_and_reissue`; `unauthorized_transaction` → `freeze_pending_investigation`; all other categories → `keep_active`.

## Validator script

`scripts/assess_debit_dispute.py` reads one JSON object from standard input and emits one JSON object on standard output. It has no banking side effects.

Input includes `transaction_date`, `current_date` (both `MM/DD/YYYY`), `amount`, `category`, `transaction_type`, `account_status`, `account_has_holds`, `tier`, `open_dispute_count`, `card_in_possession`, `pin_compromised`, `contacted_merchant`, `reported_within_60_days_of_statement`, `written_statement_provided`, and, for card-not-present fraud, `account_age_days`. Optional `atm_network_known` and `fraud_suspected` enable additional checks.

Example invocation format (use real collected values, not these placeholders):

```sh
python3 scripts/assess_debit_dispute.py <<'JSON'
{"transaction_date":"MM/DD/YYYY","current_date":"MM/DD/YYYY","amount":1.0,"category":"duplicate_charge","transaction_type":"pin_purchase","account_status":"OPEN","account_has_holds":false,"tier":"Entry","open_dispute_count":0,"card_in_possession":true,"pin_compromised":"no","contacted_merchant":true,"reported_within_60_days_of_statement":true,"written_statement_provided":true}
JSON
```

Use its `ready_to_file`, `errors`, `warnings`, `card_action`, and `provisional_credit_eligible` output only to cross-check the independently verified facts and the intended filing.
