---
name: debit-card-dispute-intake-and-filing
description: Safely intake, validate, file, and follow up on debit-card transaction disputes, including Regulation E provisional-credit assessment, ATM-specific handling, duplicate charges, and required card security actions. Use when a verified customer reports debit-card, ATM, recurring-payment, or debit-card fraud transaction problems.
---

# Debit Card Dispute Intake and Filing

Use this Skill for debit-card transactions only. It supports a multi-transaction, multi-card intake, but never files a claim until the individual claim has all required facts and all filing prerequisites are met.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Safety and scope

- A profile lookup or a customer stating a name is **not** identity verification. Confirm two of the four identity fields (date of birth, email, phone number, address), obtain the current timestamp, then call `log_verification` with every required field before any banking action.
- Verify the customer owns the account and card: the selected card must have the matching `user_id`, be linked to the selected checking account, and the checking account must be OPEN.
- Do not confuse debit disputes with credit-card disputes. Use debit-card account, card, transaction, and debit-dispute tools only.
- Do not invent transaction IDs, card IDs, transaction dates, account tiers, statement dates, merchant-contact attempts, or customer answers. Ask for missing information one claim at a time.
- A recurring-payment block prevents future recurring payments but does not dispute past charges or cancel a merchant subscription. If requested, file eligible past-charge disputes first, then separately offer the recurring block after explaining it blocks **all** recurring payments on the card.

## Required discovery and pre-filing sequence

1. **Verify identity and authority.** Complete the two-field verification and audit log described above. Obtain the user ID from the verified profile.
2. **Retrieve records.** Unlock and use, as needed:
   - `get_all_user_accounts_by_user_id_3847(user_id)` to identify checking accounts, account class/tier, status, opening date, and restrictions/holds if returned.
   - `get_debit_cards_by_account_id_7823(account_id)` for each relevant OPEN checking account. Match the card’s last four digits, `user_id`, `account_id`, and current status.
   - `get_bank_account_transactions_9173(account_id)` to find the actual transaction record and its `transaction_id`, date, amount, description, type, and status.
   - `get_debit_dispute_status_7483(user_id)` to count currently open debit disputes **for that account**.
3. **Collect claim-specific facts.** For every transaction, collect: what happened; transaction date and transaction record; discovery date; disputed amount; transaction type; and agreement to use the conversation as the written statement. For unauthorized reports also collect whether fraud is suspected, whether the card is possessed, whether the PIN was compromised, and whether it was physical/in-store or online/phone. For non-fraud claims, collect whether the customer contacted the merchant.
4. **Explain liability before proceeding with unauthorized activity.** Based on when the customer noticed/reported the activity relative to the statement, explain: within 2 business days, maximum liability $50; within 60 days, maximum liability $500; after 60 days, potentially unlimited liability and recovery may be unavailable. Record the statement date or another supported reporting-timeliness basis; do not assume it from transaction date.
5. **Check filing eligibility for each individual claim.** The transaction must be at least $1.00, within 60 calendar days, on an OPEN checking account linked to the debit card, and within the account’s open-dispute maximum: Entry 2, Mid 3, Premium 4, Elite 5. The limit is per account, not per customer. Non-fraud disputes require an attempted merchant contact. Stop and explain the unmet requirement rather than filing an ineligible claim.
6. **Duplicates.** When there are multiple duplicate charges, dispute the earliest (first) transaction only. Do not file later copies as duplicate claims.
7. **ATM claims.** Determine whether the ATM is Rho-Bank owned or third-party. For a Rho-Bank ATM cash discrepancy, review the relevant checking transactions/journal evidence; if confirmed, provisional credit is immediate. For Rho-Bank deposit-not-credited claims, retrieve images with `get_atm_deposit_images_8473`. For third-party ATM claims, explain the chargeback/network process and possible 90-day investigation. A third-party ATM cash discrepancy greater than $200 requires an Electronic Fund Transfer Error Resolution Affidavit: it is emailed to the registered address, must be returned within 10 business days, failure may cause denial, and false signing is a federal offense.
8. **File only complete, eligible claims.** Unlock `file_debit_card_transaction_dispute_6281`, construct arguments exactly as returned by the planner or manually validated below, and invoke it once per eligible transaction.
9. **Perform the actual card action after all claims on that card have been filed.** The filing parameter records each claim’s own mapped action. For the actual card action, execute only the single most severe action for that card: close/reissue > freeze > keep active. Re-check ownership and action-specific card status immediately before acting.

## Classification and filing fields

Choose exactly one category:

- `unauthorized_transaction`: not authorized, but fraud is not suspected (for example, a family member used it without permission).
- `card_present_fraud`: suspected fraud where the physical card was used.
- `card_not_present_fraud`: suspected fraud for online or phone/card-not-present activity.
- `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` when those facts apply.

Use one transaction type: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.

Map each filing’s `card_action` exactly:

| Category | Filing card_action |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| All other supported categories | `keep_active` |

A filing requires these fields: `transaction_id`, `account_id`, `card_id`, `user_id`, `dispute_category`, `transaction_date` (MM/DD/YYYY), `discovery_date` (MM/DD/YYYY), `disputed_amount` (float), `transaction_type`, `card_in_possession` (boolean), `pin_compromised` (`yes_shared`, `yes_observed`, `no`, or `unknown`), `contacted_merchant` (boolean), `police_report_filed` (boolean), `written_statement_provided` (boolean), `provisional_credit_eligible` (boolean), and `card_action`.

For suspected fraud over $500, ask whether a police report was filed and recommend one if it was not. This is not stated as a filing block.

## Provisional-credit determination

Set `provisional_credit_eligible` true only when all required conditions are supported: timely reporting within 60 days of the statement date, one of `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`, a written statement, and an OPEN unrestricted checking account. Set it false if any mandatory condition is absent. It is not required for goods/services not received, recurring-after-cancellation, ATM deposit not credited, or incorrect amount; when a non-fraud customer has not contacted the merchant; when the customer voluntarily shared the PIN; or for a card-not-present transaction on an account opened fewer than 30 days ago.

When required, credit is normally the full disputed amount, not more than the transaction amount, subject to any applicable late-reporting liability offset. Required timing is within 10 business days, or 20 business days for a new account. With provisional credit, investigation is generally 45 business days and can be 90 days for international transactions, merchant POS outside the US, or new accounts. Before a reversal after an adverse finding, the customer receives written notice at least 3 business days in advance.

## Card-action execution

- For `freeze_pending_investigation`, unlock and call `freeze_debit_card_3892(card_id)` only if the verified owner’s card is currently ACTIVE. Tell the customer that new and recurring charges will decline while frozen, while already authorized pending transactions may still process.
- For `close_and_reissue`, first check the closure prerequisites. The card must belong to the verified customer and normally be ACTIVE or PENDING, with no pending transactions/refunds. A fraud-suspected reason bypasses the 14-day minimum card-age requirement. Unlock and call `close_debit_card_4721(card_id, reason='fraud_suspected')` where the security facts support it. A closed card cannot be reactivated; arrange replacement only through an available approved replacement workflow. Do not claim a replacement was ordered if no such tool/action is available.
- `keep_active` needs no card-status change. If a required freeze or closure prerequisite is not met, document and escalate/seek the approved resolution; do not silently omit the action.

## Planner script

`scripts/plan_debit_disputes.py` performs deterministic eligibility checks, category/action validation, dispute-limit counts, duplicate selection, liability timing, and provisional-credit recommendations. It does not call bank tools and does not itself file, freeze, close, credit, or block anything.

Run it by sending JSON on stdin and reading JSON from stdout. Example shape (replace all placeholder values with runtime records):

```json
{
  "as_of_date": "MM/DD/YYYY",
  "identity_verified": true,
  "user_id": "<verified-user-id>",
  "accounts": [{"account_id":"<id>","account_type":"checking","account_class":"Entry","status":"OPEN","date_opened":"MM/DD/YYYY","has_holds_or_restrictions":false}],
  "cards": [{"card_id":"<id>","account_id":"<id>","user_id":"<verified-user-id>","status":"ACTIVE"}],
  "transactions": [{"transaction_id":"<id>","account_id":"<id>","date":"MM/DD/YYYY","amount":-10.0,"type":"debit_card_purchase","status":"posted"}],
  "existing_disputes": [],
  "claims": [{"transaction_id":"<id>","account_id":"<id>","card_id":"<id>","dispute_category":"incorrect_amount","transaction_type":"online_purchase","discovery_date":"MM/DD/YYYY","disputed_amount":10.0,"card_in_possession":true,"pin_compromised":"no","contacted_merchant":true,"police_report_filed":false,"written_statement_provided":true,"statement_date":"MM/DD/YYYY"}]
}
```

Validate the resulting `plans`: file only entries with `eligible_to_file: true`; resolve every listed `blocking_reasons` first. Treat `warnings` and `required_followups` as required customer communications or operational follow-up. The script intentionally reports unknown/missing data rather than guessing.
