---
name: debit-card-dispute-filing
description: Safely gather, validate, file, and follow up on debit-card transaction disputes, including duplicate charges, Regulation E disclosures, provisional-credit assessment, per-account dispute limits, and required post-filing card actions. Use when a verified customer asks to dispute debit-card, ATM, recurring, or card-fraud transactions.
---

# Debit-card dispute filing

## Scope and safety

Use this Skill only for a debit card linked to a checking account. Do not file a dispute until the customer is identity-verified, the transaction/card/account have been retrieved, and every required filing field is known. Never infer a transaction ID, card ID, account status, merchant-contact answer, fraud determination, PIN status, or ATM ownership.

The filing tool records the required `card_action` as metadata only. After all disputes for a card are filed, separately perform the single most severe required card action using normal banking tools. Do not claim that a card was frozen, closed, or reissued unless that separate action succeeded.

## Runtime tool workflow

1. **Verify identity.** Retrieve the customer profile using a supplied identifier. Ask the customer to confirm two of the four verification fields: date of birth, email, phone number, and address. Compare their answers with the profile, then call `log_verification` with the complete profile and current timestamp. A stated name is not one of the two verification fields.
2. Unlock and use these discoverable tools as needed:
   - `get_all_user_accounts_by_user_id_3847` — identify the requested OPEN checking account, its account class/tier, and opening date.
   - `get_debit_cards_by_account_id_7823` — locate the card linked to that account; confirm the last four digits and cardholder user ID.
   - `get_bank_account_transactions_9173` — retrieve transactions and locate the exact posted debit.
   - `get_debit_dispute_status_7483` — count unresolved/open disputes for the selected **account**, not across the customer.
   - `file_debit_card_transaction_dispute_6281` — file only validated cases.
3. Use `scripts/dispute_planner.py` after converting tool output into its documented JSON schema. Treat `ready: false` and any `blocking` entries as a stop condition. The script validates deterministic rules and produces filing payloads; the agent remains responsible for asking missing questions and executing banking tools.
4. File one case at a time with the exact payload returned by the planner. For duplicate charges, file the earliest transaction in each duplicate set first. Do not file a later duplicate when the earlier transaction cannot be identified.
5. Group successfully filed disputes by `card_id`. Preserve each filing's own mapped `card_action`, then take the most severe action once per card: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`.
   - `freeze_pending_investigation`: use `freeze_debit_card_3892` if it is available through the normal banking-tool workflow.
   - `close_and_reissue`: use the authorized card closure/reissue workflow available in the runtime. If no such authorized tool is available, do not invent a call or state it occurred; route it through the approved card/security workflow.
   - `keep_active`: no card-status change is needed.
6. Tell the customer the filing result, whether provisional credit is required, the applicable credit timing (10 business days, or 20 for an account open under 30 days), and that provisional credit may be reversed after an adverse investigation with written notice at least 3 business days before reversal.

## Required intake and pre-filing checks

For every requested transaction obtain:

- merchant/ATM, transaction date, dollar amount, and what happened;
- discovery date;
- category and transaction type;
- card possession and PIN-compromise value (`yes_shared`, `yes_observed`, `no`, or `unknown`);
- merchant-contact answer for every non-fraud dispute;
- written-statement consent; this conversation may be the statement if the customer agrees;
- for ATM matters, whether it was a Rho-Bank ATM or third-party ATM, and follow the applicable ATM process before filing;
- for fraud over $500, whether a police report was filed; recommend one if not;
- for suspected unauthorized activity, whether fraud is suspected and whether the transaction was physical/in-person or online/phone.

Before proceeding with unauthorized activity, explain the Regulation E exposure based on the customer’s reporting timing: within 2 business days, maximum $50; within 60 days, maximum $500; after 60 days, potentially unlimited liability and no recovery. Use actual statement/reporting timing where available; do not represent a calendar-day approximation as a legal determination.

Validate all of the following:

- disputed transaction is at least $1.00, is a debit, and is within 60 days old;
- linked checking account is `OPEN` and has no hold or restriction;
- the chosen card belongs to that account and customer;
- unresolved disputes on that account do not exceed the tier limit after the new filing: Entry 2, Mid 3, Premium 4, Elite 5;
- exact transaction ID, amount, and `MM/DD/YYYY` transaction/discovery dates are available;
- non-fraud cases have attempted merchant contact. If the customer has not contacted the merchant, explain that they should first attempt resolution and hold filing unless an applicable exception or escalation path is supplied.

For a duplicate, locate all matching debit-card records. Select the chronologically earliest matching transaction. If transactions have the same date and the records do not establish which occurred first, request enough information or use a source with transaction ordering; do not guess.

## Classification rules

Use exactly one allowed category:

- `unauthorized_transaction`: not authorized but fraud is **not** suspected;
- `card_present_fraud`: suspected fraud at a physical/in-store transaction;
- `card_not_present_fraud`: suspected fraud online or by phone;
- `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` as applicable.

Use exactly one transaction type: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.

Record this `card_action` in every filing:

| Category | card_action |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| all other allowed categories | `keep_active` |

## Provisional credit decision

Required provisional credit needs all of: timely reporting within 60 days of the statement, an eligible category (`unauthorized_transaction`, either fraud category, `atm_cash_discrepancy`, or `duplicate_charge`), a written statement, and an OPEN unrestricted account. It is not required for the other listed merchant/error categories, when a non-fraud customer did not contact the merchant, when `pin_compromised` is `yes_shared`, or for a card-not-present transaction on an account under 30 days old. Eligibility means required credit, not that discretionary credit is impossible.

The required amount is the full disputed amount, reduced by any applicable $50/$500 liability offset for a late report. Investigation is generally 45 business days where provisional credit is issued; it is 90 days for new accounts, international transactions, or POS transactions outside the US.

## Planner script

Run:

```text
run_skill_script(relative_path="scripts/dispute_planner.py", input_json=<schema below>)
```

Input is a JSON object:

```json
{
  "as_of_date": "MM/DD/YYYY",
  "account": {"account_id": "string", "account_type": "checking", "account_class": "Entry|Mid|Premium|Elite", "status": "OPEN", "has_hold_or_restriction": false, "date_opened": "MM/DD/YYYY"},
  "card": {"card_id": "string", "account_id": "string", "user_id": "string", "status": "ACTIVE"},
  "user_id": "string",
  "transactions": [{"transaction_id": "string", "account_id": "string", "date": "MM/DD/YYYY", "description": "string", "amount": -47.5, "type": "debit_card_purchase", "status": "posted"}],
  "open_disputes": [{"account_id": "string", "status": "OPEN"}],
  "cases": [{"merchant_query": "string", "transaction_date": "MM/DD/YYYY", "disputed_amount": 47.5, "discovery_date": "MM/DD/YYYY", "dispute_category": "duplicate_charge", "transaction_type": "signature_purchase", "card_in_possession": true, "pin_compromised": "no", "contacted_merchant": true, "police_report_filed": false, "written_statement_provided": true, "timely_statement_reporting": true, "liability_offset": 0, "atm_network": null, "international_or_outside_us_pos": false}]
}
```

`as_of_date` is required for the 60-day transaction-age check. `timely_statement_reporting` must be established from statement/report timing; set it to `null` when unknown. `liability_offset` must be `0`, `50`, or `500` only when established; use `null` when unknown. Include `atm_network` as `rho_bank`, `third_party`, or `null`; ATM cases require a non-null value. For duplicate cases, `merchant_query`, date, and amount identify the candidate set.

The output contains `ready`, `blocking`, `warnings`, and `filings`. Each filing contains a complete `tool_arguments` object for `file_debit_card_transaction_dispute_6281`, the provisional-credit determination, and a card action. Validate that there are no blocking entries before filing.
