---
name: debit-card-dispute-workflow
description: File one or more eligible debit-card transaction disputes while applying Regulation E intake, provisional-credit, ATM, card-action, and verification requirements. Use for a verified customer reporting debit-card purchases, ATM errors, duplicate charges, merchant problems, recurring charges, or suspected debit-card fraud.
---

# Debit Card Dispute Workflow

Use this workflow to gather facts, verify eligibility, file eligible debit-card disputes, and perform the resulting card security action. It is designed for multiple disputes across one or more checking accounts/cards.

## Inputs and required facts

Obtain or retrieve, at runtime:

- Customer identity and successful verification (two of date of birth, email, phone, and address); log verification before any banking action.
- `user_id`, all customer accounts, the relevant checking account(s), account tier/class, account opening date, account status, and whether the account has any holds/restrictions.
- Debit cards on each relevant account, including card ID, owner, last four digits, and status.
- Transactions for each candidate account, including transaction ID, date, description, amount, type, and status.
- Existing dispute statuses for the customer, so open-dispute counts can be calculated **per account**.
- For every proposed dispute: transaction date, discovery date, disputed amount, event details, transaction type, fraud determination, physical-card possession, PIN-compromise answer, merchant-contact result where non-fraud, police-report result for fraud above $500, and agreement to a written statement.
- For ATM matters, whether the ATM is Rho-Bank owned or third party. For cash discrepancies above $200, inform the customer of the affidavit requirement.

The customer must be told the applicable Regulation E exposure before filing an unauthorized/fraud report: reported within two business days has a maximum $50 liability, within 60 days a maximum $500 liability, and after 60 days potentially unlimited liability/no recovery. Do not represent this as a guaranteed outcome.

## Required banking procedure

1. **Verify before action.** Match the requester to the customer and confirm at least two identity fields, then call `log_verification` with all returned identity fields and the current timestamp. Confirm the customer owns the relevant card and account.
2. Retrieve accounts with `get_all_user_accounts_by_user_id_3847`, cards with `get_debit_cards_by_account_id_7823`, transactions with `get_bank_account_transactions_9173`, and dispute history with `get_debit_dispute_status_7483`.
3. Match each reported item to an actual debit transaction and use its exact `transaction_id`, date, and absolute debit amount. Do not file from a merchant name alone. If duplicate transactions are reported, dispute the earliest/first duplicate transaction.
4. For each candidate, check all filing prerequisites:
   - verified customer and card ownership;
   - transaction is at least $1 and no more than 60 days old at filing;
   - card is linked to an `OPEN` checking account;
   - count existing open disputes only for that account; maximums are Entry 2, Mid 3, Premium 4, Elite 5;
   - category, type, dates, and amount are known and valid.
   Do not file a candidate that fails a prerequisite. Explain the blocking fact and any remaining option.
5. Determine category precisely. For an unauthorized item, ask whether fraud is suspected. If fraud is suspected, use `card_present_fraud` only when the physical card was used, or `card_not_present_fraud` only for online/phone/card-not-present use. Use `unauthorized_transaction` only when fraud is not suspected. If transaction channel is unknown, do not guess; obtain it before choosing a fraud category.
6. Determine provisional-credit eligibility. It is required only when timely reporting, an eligible category (`unauthorized_transaction`, either fraud category, `atm_cash_discrepancy`, or `duplicate_charge`), written statement, and OPEN unrestricted account standing are all present. It is not required for the other listed merchant/ATM-deposit/incorrect-amount categories, when a non-fraud customer has not first contacted the merchant, when PIN was voluntarily shared, or for a card-not-present transaction on an account less than 30 days old. Eligible amount is the full disputed amount subject to any late-reporting liability offset. Standard accounts have a 10-business-day deadline and new accounts 20 business days.
7. Use `file_debit_card_transaction_dispute_6281` for each eligible filing with every required argument. Record each dispute's own mapped `card_action`:
   - fraud categories: `close_and_reissue`
   - `unauthorized_transaction`: `freeze_pending_investigation`
   - all other categories: `keep_active`.
8. After all filings for a card, perform only the most severe resulting action once: `close_and_reissue` outranks `freeze_pending_investigation`, which outranks `keep_active`.
   - A freeze requires verified ownership and an ACTIVE card; use `freeze_debit_card_3892`.
   - A fraud closure requires verified ownership and ACTIVE/PENDING status; use `close_debit_card_4721` with `reason: fraud_suspected`. Fraud bypasses minimum card age, but still account for pending transactions/refunds under the closure procedure.
   - If closure is unavailable because a prerequisite is unmet, do not silently substitute a different action; explain and escalate/seek the appropriate resolution.
9. For a third-party ATM cash discrepancy, process the network/owner chargeback route and advise that investigation may take 90 days. For a Rho-Bank ATM cash discrepancy, inspect journal/transaction records and issue confirmed credit immediately where supported. For a Rho-Bank ATM deposit issue, retrieve deposit images using `get_atm_deposit_images_8473` and compare them with the claim.
10. Confirm filed disputes, any documentary follow-up, card action, provisional-credit status/deadline, and expected investigation timeline. Advise a customer alleging fraud over $500 who has no police report to consider filing one; do not make police reporting a filing prerequisite unless the available procedure specifically requires it.

## Tool argument mapping

For each filing, send these exact concepts to `file_debit_card_transaction_dispute_6281`:

- `transaction_id`, `account_id`, `card_id`, `user_id`: retrieved records, with card owner/account linkage confirmed.
- `transaction_date`, `discovery_date`: `MM/DD/YYYY`.
- `disputed_amount`: positive float, not larger than the transaction amount.
- `dispute_category`: one supported category.
- `transaction_type`: one supported transaction type.
- `card_in_possession`: customer answer.
- `pin_compromised`: exactly `yes_shared`, `yes_observed`, `no`, or `unknown`.
- `contacted_merchant`: boolean, especially required for non-fraud disputes.
- `police_report_filed`: boolean.
- `written_statement_provided`: true only if a written statement/conversation agreement was obtained.
- `provisional_credit_eligible`: the determination above.
- `card_action`: the category mapping above, not the combined action.

## Deterministic planning helper

`scripts/plan_disputes.py` accepts JSON on stdin and emits a JSON plan/validation report on stdout. It does not contact banking systems or file disputes. Supply retrieved facts rather than inferred values. It validates enum values, dates, tier limits, transaction age, card/account linkage, duplicate selection, mapped actions, and a conservative provisional-credit determination.

Example input:

```json
{
  "as_of_date": "MM/DD/YYYY",
  "accounts": [{"account_id":"...","account_type":"checking","account_class":"Entry","status":"OPEN","has_holds_or_restrictions":false,"date_opened":"MM/DD/YYYY"}],
  "cards": [{"card_id":"...","account_id":"...","user_id":"...","status":"ACTIVE"}],
  "open_dispute_counts": {"account-id": 0},
  "candidates": [{"transaction_id":"...","account_id":"...","card_id":"...","user_id":"...","transaction_date":"MM/DD/YYYY","transaction_amount":100.0,"discovery_date":"MM/DD/YYYY","disputed_amount":100.0,"dispute_category":"duplicate_charge","transaction_type":"signature_purchase","card_in_possession":true,"pin_compromised":"no","contacted_merchant":true,"police_report_filed":false,"written_statement_provided":true,"timely_reporting":true}]
}
```

Review `filable`, `blocking_reasons`, and `required_followups` before taking actions. A plan being filable is not a substitute for identity verification, transaction lookup, required ATM record review, or customer disclosures.
