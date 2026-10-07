---
name: debit-card-dispute-workflow
description: Safely intake, validate, file, and follow up on debit-card transaction disputes, including Regulation E provisional-credit analysis, duplicate transactions, ATM-specific handling, and required card-security actions. Use for a verified customer's debit-card transaction error, unauthorized transaction, fraud, ATM issue, duplicate, merchant non-delivery, incorrect amount, or cancelled recurring-charge request.
---

# Debit Card Dispute Workflow

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Use this workflow only for debit-card transactions linked to a checking account. Do not confuse debit-card activity with credit-card transactions.

## Required tools and information

The workflow uses these documented banking tools after identity verification:

- `get_all_user_accounts_by_user_id_3847(user_id)` — find the customer's checking accounts, account class/tier, status, and opening date.
- `get_debit_cards_by_account_id_7823(account_id)` — locate the card and confirm its linked account, owner, last four digits, and status.
- `get_bank_account_transactions_9173(account_id)` — find the exact posted transaction ID, date, amount, and description.
- `file_debit_card_transaction_dispute_6281(...)` — file a validated dispute.
- `freeze_debit_card_3892(card_id)` — perform the required freeze when the final card action is freeze.

Unlock and use a documented agent-discoverable tool before calling it. Do not invent tool names, account facts, transaction IDs, statement dates, dispute counts, bank/ATM ownership, or filing outcomes. If an eligibility fact cannot be determined through declared tools or customer-provided information, obtain it before filing.

## 1. Verify, identify, and disclose

1. Identify the customer and retrieve their profile.
2. Verify identity by having the customer confirm at least two of date of birth, email, phone number, and address against the retrieved profile. Then call `log_verification` with the complete returned profile fields and current timestamp. A name or email supplied merely to find the profile is not by itself sufficient verification.
3. Confirm the customer owns the checking account and the card.
4. Before proceeding with an unauthorized-activity report, explain the Regulation E timing protection based on when the customer noticed activity relative to the statement: within 2 business days has maximum $50 liability; within 60 days has maximum $500 liability; after 60 days may mean unlimited liability and no recovery. If the statement date or timing is unknown, explain the general tiers without asserting a case-specific liability amount and obtain the missing date.
5. Gather, for every proposed dispute: card/account or last four digits, merchant/ATM, transaction date, full transaction amount, amount actually disputed, discovery date, what happened, channel (PIN/signature/online/ATM/recurring/P2P), card possession, PIN-compromise status, merchant-contact result where required, and agreement to a written statement. Treat an agreed conversation statement as `written_statement_provided: true`.

## 2. Locate and validate each transaction

For each affected account:

1. Retrieve accounts and select an `OPEN` checking account. Confirm its tier, opening date, and that there are no holds or restrictions. A debit card cannot support this filing if its linked checking account is not open.
2. Retrieve cards for the account. Match the customer-provided card details, verify the card belongs to the customer, and record its `card_id`. Confirm it is usable for the required post-filing action; in particular, only an `ACTIVE` card can be frozen.
3. Retrieve transactions for the account and match by date, amount, description, and card circumstances. Use the returned `transaction_id`, exact `date`, and absolute debit amount. Do not file against a pending, unmatched, credit, or wrong-account transaction.
4. Confirm the disputed amount is at least $1.00, is no more than the relevant transaction amount, and the transaction is no more than 60 days old under the dispute rule.
5. Determine the number of already-open disputes for **that account**, using a declared normal banking source if available. Enforce the per-account maximum: Entry 2, Mid 3, Premium 4, Elite 5. If the open-dispute count cannot be established, do not assert that the limit is satisfied or file until it is available.
6. For duplicate charges, identify the complete duplicate series and dispute the earliest/first transaction, not a later duplicate. Do not submit later duplicates in place of the first one.

## 3. Classify accurately and collect category prerequisites

Select exactly one dispute category:

- `unauthorized_transaction`: not authorized, but fraud is **not** suspected (for example, a family member used the card without permission).
- `card_present_fraud`: fraud suspected and the physical card was used in person.
- `card_not_present_fraud`: fraud suspected for an online or phone transaction.
- `atm_cash_discrepancy`: ATM gave incorrect/no cash.
- `atm_deposit_not_credited`: ATM deposit absent from account.
- `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` as applicable.

Use one exact transaction type: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.

Ask whether fraud is suspected before choosing an unauthorized category. Ask whether the card remains in possession and whether the PIN is `yes_shared`, `yes_observed`, `no`, or `unknown`. For every non-fraud dispute, obtain confirmation that the customer tried to resolve it with the merchant before filing. If they have not, explain that merchant contact is required and pause that individual filing; do not use an untrue `contacted_merchant` value.

For suspected fraud over $500, ask whether a police report was filed and recommend one if it was not. Record the truthful boolean either way.

### ATM cases

Ask whether the ATM is Rho-Bank branded or third party.

- For a Rho-Bank ATM cash discrepancy, review corresponding checking-account transactions/journal information if available. If a discrepancy is confirmed, arrange immediate provisional credit. If records show the stated amount, explain that the claim is not validated but the customer may still formally dispute it.
- For a Rho-Bank ATM deposit issue, retrieve deposit images with `get_atm_deposit_images_8473` if that documented tool is available and compare them with the claim.
- A card retained by a Rho-Bank ATM is not a transaction dispute by itself; offer retrieval within 3 business days or replacement, unless unauthorized transactions also exist.
- For a third-party ATM cash discrepancy, submit the required chargeback process and explain the investigation may take 90 days. If the disputed amount exceeds $200, tell the customer that an Electronic Fund Transfer Error Resolution Affidavit will be emailed to their registered address, must be returned within 10 business days, and false signing is a federal offense. Do not claim it has been emailed unless the appropriate declared action succeeds.

## 4. Determine provisional-credit eligibility

Evaluate each dispute individually. Required provisional credit exists only when all applicable requirements are satisfied: timely reporting within 60 days of the statement date, category is one of `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`, written statement is provided, and the checking account is open with no holds or restrictions.

It is not required for `goods_services_not_received`, `recurring_charge_after_cancellation`, `atm_deposit_not_credited`, or `incorrect_amount`; when a non-fraud customer has not contacted the merchant; when `pin_compromised` is `yes_shared`; or for a card-not-present transaction on an account open fewer than 30 days. Do not mark it required when any of those exclusions applies.

When required, provisional credit is for the full disputed amount, subject to any applicable late-reporting liability offset. Standard accounts receive it within 10 business days; accounts open fewer than 30 days within 20 business days. A qualifying third-party ATM dispute remains due within 10 business days. Explain that provisional-credit investigations may take 45 business days, or 90 days for international/foreign POS, new-account, or applicable third-party ATM matters. If denied after provisional credit, the customer receives written notice at least 3 business days before reversal and may request supporting documents.

Use `scripts/plan_disputes.py` to produce a deterministic eligibility and card-action check from gathered facts. The helper is advisory: it does not query systems, file disputes, issue credit, or take card action.

## 5. File eligible disputes

Only after all prerequisite facts are validated, call `file_debit_card_transaction_dispute_6281` separately for each eligible transaction with:

- `transaction_id`, `account_id`, `card_id`, `user_id`
- `dispute_category`, `transaction_date` (MM/DD/YYYY), `discovery_date` (MM/DD/YYYY), and `disputed_amount` as a positive float
- `transaction_type`, `card_in_possession`, `pin_compromised`, `contacted_merchant`, `police_report_filed`, and `written_statement_provided`
- the truthfully calculated `provisional_credit_eligible`
- the category's individual `card_action`

The individual action mapping is:

| Category | Filed `card_action` |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| Every ATM, duplicate, amount, goods/services, or recurring category | `keep_active` |

Report only successful filings as filed. For an ineligible or incomplete item, clearly state the missing prerequisite and leave it unfiled while continuing with independent eligible disputes.

## 6. Apply the most severe actual card protection

After all filings for a given card, retain each filing's own mapped metadata action, but perform only the most severe actual protection once for that card:

`close_and_reissue` > `freeze_pending_investigation` > `keep_active`.

For a required freeze, first confirm the card is active, disclose that new and recurring transactions will be declined while pending authorizations may still settle and the card can later be unfrozen, then call `freeze_debit_card_3892(card_id)` and confirm its result. For `close_and_reissue`, use only a separately declared normal banking closure/reissue process; do not substitute freezing and do not fabricate a closure/reissue tool. `keep_active` requires no card-status action.

End with a concise per-item summary: filed or not filed, category, disputed amount, provisional-credit determination/timing, ATM affidavit or chargeback requirements if applicable, and final card protection result.

## Helper input/output

Run `scripts/plan_disputes.py` with JSON on stdin:

```json
{
  "account": {"status": "OPEN", "age_days": 45, "has_holds_or_restrictions": false},
  "disputes": [
    {
      "card_id": "runtime card id",
      "category": "duplicate_charge",
      "transaction_type": "signature_purchase",
      "disputed_amount": 25.0,
      "transaction_amount": 25.0,
      "within_60_days": true,
      "timely_statement_report": true,
      "written_statement_provided": true,
      "contacted_merchant": true,
      "pin_compromised": "no"
    }
  ]
}
```

It emits JSON containing `valid`, `errors`, category-specific `card_action`, `provisional_credit_required`, any exclusion reasons, affidavit requirement, and a per-card most-severe `actual_card_action`. Use the result as a consistency check, then independently verify all transaction, account, ownership, tier-limit, and statement-date facts through the banking workflow.
