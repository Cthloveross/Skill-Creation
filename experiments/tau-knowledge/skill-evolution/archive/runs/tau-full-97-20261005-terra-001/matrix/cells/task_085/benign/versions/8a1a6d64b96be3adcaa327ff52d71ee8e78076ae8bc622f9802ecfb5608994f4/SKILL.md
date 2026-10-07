---
name: debit-card-atm-dispute
version: 1.3.0
description: Process a verified customer's debit-card ATM cash-discrepancy or ATM-deposit-not-credited claim. Use to match the ATM transaction, collect Regulation E facts, validate filing prerequisites, submit a complete debit-card dispute, and communicate ATM investigation and credit next steps.
---

# Debit-card ATM dispute

Process one identified ATM issue at a time. A missing, unavailable, or unfavorable Rho-Bank ATM journal/dispense result does **not** prevent a customer from filing a formal ATM cash-discrepancy dispute. It affects whether the discrepancy is immediately validated and whether an immediate confirmed-discrepancy credit can be arranged.

Do not fabricate records, IDs, account attributes, journal findings, restrictions, tool results, or customer facts.

## Verify and collect the claim

1. Complete normal identity verification before account lookup or filing. Confirm at least two identity fields against the customer record, then call `log_verification` with every required customer-record field and the current timestamp.
2. Identify the ATM, transaction date, withdrawal or deposit amount, and the positive amount missing or uncredited. If duplicate transactions are involved, dispute the earliest transaction.
3. Collect the discovery date, whether the physical card remains in the customer's possession, PIN status (`yes_shared`, `yes_observed`, `no`, or `unknown`), whether the customer contacted the ATM owner, and consent to use the conversation as the written statement.
4. Before filing, explain the Regulation E reporting-liability tiers: within 2 business days of the statement has a $50 maximum liability; within 60 days has a $500 maximum liability; after 60 days may result in unlimited liability. Ask for statement timing when needed to explain the customer's precise exposure, but do **not** treat unavailable statement timing as a blocker to the documented filing tool. The published filing arguments do not include a liability amount or statement date.
5. An ATM operational error is not fraud merely because the customer received too little cash. For this non-fraud claim, a police report is not required. If the filing interface requires `police_report_filed`, supply `false` unless the customer actually reported otherwise.

## Retrieve and assess records

Unlock and use the documented tools as needed.

1. Use `get_all_user_accounts_by_user_id_3847(user_id)` to identify the customer-named account. It must be an `OPEN` checking account.
2. Use `get_debit_cards_by_account_id_7823(account_id)` to select a debit card linked to that checking account and the verified customer. Prefer the current active card when records show card history.
3. Use `get_bank_account_transactions_9173(account_id)` and match the actual transaction ID, date, ATM description, signed amount, transaction type, and posted status. The transaction must be at least $1 and no more than 60 days old. The requested amount must be positive and cannot exceed the transaction amount.
4. Use `get_debit_dispute_status_7483(user_id)`. Count unresolved (`OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, or `PROVISIONAL_CREDIT_ISSUED`) disputes for the selected account only. Per-account limits are Entry 2, Mid 3, Premium 4, and Elite 5.
   - Apply the account class when exposed.
   - If account class is absent and fewer than two disputes are open, capacity is established under the strictest Entry limit.
   - If account class is absent and two or more disputes are open, obtain the tier before filing.
5. Determine whether the ATM is Rho-Bank owned.
   - For a Rho-Bank cash discrepancy, review actual journal/dispense information exposed through the transaction workflow.
   - If it confirms the discrepancy, submit the formal claim and arrange the immediate credit through normal banking workflow only after successful filing.
   - If it says the requested amount was dispensed, explain that the shortage cannot currently be validated, but still submit the formal dispute if filing prerequisites are met.
   - If no distinct journal result is available, explain that immediate confirmation or immediate credit cannot yet be determined, and still submit the formal dispute if filing prerequisites are met.
6. For a third-party ATM, explain that the claim is submitted to the ATM owner/network and investigation may take up to 90 days. For an ATM cash discrepancy over $200, give the Electronic Fund Transfer Error Resolution Affidavit notice: it will be emailed to the registered email address, must be signed and returned within 10 business days, and false signing is a federal offense.

## Classify and file

Use these exact classifications for ATM operational errors:

| Claim | `dispute_category` | `transaction_type` | `card_action` |
| --- | --- | --- | --- |
| ATM dispensed too little or no cash | `atm_cash_discrepancy` | `atm_withdrawal` | `keep_active` |
| ATM deposit not reflected | `atm_deposit_not_credited` | `atm_deposit` | `keep_active` |

For an ATM deposit not credited, retrieve deposit images with `get_atm_deposit_images_8473` when that documented tool is available.

After all pre-filing facts are established, run `scripts/build_dispute_plan.py`. The helper creates no bank action. If `eligible_to_file` is true:

1. Unlock `file_debit_card_transaction_dispute_6281`.
2. Recheck the unlocked schema.
3. Submit the helper's `file_args` exactly once, adding an interface-required field only when it is supported by actual records or customer-provided facts.
4. Do not submit a partial filing. If a genuinely required tool parameter cannot be evidenced, explain the specific missing fact and obtain it or use an appropriate human handoff.

The documented filing fields are transaction ID, account ID, card ID, user ID, category, transaction and discovery dates, disputed amount, transaction type, card possession, PIN status, merchant/ATM-owner contact, police-report status, written-statement status, provisional-credit eligibility, and card action. Do not invent a `customer_max_liability_amount` parameter.

## Provisional credit and card handling

`provisional_credit_eligible` must be a boolean. Mark it true only when all required conditions are established: reporting within 60 days of the statement, qualifying category, written statement, OPEN account with no holds or restrictions, and no stated disqualifier. If statement timing or account restrictions are not exposed, use `false` conservatively. This uncertainty is not itself a reason to refuse an otherwise complete formal filing.

For non-fraud disputes, lack of prior merchant/ATM-owner contact means required provisional credit does not apply under the supplied guidance. Do not promise immediate credit unless an actual Rho-Bank journal result confirms the discrepancy and the required credit action succeeds.

`card_action` is filing metadata. ATM cash discrepancies and ATM deposits not credited use `keep_active`; do not freeze, close, or reissue the card for those claims. Never state that a dispute, credit, affidavit email, or card action occurred until its corresponding tool/action succeeds.

## Helper: build and validate the filing plan

`scripts/build_dispute_plan.py` reads one JSON object from stdin and writes one JSON object to stdout. It is deterministic and makes no banking calls.

### Input schema

- `today`: filing date in `MM/DD/YYYY`.
- `verified`: boolean; true only after successful identity verification was logged.
- `account`: object with `account_id`, `account_type`, `status`; optionally `account_class`, `date_opened`, and `holds_or_restrictions` (`true`, `false`, or `null` if unexposed).
- `card`: object with `card_id`, `account_id`, `user_id`; optionally `status`.
- `transaction`: object with `transaction_id`, `account_id`, `date`, `amount`, `type`; optionally `description` and `status`.
- `disputes`: list of prior dispute objects containing `account_id` and `status`.
- `case`: object containing `category`, `transaction_type`, `discovery_date`, `disputed_amount`, `card_in_possession`, `pin_compromised`, `contacted_merchant`, and `written_statement_provided`. Optionally include `statement_timing` (`within_2_business_days`, `within_60_days`, `after_60_days`, or `unknown`) and `police_report_filed`.
- `atm`: object containing `rho_bank_owned`; optionally `journal_confirmed_discrepancy` when an actual result exists.

### Output schema

The output includes `eligible_to_file`, blocking `errors`, non-blocking `warnings`, dispute-capacity information, `provisional_credit_eligible`, and `file_args` only when complete documented filing facts are present. An absent statement-timing value produces a provisional-credit warning, not a filing error.

Example executor usage:

```text
run_skill_script(
  relative_path="scripts/build_dispute_plan.py",
  input_json={runtime-derived account, card, transaction, dispute, claim, and ATM facts}
)
```

Resolve `errors` using supported evidence. Warnings about an unavailable journal, unavailable statement timing, unavailable restrictions, or pending ATM investigation do not alone block filing.
