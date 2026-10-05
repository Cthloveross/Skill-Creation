---
name: debit-card-atm-cash-discrepancy
version: 1.2.0
description: Investigate and file a verified customer's debit-card ATM cash-discrepancy dispute while separately determining provisional-credit eligibility without delaying a supported filing.
---

# Debit-Card ATM Cash-Discrepancy Dispute

Use this Skill when a customer says an ATM withdrawal dispensed too little cash or no cash. Handle one selected transaction at a time; repeat the workflow for another transaction only after completing the current one.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Collect and explain

Before filing, explain the Regulation E reporting exposure for unauthorized activity: reporting within two business days of the statement has a maximum $50 liability; within 60 days has a maximum $500 liability; after 60 days liability may be unlimited and recovery may be unavailable. Explain that ATM withdrawals are covered EFTs and prompt reporting matters. Do not misclassify an ATM dispensing error as fraud.

Collect the selected account/card, transaction date and charged withdrawal amount, ATM name or location, actual cash received, shortage, discovery date, card possession, PIN-compromise status, ATM-operator contact, and consent for the conversation to be the written statement. The shortage, not the complete withdrawal amount, is the disputed amount.

Ask the customer whether the ATM is Rho-Bank branded if that cannot be determined from the transaction description. For a non-fraud ATM dispute, `contacted_merchant` records contact with the ATM operator and is not a prerequisite to filing.

## Workflow

1. **Verify identity and authority before banking actions.** Retrieve the customer profile, compare at least two supplied profile fields (such as date of birth and mailing address), retrieve the current time, and call `log_verification` with the retrieved profile values. Stop for failed verification, unresolved authority, or ownership conflict.
2. **Review the selected checking account and card.** Call `get_all_user_accounts_by_user_id_3847(user_id)`. Confirm the customer-selected account is a checking account in `OPEN` status, belongs to the customer, and review the returned balance. Use `get_debit_cards_by_account_id_7823(account_id)` and select the linked card for that user; do not select a closed historical card.
3. **Match the withdrawal.** Call `get_bank_account_transactions_9173(account_id)` and match the selected posted `atm_withdrawal` by date, ATM description, and charged amount. The account-history `transaction_id` is the filing transaction ID. Confirm the transaction is at least $1, no more than 60 calendar days old, and that the claimed shortage is at least $1 and does not exceed the withdrawal amount.
4. **Check prior disputes.** Call `get_debit_dispute_status_7483(user_id)`. Count unresolved (`OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, or `PROVISIONAL_CREDIT_ISSUED`) disputes for the selected account. Apply the published per-account limit when the returned account tier maps to Entry (2), Mid (3), Premium (4), or Elite (5). If an account-level label does not use those names, do not invent a tier: zero unresolved disputes is below every published maximum; otherwise use the conservative Entry limit until the actual tier can be confirmed.
5. **Apply ATM handling.** For a Rho-Bank ATM, review available corresponding-account transaction/journal information. If it confirms the discrepancy, use the normal available banking process to arrange immediate credit. If it shows the requested amount or does not validate the claim, explain that result but still file the formal dispute if the filing requirements pass. For a third-party ATM, file the dispute/chargeback workflow; investigation may take up to 90 days. For a shortage over $200, tell the customer that an EFT Error Resolution Affidavit will be sent to their registered email, must be returned within 10 business days, failure to return it may cause denial, and a false affidavit is a federal offense.
6. **Determine provisional credit independently.** `atm_cash_discrepancy` is a qualifying category, but required provisional credit also requires statement-based timely reporting, a written statement, an OPEN account in good standing without holds/restrictions, and no voluntary PIN sharing. Set `provisional_credit_eligible` to `true` only when every condition is established. If statement-date timing or account-standing evidence is unavailable, set it to `false` and explain that required eligibility is not yet established. This boolean is required in the filing payload, but uncertainty must **not** block a supported dispute filing. Do not refuse, transfer, or request a statement date merely to determine this separate field. Do not promise immediate credit unless a Rho-Bank journal discrepancy is actually confirmed.
7. **Validate, then file.** Use `scripts/validate_debit_dispute.py` with live lookup results. When its output is valid, unlock `file_debit_card_transaction_dispute_6281` and call it with the returned `filing_payload`. The filing must use `atm_cash_discrepancy`, `atm_withdrawal`, the matched identifiers, and `keep_active`. Do not wait for a favorable journal result or for a statement date.
8. **Post-filing action and customer update.** `card_action` is filing metadata. For this category, keep the card active; do not freeze or reissue it absent another dispute requiring that action. Preserve the returned dispute identifier and communicate the investigation expectation, affidavit requirement if applicable, and whether provisional-credit eligibility was established. A provisional credit can be reversed after an adverse finding with at least three business days' written notice.

## Required filing payload

Call `file_debit_card_transaction_dispute_6281` using current interaction and tool results, with every field below:

```json
{
  "transaction_id": "matched account-history transaction ID",
  "account_id": "selected open checking account ID",
  "card_id": "selected linked debit-card ID",
  "user_id": "verified customer ID",
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

The literals demonstrate schema and permitted values only; never reuse identifiers, dates, amounts, or customer facts from another case. `police_report_filed` is normally `false` for this non-fraud dispute. `provisional_credit_eligible` must always be present and boolean, including when timing evidence is unavailable.

## Validator interface

Run the packaged helper through the supported script runtime with one JSON object. It reads JSON from stdin and emits JSON to stdout; it performs no banking action. Its input schema is documented in the script module docstring. Supply live `today`, verification/logging flags, user ID, selected account/card/transaction, prior disputes, ATM facts, optional statement date, and dispute facts. The output contains:

- `valid`: whether filing prerequisites and required fields passed;
- `errors` and `warnings`;
- `filing_payload`: complete payload when valid;
- `provisional_credit_eligible`: required boolean determination;
- `affidavit_required`, timing details, and `post_filing_card_action`.

Reconcile errors before filing. A missing `statement_date` is a warning and produces `false` provisional-credit eligibility; it is never a filing error.

## Do not file when

Do not file if identity/authority/ownership is not verified; the account is not an OPEN checking account; the card, withdrawal, or facts cannot be matched; the transaction is over 60 days old; the dollar rules fail; the applicable dispute limit is reached; or required filing facts are absent. Ask a focused question for a genuinely missing filing fact. Do not invent account status, a tier, journal result, holds, statement date, or provisional-credit eligibility evidence.
