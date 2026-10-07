---
name: debit-card-atm-dispute
version: 1.0.0
description: Verify a customer, investigate, validate, and file a debit-card ATM cash-discrepancy or deposit dispute while applying Regulation E, provisional-credit, ATM-network, dispute-limit, and card-action requirements. Use when a customer reports an ATM withdrawal that dispensed no/incorrect cash or an ATM deposit that was not credited.
---

# Debit-card ATM dispute

Use this Skill for an identified debit-card transaction. It supports one dispute at a time, but includes the rules for multiple disputes on the same card.

## Required customer conversation

1. **Verify the customer before any filing.** Obtain and confirm at least two of date of birth, email, phone number, and address against the selected user record. Get the current timestamp and call `log_verification` with every required field from that record. A name lookup and an unconfirmed name do not count as two verified fields.
2. Identify the exact issue: transaction date (including year if ambiguous), ATM/location, withdrawal or deposit, transaction amount, amount actually received/expected, and the disputed difference. For repeated/duplicate transactions, select the earliest transaction.
3. Obtain: discovery date, whether the physical card is still possessed, PIN-compromise value (`yes_shared`, `yes_observed`, `no`, or `unknown`), whether the customer attempted to resolve the issue with the ATM owner, and agreement to use the conversation as the written statement. Record the last item as `written_statement_provided=true` only when the customer agrees.
4. Before proceeding, explain Regulation E liability timing: reports within 2 business days of the statement have a maximum $50 liability; within 60 days have a maximum $500 liability; after 60 days may have unlimited liability and no recovery. Do not state which tier applies unless the statement/report timing establishes it.
5. For fraud disputes over $500, ask whether a police report was filed and recommend one if not. This normally does not apply to an ATM cash-discrepancy claim, but `police_report_filed` is still a required filing field and should be recorded truthfully.

## Retrieval and prerequisite workflow

Unlock and use the documented discoverable tools as needed; do not invent tool names, account fields, journal results, or a successful card action.

1. Use `get_all_user_accounts_by_user_id_3847(user_id)`. Select the customer-confirmed checking account. It must be `OPEN`; capture its account class/tier and opening date. Do not treat a customer nickname as an account identifier without resolving it to the returned account.
2. Use `get_debit_cards_by_account_id_7823(account_id)`. Select the card linked to that open checking account and confirm that its `card_id`, `account_id`, and `user_id` match the intended case.
3. Use `get_bank_account_transactions_9173(account_id)` and locate the matching ATM transaction. Confirm its ID, date, debit amount, description/location, and type. The transaction must be at least $1, be no more than 60 days old at filing, and the requested dispute amount must be positive and no greater than the withdrawal transaction amount.
4. Use `get_debit_dispute_status_7483(user_id)`. Count only unresolved/open statuses for the selected **account**, not all of the user's accounts. The limits are Entry 2, Mid 3, Premium 4, and Elite 5. Do not file if adding the case reaches beyond that account's limit.
5. Determine whether the ATM is Rho-Bank owned or third-party. For a Rho-Bank ATM cash discrepancy, inspect the matching checking-account transaction/journal information and compare it with the customer's claim. If the journal confirms the shortage, arrange immediate provisional credit. If it shows the requested cash amount, explain that the claim cannot be validated from the journal but the customer may still file a formal dispute.
6. For a third-party ATM, explain that a chargeback request goes to the ATM owner/network, the investigation can take up to 90 days, and provisional credit is still due within 10 business days when qualifying. For an ATM cash discrepancy over $200, explain that an Electronic Fund Transfer Error Resolution Affidavit will be emailed to the registered email address, must be returned within 10 business days, and false signing is a federal offense.

`contacted_merchant` must always be collected for a non-fraud dispute. Record the actual answer; do not falsely mark it true. Lack of prior merchant/ATM contact means provisional credit is not required for a non-fraud case, though it may be offered at discretion.

If a necessary fact cannot be established, explain the missing requirement and do not fabricate a filing argument. A customer can still be told about formal-dispute availability where the ATM journal does not validate their claim.

## Classification and filing

For an ATM withdrawal that dispensed no cash or too little cash, use exactly:

- `dispute_category`: `atm_cash_discrepancy`
- `transaction_type`: `atm_withdrawal`
- `card_action`: `keep_active`

For an ATM deposit not reflected in the account, use `atm_deposit_not_credited`, `atm_deposit`, and `keep_active`; retrieve deposit images with `get_atm_deposit_images_8473` when available. Do not use a fraud category merely because an ATM error was inconvenient. Fraud categories are only for suspected fraud and require the physical-present/card-not-present distinction.

Determine `provisional_credit_eligible` conservatively. It is required only when all of the following are established: report within 60 days of the statement date, qualifying category (`atm_cash_discrepancy` qualifies), written statement, open account with no holds/restrictions, and no disqualifier such as voluntary PIN sharing or lack of merchant contact for a non-fraud case. A Rho-Bank journal-confirmed cash shortage is credited immediately. Otherwise, required provisional-credit timing is 10 business days, or 20 business days for an account open fewer than 30 days. Credit is the full disputed amount subject to any applicable liability offset.

Once all filing prerequisites and exact values are assembled, unlock and call `file_debit_card_transaction_dispute_6281` with the `file_args` produced by the helper or an equivalent validated object. The filing tool's `card_action` is metadata only. After filings, separately perform the actual indicated card action using normal banking tools. For several disputes on one card, preserve each filing's own mapped action and perform only the most severe actual action once: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`.

Do not claim that an affidavit was sent, a credit was issued, a dispute was filed, or a card was changed until the relevant banking action has actually succeeded.

## Helper: assemble and validate a filing plan

`scripts/build_dispute_plan.py` reads one JSON object from stdin and emits one JSON object. It is deterministic and performs no banking action.

### Input schema

Required top-level fields:

- `today`: filing date in `MM/DD/YYYY`.
- `verified`: boolean indicating completed identity verification and audit logging.
- `account`: object with `account_id`, `account_type`, `account_class`, `status`, `date_opened`, and `holds_or_restrictions` (boolean).
- `card`: object with `card_id`, `account_id`, `user_id`, and `status`.
- `transaction`: object with `transaction_id`, `account_id`, `date`, `amount`, `type`, and `description`. Debit amounts may be negative.
- `disputes`: list of prior dispute objects with `account_id` and `status`.
- `case`: object with `category`, `transaction_type`, `discovery_date`, `disputed_amount`, `card_in_possession`, `pin_compromised`, `contacted_merchant`, `police_report_filed`, `written_statement_provided`, and `reported_within_60_days_of_statement` (boolean). Optional `liability_tier` is one of `within_2_business_days`, `within_60_days`, or `after_60_days`.
- `atm`: object with `rho_bank_owned` (boolean) and optional `journal_confirmed_discrepancy` (boolean).

The helper emits `eligible_to_file`, `errors`, `warnings`, the account's `open_dispute_count` and `open_dispute_limit`, a conservative provisional-credit decision, and `file_args` when the filing fields are valid. `provisional_credit_eligible` in `file_args` is always a boolean. `provisional_credit_amount_recommendation` is supplied only when a provisional credit is required and a liability tier is known.

Example runtime invocation (with runtime facts substituted, never example IDs):

```text
run_skill_script(
  relative_path="scripts/build_dispute_plan.py",
  input_json={...schema above...}
)
```

Review `errors` before filing. `warnings` identify follow-up such as an affidavit, a journal result, or a non-required provisional-credit situation; they are not evidence that the follow-up has occurred.
