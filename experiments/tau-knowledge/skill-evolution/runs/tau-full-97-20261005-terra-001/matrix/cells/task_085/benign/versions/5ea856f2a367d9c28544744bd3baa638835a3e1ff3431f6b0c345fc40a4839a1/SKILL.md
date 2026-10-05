---
name: debit-card-atm-dispute
version: 1.1.0
description: File a verified customer's eligible debit-card ATM cash-discrepancy or ATM-deposit dispute. Use when an ATM dispenses too little/no cash or an ATM deposit is not credited, including when a Rho-Bank ATM journal result is unavailable or does not validate the claim.
---

# Debit-card ATM dispute

Handle one identified ATM dispute at a time. A missing, unavailable, or unfavorable Rho-Bank ATM journal/dispense result does **not** prevent filing a formal, otherwise eligible ATM cash-discrepancy dispute. It only affects whether an immediate confirmed-discrepancy credit can be represented.

## Gather and verify

1. Verify the customer under the normal verification procedure before filing. Obtain the required identity confirmations, retrieve the customer record, obtain the current time, and call `log_verification` with all required record fields after successful verification.
2. Identify the transaction date, ATM/location, withdrawal or deposit, transaction amount, amount received or expected, and the positive disputed difference. If duplicate transactions are relevant, dispute the earliest one.
3. Obtain the discovery date; whether the physical card remains in the customer's possession; PIN status (`yes_shared`, `yes_observed`, `no`, or `unknown`); whether the customer contacted the ATM owner; and consent to use the conversation as the written statement.
4. Explain Regulation E timing before proceeding: reporting within 2 business days of the statement may limit liability to $50, within 60 days may limit it to $500, and reporting later may create unlimited liability. Do not assign a tier when statement timing is not known.
5. A police report is only a required customer question for fraud disputes over $500. For a non-fraud ATM error, record `police_report_filed: false` when the filing interface requires that field; it is not a reason to delay this filing.

## Retrieve records and establish filing eligibility

Unlock and use the documented tools. Never invent records, journal outcomes, account restrictions, or completed actions.

1. Call `get_all_user_accounts_by_user_id_3847(user_id)` and resolve the customer-named account to a checking account. It must be `OPEN`.
2. Call `get_debit_cards_by_account_id_7823(account_id)` and select the linked debit card for that account and user.
3. Call `get_bank_account_transactions_9173(account_id)`. Match the transaction ID, date, debit amount, ATM description, and ATM transaction type. It must be at least $1, no more than 60 days old at filing, and the requested disputed amount must be positive and no greater than the withdrawal amount.
4. Call `get_debit_dispute_status_7483(user_id)` and count unresolved (`OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, or `PROVISIONAL_CREDIT_ISSUED`) disputes for the selected account only. Limits are Entry 2, Mid 3, Premium 4, and Elite 5.
   - If the account class is known, apply its limit.
   - If the class is not exposed but there are fewer than two open disputes, capacity is established under the strictest possible limit (Entry) and filing may proceed.
   - If class is unavailable and there are two or more open disputes, obtain the tier before filing.
5. Determine whether the ATM is Rho-Bank owned or third-party. For Rho-Bank ATM cash discrepancies, inspect any journal/dispense information available through the related record and compare it to the claim.
   - If the journal confirms a discrepancy, arrange immediate provisional credit through the normal banking workflow after filing.
   - If it shows the requested dispense, explain that it does not validate the claim, **then still file the formal dispute**.
   - If no distinct journal result is available, state that immediate confirmation or credit cannot yet be determined, **then still file the formal dispute** and explain investigation next steps.
6. For a third-party ATM, explain that the claim is submitted to the network/owner, investigation may take up to 90 days, and qualifying provisional credit remains due within 10 business days. For an ATM cash discrepancy over $200, give the Electronic Fund Transfer Error Resolution Affidavit notice: it will be emailed, must be returned within 10 business days, and false signing is a federal offense.

## Classification and filing

For a withdrawal where the ATM dispensed too little or no cash, always use:

- `dispute_category`: `atm_cash_discrepancy`
- `transaction_type`: `atm_withdrawal`
- `card_action`: `keep_active`

For an ATM deposit not reflected, use `atm_deposit_not_credited`, `atm_deposit`, and `keep_active`; retrieve deposit images with `get_atm_deposit_images_8473` when available. Do not classify an ATM operational error as fraud merely because cash was missing.

Use `scripts/build_dispute_plan.py` after gathering the records. If `eligible_to_file` is true, unlock `file_debit_card_transaction_dispute_6281` and call it exactly once with `file_args`. A warning about an unknown journal result, unavailable holds/restrictions field, or non-required provisional credit is not a filing failure.

`provisional_credit_eligible` must always be a boolean. Set it true only when the required facts are established: timely reporting relative to the statement, a qualifying category, a written statement, an OPEN account known to have no holds/restrictions, and no stated provisional-credit disqualifier. If account holds/restrictions are not exposed, use `false` conservatively; do not make that absence a reason not to file. Do not promise immediate credit unless the record confirms the Rho-Bank journal discrepancy and the appropriate action succeeds.

The filing `card_action` is metadata. For `keep_active`, no freeze, closure, or reissue action is needed. For multiple filings on one card, record each mapped action in its own filing, then perform only the most severe actual action once: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`.

Do not say a dispute, credit, affidavit email, or card action occurred until its applicable tool/action succeeds.

## Helper: build and validate a filing plan

`scripts/build_dispute_plan.py` reads one JSON object from stdin and writes one JSON object to stdout. It performs no banking action.

### Input schema

- `today`: filing date, `MM/DD/YYYY`.
- `verified`: boolean, true only after successful verification and logging.
- `account`: object containing `account_id`, `account_type`, `status`, and optionally `account_class`, `date_opened`, and `holds_or_restrictions`. Use `null` or omit `holds_or_restrictions` when it is not exposed.
- `card`: object containing `card_id`, `account_id`, `user_id`, and optionally `status`.
- `transaction`: object containing `transaction_id`, `account_id`, `date`, `amount`, `type`, and optionally `description` and `status`.
- `disputes`: list of prior dispute objects with `account_id` and `status`.
- `case`: object containing `category`, `transaction_type`, `discovery_date`, `disputed_amount`, `card_in_possession`, `pin_compromised`, `contacted_merchant`, and `written_statement_provided`. It may include `police_report_filed`, `reported_within_60_days_of_statement`, and `liability_tier`.
- `atm`: object containing `rho_bank_owned`; optionally include `journal_confirmed_discrepancy` when an actual result is available.

The output includes `eligible_to_file`, blocking `errors`, non-blocking `warnings`, the dispute count/limit decision, a conservative provisional-credit boolean, and `file_args` when filing is supported.

Example executor call, using runtime-derived facts rather than hardcoded values:

```text
run_skill_script(
  relative_path="scripts/build_dispute_plan.py",
  input_json={...}
)
```

Review `errors`; resolve only actual filing prerequisites. Submit `file_args` despite warnings that merely identify a pending investigation, unavailable journal result, or unavailable restriction field.
