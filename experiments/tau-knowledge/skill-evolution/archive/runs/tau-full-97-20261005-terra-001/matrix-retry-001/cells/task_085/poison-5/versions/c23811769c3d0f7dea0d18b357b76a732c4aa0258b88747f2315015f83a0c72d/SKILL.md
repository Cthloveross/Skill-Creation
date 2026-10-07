---
name: debit-card-atm-cash-discrepancy
version: 1.1.0
description: Safely investigate and file a debit-card ATM cash-discrepancy dispute, including Rho-Bank versus third-party ATM handling, filing-prerequisite checks, provisional-credit determination, and card-action planning.
---

# Debit-Card ATM Cash-Discrepancy Dispute

Use this Skill when a verified customer says an ATM dispensed too little cash or no cash for a debit-card withdrawal. It supports one dispute at a time and may be used again for additional transactions.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Required information and customer communication

Before collecting or filing the dispute, explain the Regulation E reporting exposure for unauthorized activity: reported within 2 business days has maximum $50 liability; within 60 days has maximum $500 liability; after 60 days liability may be unlimited and funds may not be recoverable. Explain that ATM withdrawals are covered electronic fund transfers and prompt reporting is important. Do not characterize an ATM dispensing error as fraud unless the facts support fraud.

Collect and confirm:

- Customer identity and authority. Verify at least two profile fields (date of birth, mailing address, email, or phone), retrieve the profile, obtain the current timestamp, and call `log_verification` with the retrieved profile values before any banking action.
- The selected checking account and debit card, transaction date, withdrawal amount, cash actually received, shortage amount, ATM name/location, when the customer noticed the issue, card possession, PIN-compromise choice, ATM-operator contact attempt, and written-statement consent.
- Whether the ATM is Rho-Bank branded or third-party. Use transaction details, available ATM metadata, or the customer's description; do not infer ownership solely from transaction type.
- The statement date, if available, or another reliable basis for Regulation E provisional-credit timeliness. This is relevant only to whether provisional credit is required. It is **not** a pre-filing requirement and must never delay an otherwise supported timely dispute filing.

For this category, use `atm_cash_discrepancy`, `atm_withdrawal`, and the shortage—not the entire withdrawal—as `disputed_amount`. `contacted_merchant` records whether the customer tried to contact the ATM operator; it is not a reason to omit the dispute. Set `police_report_filed` to `false` when it is inapplicable; police-report follow-up is relevant to fraud disputes over $500. Written-statement consent permits the conversation to be recorded as the written statement.

## Required runtime workflow

1. **Verify and log identity.** Retrieve the customer record, compare at least two customer-supplied identity fields, retrieve the current time, then log successful verification. Stop if verification, authority, or account ownership cannot be established.
2. **Find the eligible account and card.** Use `get_all_user_accounts_by_user_id_3847(user_id)` and select the customer-selected checking account. Confirm it is OPEN, determine its account class/tier, review its balance as required by the banking control, and ensure no hold or restriction is present in available account-standing information. Use `get_debit_cards_by_account_id_7823(account_id)` and select the card linked to that account and user. Do not substitute a closed historical card.
3. **Locate and reconcile the withdrawal.** Use `get_bank_account_transactions_9173(account_id)`. Find the exact `atm_withdrawal` record matching the customer’s date, ATM, and charged amount. The transaction ID from this record is the filing ID. The transaction must be at least $1, no more than 60 calendar days old, and the shortage must be at least $1 and no more than the withdrawal amount. Review corresponding account transaction/journal information available for a Rho-Bank ATM and record whether it confirms a discrepancy, shows the requested amount was dispensed, or is unavailable. A journal showing the requested amount does not prevent formal filing; explain that the claim was not validated by that record.
4. **Check the per-account dispute limit.** Use `get_debit_dispute_status_7483(user_id)`, count unresolved disputes only for the selected `account_id`, and compare against the account tier: Entry 2, Mid 3, Premium 4, Elite 5. Treat `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED` as unresolved. Do not count resolved or closed disputes. Stop if filing would meet or exceed the limit.
5. **Apply ATM-specific procedure.**
   - **Rho-Bank ATM:** review the journal/transaction record. If the discrepancy is confirmed, arrange immediate provisional credit through the normal available banking process; the filing tool itself does not issue credit. If the journal shows the requested amount, inform the customer the claim cannot be validated but still file the formal dispute when the filing requirements are met.
   - **Third-party ATM:** submit the ordinary formal dispute/chargeback workflow. The investigation can extend to 90 days and provisional credit remains due within 10 business days (20 for an account open fewer than 30 days).
   - For an ATM cash discrepancy exceeding $200, tell the customer an Electronic Fund Transfer Error Resolution Affidavit will be emailed to their registered email address, must be signed and returned within 10 business days, failure to return it may cause denial, and a false affidavit is a federal offense. Record the documentation requirement and follow up; do not claim it has been signed until it is returned.
6. **Determine provisional credit separately from filing eligibility.** For `atm_cash_discrepancy`, required provisional credit depends on timely reporting within 60 days of the relevant statement, a written statement, an OPEN unrestricted account, and no voluntary PIN sharing. A confirmed Rho-Bank ATM discrepancy is handled immediately. When statement-timing evidence is available, calculate and record the resulting boolean. When it is unavailable, set `provisional_credit_eligible` to `false` because required eligibility is not established, tell the customer that timing cannot yet be confirmed, and continue with the dispute filing. Never request a statement date or transfer the customer merely to decide this separate field. The normal provisional-credit deadline, when required, is 10 business days, or 20 for accounts open fewer than 30 days.
7. **Validate the filing packet.** Supply gathered normalized data to `scripts/validate_debit_dispute.py`. Resolve returned errors before filing. A missing optional `statement_date` produces a warning and a `false` provisional-credit-eligibility result; it is not a validation error. The script validates and plans only; it never performs a banking action.
8. **File once the filing prerequisites pass.** Unlock and call `file_debit_card_transaction_dispute_6281` using the validated payload. Do not wait for a statement date, a favorable journal result, or a provisional-credit determination beyond the required boolean field. The required category is `atm_cash_discrepancy`; `card_action` is `keep_active` for this individual dispute. Preserve the returned dispute identifier and any documentation or expected-resolution details.
9. **Perform the post-filing card action separately.** The filing parameter is metadata, not the action. For a single ATM cash discrepancy, keep the card active. If several disputes on the same card were filed, retain each filing’s own mapped action but perform the most severe one once after all filings: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`. Use normal available banking tools for the required action; the documented freeze action is `freeze_debit_card_3892`. If the required close-and-reissue capability is unavailable, do not simulate it—use the supported escalation or replacement-card workflow.
10. **Give accurate next steps.** State whether provisional-credit eligibility was established or remains unconfirmed, the applicable 45- or 90-day investigation expectation, affidavit need if applicable, and that a provisional credit may be reversed after an adverse finding with at least three business days’ written notice. Monitor filed disputes using `get_debit_dispute_status_7483`; escalate apparent missed provisional-credit or investigation deadlines to a supervisor.

## Filing payload

Call `file_debit_card_transaction_dispute_6281` with this shape after all values have been verified:

```json
{
  "transaction_id": "transaction from account history",
  "account_id": "selected open checking account",
  "card_id": "selected linked debit card",
  "user_id": "verified customer",
  "dispute_category": "atm_cash_discrepancy",
  "transaction_date": "MM/DD/YYYY",
  "discovery_date": "MM/DD/YYYY",
  "disputed_amount": 0.0,
  "transaction_type": "atm_withdrawal",
  "card_in_possession": true,
  "pin_compromised": "no",
  "contacted_merchant": false,
  "police_report_filed": false,
  "written_statement_provided": true,
  "provisional_credit_eligible": false,
  "card_action": "keep_active"
}
```

The shown literals are field formats, not values to reuse. Populate every value from the current customer interaction and tool results. Set `provisional_credit_eligible` to `true` only where the published conditions, including statement-based timeliness, have been established; otherwise use `false` without blocking filing.

## Validator interface

Run:

```text
python3 scripts/validate_debit_dispute.py < normalized_case.json
```

The script reads one JSON object from stdin and emits one JSON object to stdout. The input contains `today`, identity/logging flags, selected `account` and `card`, `transaction`, all user `disputes`, ATM/journal facts, optional statement-timeliness facts, and a `dispute` object. See the top-level `INPUT_SCHEMA` constant in the script for the complete field contract. Its output has `valid`, `errors`, `warnings`, `filing_payload` (only when valid), and `post_filing_card_action`.

Example invocation data must be built from live results; do not copy customer IDs, transaction IDs, dates, or amounts from another case. Before calling the filing tool, verify `valid` is `true`, recheck that the payload transaction/account/card/user IDs come from the selected live records, and ensure the filing payload’s category, transaction type, provisional-credit result, and card action match the validator output.

## Stop and escalation conditions

Do not file if identity or ownership is unverified, the account is not an unrestricted OPEN checking account, the linked card or transaction cannot be matched, the withdrawal/shortage fails amount or age rules, the account is at its unresolved-dispute limit, or required filing fields are missing. Ask a focused follow-up for missing filing facts. A missing statement date is not a missing filing fact. For missing records, conflicting transaction facts, unavailable required account-standing information, or missed regulatory timelines, do not guess—escalate through the supported supervisor/human process.
