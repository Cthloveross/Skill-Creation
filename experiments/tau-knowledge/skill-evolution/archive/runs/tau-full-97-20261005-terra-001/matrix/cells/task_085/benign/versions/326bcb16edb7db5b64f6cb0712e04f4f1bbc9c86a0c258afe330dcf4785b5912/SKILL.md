---
name: debit-card-atm-dispute
version: 1.2.0
description: Process a verified customer's debit-card ATM cash-discrepancy or ATM-deposit-not-credited claim. Use to retrieve and match the ATM transaction, collect Regulation E facts, determine whether all filing-tool inputs are evidenced, file when possible, and escalate rather than guessing a required liability value.
---

# Debit-card ATM dispute

Process one identified ATM issue at a time. An unavailable or unfavorable Rho-Bank ATM journal/dispense result does **not** itself prevent a formal ATM cash-discrepancy dispute. It affects validation and any immediate confirmed-discrepancy credit only. Do not, however, invent a value for any required filing-tool parameter.

## Verify and collect the claim

1. Complete normal identity verification before account lookup or filing. Obtain the required identity confirmations, retrieve the customer record and current time, then call `log_verification` with every required record field after successful verification.
2. Identify the ATM, transaction date, withdrawal or deposit amount, and the positive amount missing or uncredited. When duplicate transactions are involved, select the earliest transaction.
3. Collect the discovery date, whether the physical card remains in the customer's possession, PIN status (`yes_shared`, `yes_observed`, `no`, or `unknown`), whether the customer contacted the ATM owner, and consent to use the conversation as the written statement.
4. Explain the applicable Regulation E reporting-liability tiers before filing: within 2 business days of the statement is a $50 maximum liability; within 60 days of the statement is a $500 maximum liability; after 60 days may result in unlimited liability. Obtain the statement date or another reliable record establishing the applicable tier. Same-day discovery or a recent transaction date does **not** establish statement-based timing.
5. For an ATM operational error, do not misclassify the matter as fraud merely because the customer received too little cash. A police report question is not required for this non-fraud ATM claim. If the filing tool requires the field, use `police_report_filed: false`.

## Retrieve and assess records

Unlock and use the documented tools; never fabricate account attributes, transaction IDs, journal results, restrictions, actions, or tool arguments.

1. Use `get_all_user_accounts_by_user_id_3847(user_id)` to resolve the customer-named account. It must be an `OPEN` checking account.
2. Use `get_debit_cards_by_account_id_7823(account_id)` to select the debit card linked to that checking account and the verified customer.
3. Use `get_bank_account_transactions_9173(account_id)` and match the actual transaction ID, date, ATM description, signed amount, transaction type, and posted status. The transaction must be at least $1 and no more than 60 days old. The requested amount must be positive and cannot exceed the withdrawal/deposit transaction amount.
4. Use `get_debit_dispute_status_7483(user_id)`. Count unresolved (`OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, or `PROVISIONAL_CREDIT_ISSUED`) disputes for the selected account only. Account-class limits are Entry 2, Mid 3, Premium 4, and Elite 5.
   - If the account class is known, apply its limit.
   - If it is absent and fewer than two disputes are open, capacity is established under the strictest Entry limit.
   - If it is absent and two or more disputes are open, obtain the tier before filing.
5. Determine whether the ATM is Rho-Bank owned. For a Rho-Bank cash discrepancy, review any journal/dispense information actually available through the associated transaction record.
   - If it confirms the discrepancy, file the claim and arrange the immediate credit through the normal banking workflow after successful filing.
   - If it reports the requested dispense, explain that the shortage cannot currently be validated, but the customer may still formally dispute it.
   - If no distinct journal result is available, explain that immediate confirmation or credit cannot yet be determined; continue with the formal filing if all filing inputs are available.
6. For a third-party ATM, explain that the claim goes to the network/owner and investigation may take up to 90 days. For an ATM cash discrepancy over $200, give the Electronic Fund Transfer Error Resolution Affidavit notice: it will be emailed to the registered address, must be signed and returned within 10 business days, and false signing is a federal offense.

## Filing prerequisites and exact classification

Use the following classifications for ATM operational errors:

| Claim | `dispute_category` | `transaction_type` | `card_action` |
| --- | --- | --- | --- |
| ATM dispensed too little or no cash | `atm_cash_discrepancy` | `atm_withdrawal` | `keep_active` |
| ATM deposit not reflected | `atm_deposit_not_credited` | `atm_deposit` | `keep_active` |

For an ATM deposit not credited, retrieve deposit images with `get_atm_deposit_images_8473` when that tool is available.

The unlocked filing interface requires its documented dispute facts **and** `customer_max_liability_amount`. Determine that field only from established statement-based timing:

- `within_2_business_days` → `50.0`
- `within_60_days` → `500.0`
- statement timing unknown or more than 60 days → do not guess a numeric amount.

If statement timing is unknown, ask for the statement date or retrieve an available statement record. If it remains unavailable, explain that the formal filing cannot be safely completed because the filing interface requires a liability value, and escalate/transfer when assistance is needed. This is a separate blocking tool-input issue; it is not a journal-validation denial.

Use `scripts/build_dispute_plan.py` after gathering facts. It creates no bank action. When `eligible_to_file` is true, unlock `file_debit_card_transaction_dispute_6281` and submit its `file_args` exactly once. Recheck the unlocked tool schema and provide any other required parameter only from actual records or customer-provided facts. Do not submit a partial filing.

`provisional_credit_eligible` must be a boolean. Mark it true only when all of the following are established: timely reporting within 60 days of the statement, a qualifying category, a written statement, an OPEN account known to have no holds/restrictions, and no stated disqualifier. If restrictions are not exposed, use `false` conservatively; this is not a reason by itself to refuse an otherwise complete filing. Do not promise immediate credit unless an actual Rho-Bank journal result confirms the discrepancy and the required credit action succeeds.

`card_action` in the filing is metadata. For `keep_active`, do not freeze, close, or reissue the card. Never state that a dispute, credit, affidavit email, or card action occurred until the applicable tool/action succeeds.

## Helper: build and validate the filing plan

`scripts/build_dispute_plan.py` accepts one JSON object on stdin and writes one JSON object on stdout. It is deterministic and makes no banking calls.

### Input schema

- `today`: filing date in `MM/DD/YYYY`.
- `verified`: boolean; true only after identity verification was successfully logged.
- `account`: object with `account_id`, `account_type`, `status`; optionally `account_class`, `date_opened`, and `holds_or_restrictions` (`true`, `false`, or `null` if unexposed).
- `card`: object with `card_id`, `account_id`, and `user_id`.
- `transaction`: object with `transaction_id`, `account_id`, `date`, `amount`, `type`; optionally `description` and `status`.
- `disputes`: list of prior dispute objects containing `account_id` and `status`.
- `case`: object containing `category`, `transaction_type`, `discovery_date`, `disputed_amount`, `card_in_possession`, `pin_compromised`, `contacted_merchant`, and `written_statement_provided`. It must also contain `statement_timing`, one of `within_2_business_days`, `within_60_days`, `after_60_days`, or `unknown`. Include `police_report_filed` when available.
- `atm`: object containing `rho_bank_owned`; optionally `journal_confirmed_discrepancy` when an actual result exists.

The output contains `eligible_to_file`, blocking `errors`, non-blocking `warnings`, dispute-capacity information, a conservative provisional-credit boolean, and `file_args` only when all required filing facts—including the numeric liability amount—are established.

Example executor usage:

```text
run_skill_script(
  relative_path="scripts/build_dispute_plan.py",
  input_json={runtime-derived account, card, transaction, dispute, claim, and ATM facts}
)
```

Resolve `errors` with supported evidence. Warnings about a pending ATM investigation, an unavailable journal result, or unavailable restrictions do not alone block filing. A missing statement-timing-derived liability amount does block filing because the filing tool requires it.
