---
name: debit-card-dispute-filing
description: Gather, validate, file, and follow up on debit-card transaction disputes, including fraud, duplicates, ATM errors, Regulation E disclosures, provisional-credit assessment, account-level limits, and required card security actions. Use when a verified customer requests a debit-card, ATM, recurring-payment, or debit-card-fraud dispute.
---

# Debit-card dispute filing

## Core execution rule

A successful specialist transfer, security handoff, or promise to investigate is **not** a substitute for filing a supported dispute. Once the filing prerequisites and tool arguments are available, unlock and call `file_debit_card_transaction_dispute_6281` with the exact validated payload. File first, then perform or arrange the separately required card action.

Do not invent transaction, account, card, user, statement, merchant-contact, PIN, fraud, or ATM-network facts. Do not claim a filing, freeze, closure, or reissue succeeded unless its tool/action succeeded.

## Workflow

1. **Verify the customer.** Retrieve the profile from a supplied identifier. Confirm any two of date of birth, email, phone number, and address against the profile, obtain the current time, and call `log_verification`. A name alone does not count as one of the two fields.
2. **Identify the account and card.** Unlock and use:
   - `get_all_user_accounts_by_user_id_3847` to identify the requested checking account, its class/tier, status, and opening date.
   - `get_debit_cards_by_account_id_7823` to identify the linked card, cardholder, status, and last four digits.
3. **Identify the exact debit.** Unlock `get_bank_account_transactions_9173` and retrieve the selected account history. Reconcile the merchant, date, amount, and exact `transaction_id`. For duplicates, identify matching records and select the earliest transaction; if ordering cannot be established, obtain it rather than guessing.
4. **Check dispute capacity.** Unlock `get_debit_dispute_status_7483`. Count unresolved statuses (`OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED`) for the selected account only. The maximum open disputes is Entry 2, Mid 3, Premium 4, Elite 5.
5. **Collect required case facts.** Ask for missing facts listed below. For suspected unauthorized activity, explain the Regulation E liability timing before proceeding: within 2 business days of the statement, maximum $50; within 60 days, maximum $500; after 60 days, potentially unlimited liability and no recovery. Do not equate a transaction date with the statement date.
6. **Validate and plan.** Optionally run `scripts/dispute_planner.py` using the documented schema below. It never performs banking actions. Resolve every `blocking` result before filing.
7. **File each supported dispute.** Unlock `file_debit_card_transaction_dispute_6281`, then call it through `call_discoverable_agent_tool` with its exact JSON filing arguments. Submit one complete payload per transaction. A failure for one case must not silently prevent filing other independently supported cases.
8. **Secure the card after filing.** Preserve each filing's own `card_action`. For all successfully filed disputes on a card, execute the one most severe actual action: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`.
   - For `freeze_pending_investigation`, use `freeze_debit_card_3892` when available in the normal workflow.
   - For `close_and_reissue`, use the authorized closure/reissue workflow when available. If it is unavailable, transfer only **after filing** with `reason: fraud_or_security_concern` or `specialized_department_required`, and include the card ID, transaction ID(s), fraud category, and explicit replacement/security work in the summary.
   - `keep_active` requires no card-status change.
9. **Confirm the outcome.** State the actual filing result, required card action status, and the provisional-credit determination without overstating unverified eligibility.

## Filing prerequisites and intake

A filing requires a verified customer, an exact transaction, a checking account that is `OPEN` without holds/restrictions, and a debit card linked to that account. The transaction must be a debit of at least $1.00 and no more than 60 days old. The card must belong to the selected account and verified user.

For every case collect:

- merchant or ATM, transaction date, amount, issue description, and discovery date;
- dispute category and transaction type;
- whether the card is in the customer's possession;
- PIN status: `yes_shared`, `yes_observed`, `no`, or `unknown`;
- written-statement consent. The conversation can serve as the written statement if the customer agrees;
- merchant-contact response for non-fraud matters; have the customer attempt merchant resolution before filing a non-fraud merchant dispute when required;
- ATM owner (`rho_bank` or `third_party`) for ATM cases;
- police-report response for fraud over $500, and recommend a report if none was filed;
- for unauthorized transactions, whether fraud is suspected and whether it was physical/in-person or online/phone.

## Classification and card action

Use only these categories:

- `unauthorized_transaction` only when unauthorized but fraud is not suspected;
- `card_present_fraud` for suspected physical/in-person fraud;
- `card_not_present_fraud` for suspected online/phone fraud;
- `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` as applicable.

Use only these transaction types: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.

Set filing metadata `card_action` as follows:

| Category | card_action |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| all other categories | `keep_active` |

The metadata does not complete the actual card action.

## Provisional credit

Required provisional credit needs all of: reporting within 60 days of the **statement date**, an eligible category (`unauthorized_transaction`, either fraud category, `atm_cash_discrepancy`, or `duplicate_charge`), a written statement, and an OPEN unrestricted account. It is not required for the remaining merchant/error categories, voluntary PIN sharing, missing non-fraud merchant contact, or card-not-present fraud on an account under 30 days old.

Obtain the statement/reporting timing before deciding that credit is required. Never use the transaction date as a substitute for statement date. If filing must proceed while this timing is unavailable, provide the mandatory boolean `provisional_credit_eligible` as `false` (required eligibility is not established), record/request the missing statement-date fact, and do not tell the customer they are definitively ineligible. Reassess promptly when the fact is available.

When required, provisional credit is the full disputed amount less an established $50 or $500 liability offset, due within 10 business days (20 for accounts under 30 days). Investigation is generally 45 business days, or 90 for new accounts, international transactions, or qualifying outside-US POS transactions. An adverse result can reverse provisional credit only with written notice at least 3 business days beforehand.

## Planner script

Run:

```text
run_skill_script(relative_path="scripts/dispute_planner.py", input_json=<object>)
```

The script reads one JSON object and emits one JSON object. It accepts:

```json
{
  "as_of_date": "MM/DD/YYYY",
  "user_id": "string",
  "account": {
    "account_id": "string",
    "account_type": "checking",
    "account_class": "Entry|Mid|Premium|Elite",
    "status": "OPEN",
    "has_hold_or_restriction": false,
    "date_opened": "MM/DD/YYYY"
  },
  "card": {"card_id": "string", "account_id": "string", "user_id": "string"},
  "transactions": [{"transaction_id": "string", "account_id": "string", "date": "MM/DD/YYYY", "description": "string", "amount": -1.0, "type": "debit_card_purchase", "status": "posted"}],
  "open_disputes": [{"account_id": "string", "status": "OPEN"}],
  "cases": [{
    "merchant_query": "string", "transaction_date": "MM/DD/YYYY", "disputed_amount": 1.0,
    "discovery_date": "MM/DD/YYYY", "dispute_category": "duplicate_charge",
    "transaction_type": "signature_purchase", "card_in_possession": true,
    "pin_compromised": "no", "contacted_merchant": true, "police_report_filed": false,
    "written_statement_provided": true, "timely_statement_reporting": null,
    "liability_offset": null, "atm_network": null,
    "international_or_outside_us_pos": false
  }]
}
```

`timely_statement_reporting` is `true`, `false`, or `null` when statement timing is unavailable. `liability_offset` is `0`, `50`, `500`, or `null` when unestablished. The planner returns `ready`, `blocking`, `warnings`, and `filings`; each filing has a complete `tool_arguments` object. Only file when `ready` is true. The executor, not the script, calls the banking tool and performs card security work.
