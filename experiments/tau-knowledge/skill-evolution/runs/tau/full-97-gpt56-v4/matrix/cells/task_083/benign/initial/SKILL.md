---
name: debit-card-dispute-filing
description: File one or more eligible debit-card transaction disputes while satisfying Regulation E intake, account/card/dispute-limit checks, provisional-credit assessment, ATM requirements, and required post-filing card action. Use when a verified customer reports debit-card purchases or ATM errors.
---

# Debit-card dispute filing

Use this Skill for debit-card disputes only. Do not substitute credit-card records or assume customer-provided account, card, transaction, or dispute-count details are current.

## Required intake and disclosure

1. Identify the customer and verify identity using two account fields. Retrieve the customer record, obtain the current time, and call `log_verification` with the retrieved account fields and timestamp before filing.
2. Before proceeding, tell the customer their Regulation E exposure based on when they noticed unauthorized activity: within 2 business days, maximum $50; within 60 days, maximum $500; after 60 days, potentially unlimited/no recovery. Do not characterize this as a guarantee of recovery.
3. For each claimed transaction collect:
   - card (last four digits is useful), merchant/ATM, transaction date, and full transaction amount;
   - date first noticed; transaction type; whether physical card remains in possession; PIN-compromise value (`yes_shared`, `yes_observed`, `no`, or `unknown`);
   - whether merchant contact was attempted for non-fraud merchant disputes;
   - suspected-fraud facts and whether the transaction was physical or online/phone;
   - police-report status for suspected fraud above $500;
   - agreement to provide a written statement (the conversation may be used if the customer agrees).
4. For ATM claims, determine whether the ATM is Rho-Bank owned or third-party. For a third-party cash-discrepancy claim over $200, explain the affidavit requirement, email delivery, 10-business-day return deadline, and possible denial if it is not returned. Record only information actually supplied.

## Retrieve and verify authoritative records

Unlock and use the declared banking tools as needed:

1. `get_all_user_accounts_by_user_id_3847(user_id)` to find the relevant checking account, its status, class/tier, and opening date.
2. `get_debit_cards_by_account_id_7823(account_id)` for each candidate checking account. Match the card, ensure its `user_id` is the customer, and retain its current status.
3. `get_bank_account_transactions_9173(account_id)` to match every claimed transaction by date, amount, and description and obtain its exact `transaction_id`. Do not file based only on an approximate match. Confirm a debit amount and use the absolute dollar amount as `disputed_amount`.
4. `get_debit_dispute_status_7483(user_id)` to count active disputes **on each account separately**. Treat `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED` as active unless the runtime provides a more specific authoritative definition. The maximum active disputes is Entry 2, Mid 3, Premium 4, Elite 5.

File only when all applicable prerequisites are satisfied: verified customer; transaction is at least $1; transaction is within 60 days; linked checking account is OPEN; matched card/account/customer linkage is valid; and adding the disputes does not exceed that account's limit. Explain and stop/escalate for a transaction that fails a prerequisite rather than guessing or filing it against another account.

For duplicate charges, identify all matching duplicates and dispute the earliest/first transaction only. Do not create duplicate filings for later matching entries.

## Classify each dispute exactly

Use only the exact tool enums below.

- Suspected fraud: `card_present_fraud` for a physical/in-store transaction, `card_not_present_fraud` for online or phone. Do not use `unauthorized_transaction` when fraud is suspected.
- No fraud suspected, but customer did not authorize it (for example, a family member exceeded permission): `unauthorized_transaction`.
- ATM dispensed no/wrong cash: `atm_cash_discrepancy`.
- ATM deposit absent: `atm_deposit_not_credited`.
- Repeated same charge: `duplicate_charge`.
- Wrong charged value: `incorrect_amount`.
- Paid but never received: `goods_services_not_received`.
- Charge after canceled subscription: `recurring_charge_after_cancellation`.

Select `transaction_type` exactly as: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.

Set filing metadata `card_action` from the category, without altering it due to another claim:

| Category | card_action |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| all ATM, duplicate, amount, goods/services, and recurring categories | `keep_active` |

## Provisional-credit decision

Set `provisional_credit_eligible` only after evaluating the authoritative facts. It is required when all are true: timely report within 60 days of the statement date, category is `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`; written statement is provided; and the account is OPEN with no hold/restriction.

It is not required for `goods_services_not_received`, `recurring_charge_after_cancellation`, `atm_deposit_not_credited`, or `incorrect_amount`; when an applicable non-fraud merchant dispute was not first raised with the merchant; when the PIN was voluntarily shared (`yes_shared`); or for a card-not-present transaction on an account under 30 days old. If statement timing, account restrictions, or any other needed fact cannot be determined, do not claim required eligibility—obtain the fact or explain the limitation.

Qualifying provisional credit is the full disputed amount subject to a documented late-report liability offset. State the expected timing: 10 business days normally, 20 business days for an account opened under 30 days. Third-party ATM claims may take up to 90 days; their qualifying provisional credit is still due within 10 business days. Do not issue credit yourself unless a declared banking tool explicitly performs that action.

## File and secure the cards

For every eligible transaction, unlock `file_debit_card_transaction_dispute_6281` and call it with all required fields:

```text
transaction_id, account_id, card_id, user_id, dispute_category,
transaction_date (MM/DD/YYYY), discovery_date (MM/DD/YYYY), disputed_amount,
transaction_type, card_in_possession, pin_compromised, contacted_merchant,
police_report_filed, written_statement_provided, provisional_credit_eligible,
card_action
```

Use the exact matched transaction date and transaction amount. Never invent a police report, written statement, merchant contact, or fraud finding.

After all successful filings, perform one actual action per affected card using the most severe successful filing action for that card: `close_and_reissue` outranks `freeze_pending_investigation`, which outranks `keep_active`. Do not take an action for a failed filing.

For a required freeze, confirm the card belongs to the verified customer and is currently ACTIVE; tell the customer that new and recurring transactions will decline while pending transactions may still post and that unfreezing is possible; then unlock and call `freeze_debit_card_3892(card_id)`. Confirm the result. If a close/reissue action is required, use only a declared normal banking tool that supports that action; if none is available, do not simulate it and transfer/escalate for completion.

Finish with a concise per-transaction result, applicable documentation/affidavit next steps, provisional-credit status/timing, and the actual card-security action taken. Never expose internal-only security codes.

## Optional planning helper

`scripts/plan_disputes.py` is a deterministic preflight checker; it does not call bank tools or file disputes. Give it already retrieved, authoritative facts. It reads one JSON object from stdin and emits a JSON object with per-item errors, mapped card actions, provisional-credit decisions, active-limit totals, and per-card most-severe actions.

Example input shape:

```json
{
  "account_limits": {"acct": {"tier": "Mid", "existing_active": 1}},
  "items": [{"account_id": "acct", "card_id": "card", "amount": 25.0,
    "age_days": 4, "category": "duplicate_charge", "written_statement_provided": true,
    "statement_timely": true, "account_open_unrestricted": true,
    "merchant_contact_required": false, "contacted_merchant": false,
    "pin_compromised": "no", "new_account_card_not_present": false}]
}
```

Review `errors` before any filing. Runtime facts and tool results always override helper output.
