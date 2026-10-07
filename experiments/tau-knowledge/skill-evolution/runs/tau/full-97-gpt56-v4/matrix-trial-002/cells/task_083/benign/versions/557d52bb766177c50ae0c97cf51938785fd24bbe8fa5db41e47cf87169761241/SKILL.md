---
name: debit-card-dispute-intake-and-filing
description: Safely verify, qualify, file, and follow up on one or more debit-card transaction disputes, including Regulation E disclosures, provisional-credit decisions, ATM handling, and card security actions. Use when a customer reports unauthorized debit-card activity, ATM errors, duplicate charges, incorrect amounts, missing goods, or recurring charges.
---

# Debit-card dispute intake and filing

Use this Skill for debit-card disputes only. Do not substitute credit-card tools or file a dispute from customer-supplied merchant details alone: locate and verify every transaction in the linked checking account's history.

## Required intake and verification

1. Identify the customer using an approved lookup. Ask the customer to confirm **two of the four** identity fields: date of birth, registered email, phone number, or address. Do not treat information returned by a lookup as a customer confirmation.
2. Get the current timestamp, then call `log_verification` with all required fields and that timestamp after two fields have been confirmed.
3. Before filing, give the Regulation E liability disclosure for unauthorized activity: reporting within 2 business days of the statement has a maximum $50 liability; within 60 days has a maximum $500 liability; after 60 days liability may be unlimited and funds may not be recoverable. If the statement date or reporting timing is unknown, state the limits without assigning a tier and obtain the statement date/timing.
4. Collect, per proposed dispute:
   - transaction date, amount, merchant/ATM, and date first noticed;
   - whether fraud is suspected and, if so, whether it was physically present or online/phone;
   - transaction type; whether the physical card remains in possession; PIN compromise status;
   - whether the merchant was contacted for every non-fraud claim;
   - written-statement agreement; record it as true only if the customer agrees;
   - police-report status for fraud above $500 (recommend a report if not filed);
   - for an ATM claim, whether the ATM is Rho-Bank branded and, for a cash discrepancy, the amount actually dispensed so the disputed amount is the shortage rather than automatically the full withdrawal.

A customer saying that a relative used a card beyond permission is not by itself fraud. Confirm whether fraud is suspected. Use `unauthorized_transaction` only when fraud is not suspected; otherwise use the applicable card-present or card-not-present fraud category.

## Retrieve and qualify records

After verification, unlock and use these documented banking tools as needed:

- `get_all_user_accounts_by_user_id_3847` to find a checking account. It must be `OPEN` and linked to the debit card.
- `get_debit_cards_by_account_id_7823` to identify the card by its last four digits and confirm its account and cardholder.
- `get_bank_account_transactions_9173` for each candidate checking account. Match the actual `transaction_id`, date, description, and debit amount. Transactions are reverse chronological.
- `get_debit_dispute_status_7483` to count active disputes for the same account before filing. Count unresolved statuses conservatively: `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED`.
- `get_atm_deposit_images_8473` for an Rho-Bank ATM deposit-not-credited claim.
- `file_debit_card_transaction_dispute_6281` only after all filing parameters and eligibility checks are complete.

Pre-filing checks for each claim are: verified customer; transaction is a debit of at least $1; transaction occurred within 60 days; an `OPEN` linked checking account; and sufficient remaining account-level dispute capacity. Capacity is Entry 2, Mid 3, Premium 4, Elite 5 active disputes. Capacity is per account, so reserve capacity for the whole batch before filing any of it. Stop and explain/escalate if a required condition is not met.

For duplicates, retrieve all matching copies and file only the **earliest** transaction. Do not file later duplicates merely because they appear first in reverse-chronological history.

## Choose exact filing values

Use only these dispute categories:

- `unauthorized_transaction`
- `atm_cash_discrepancy`
- `atm_deposit_not_credited`
- `duplicate_charge`
- `incorrect_amount`
- `goods_services_not_received`
- `recurring_charge_after_cancellation`
- `card_present_fraud`
- `card_not_present_fraud`

Use only these transaction types: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.

Map the filing's `card_action` exactly as follows:

| Category | card_action |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| all ATM, duplicate, incorrect amount, missing goods, and recurring categories | `keep_active` |

Set `contacted_merchant` from the customer's actual answer; it is required information for non-fraud claims. A false answer does not permit inventing contact. It also prevents a required provisional-credit determination for a non-fraud claim under the supplied guidelines.

Set `police_report_filed` for every filing; for fraud above $500, ask and recommend a police report when false. Set `written_statement_provided` true only after the customer agrees to provide one (an agreed conversation may serve as the statement).

Use the actual transaction date and customer discovery date in `MM/DD/YYYY`; use a positive dollar amount for `disputed_amount`, no greater than the relevant debit/shortage. Never infer a transaction ID, amount, or date from the customer's narrative if account history disagrees.

## Provisional credit decision

Set `provisional_credit_eligible` to true only when all required conditions are established:

1. Timely report within 60 days of the statement;
2. category is `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`;
3. written statement is provided; and
4. checking account is open with no hold or restriction.

Set it false (or pause rather than guess if a required fact is unknown) where an exclusion applies: categories for missing goods, recurring cancellation, ATM deposit, or incorrect amount; non-fraud merchant contact was not attempted; PIN was voluntarily shared; or a new account (under 30 days) has a card-not-present transaction. For a qualifying claim, provisional credit is for the full disputed amount, reduced by applicable late-reporting liability. Required timing is within 10 business days, or 20 for an account under 30 days. Investigation is generally 45 business days once credit is issued and 90 for international, qualifying out-of-US merchant POS, or new-account matters.

## ATM procedures

Determine ATM ownership; do not assume from a merchant name.

- For a Rho-Bank ATM cash discrepancy, review corresponding account activity/journal evidence. If confirmed, issue provisional credit immediately; if journal records show the stated amount, explain that the claim cannot be validated but the customer may formally dispute it.
- For a Rho-Bank ATM deposit issue, obtain deposit images and compare them with the claimed deposit.
- For a third-party ATM, explain that a chargeback goes to the owner/network, investigation may take 90 days, and required provisional credit remains due within 10 business days when eligible.
- For a third-party ATM cash discrepancy **over $200**, tell the customer that an Electronic Fund Transfer Error Resolution Affidavit will be emailed, must be signed and returned within 10 business days, and failure to return it may result in denial. Explain that false signing is a federal offense. Do not claim the affidavit was sent unless the available workflow actually sends it.

## File and take card action

For each fully qualified claim, call `file_debit_card_transaction_dispute_6281` with every required argument. Save the returned dispute ID/status in the case notes. A filing tool call does not itself change card status.

When multiple disputes use one card, preserve each filing's own mapped `card_action`. After all successful filings, perform **one** actual action for that card using the most severe successful filing action:

`close_and_reissue` > `freeze_pending_investigation` > `keep_active`.

Use the normal approved card-action tool/workflow available in the runtime. `freeze_debit_card_3892` is the documented freeze operation. A card close/reissue is a card action, not a checking-account closure; do not close the deposit account merely because a replacement card is needed. If the required normal action tool or authority is unavailable, do not claim it happened; explain and escalate through the approved workflow.

Finish with a concise customer summary: filed claims and claimed amounts, any unresolved prerequisite/document requirement, the affidavit requirement if relevant, card action actually taken, provisional-credit eligibility/timing, and expected investigation timeline. Never promise a dispute outcome.

## Optional deterministic planner

`scripts/plan_debit_disputes.py` validates a structured intake and produces a filing/readiness plan. It does not call banking tools and does not file, credit, freeze, close, or reissue anything.

Run it by sending JSON on stdin:

```json
{
  "as_of": "MM/DD/YYYY",
  "verified": true,
  "account": {"account_id": "...", "account_type": "checking", "status": "OPEN", "account_class": "Mid", "date_opened": "MM/DD/YYYY", "has_holds_or_restrictions": false},
  "existing_disputes": [],
  "disputes": [{"transaction_id": "...", "account_id": "...", "card_id": "...", "user_id": "...", "transaction_date": "MM/DD/YYYY", "transaction_amount": -10.0, "discovery_date": "MM/DD/YYYY", "disputed_amount": 10.0, "category": "duplicate_charge", "transaction_type": "signature_purchase", "card_in_possession": true, "pin_compromised": "no", "contacted_merchant": true, "police_report_filed": false, "written_statement_provided": true, "reported_within_60_days_of_statement": true, "fraud_suspected": false, "card_status": "ACTIVE", "duplicate_candidates": []}]
}
```

The script emits JSON with `ready_to_file`, per-dispute errors/warnings, computed `card_action`, provisional-credit decision, deadline guidance, and per-card final action. Feed it facts obtained at runtime; it deliberately rejects missing or inconsistent facts instead of fabricating them.
