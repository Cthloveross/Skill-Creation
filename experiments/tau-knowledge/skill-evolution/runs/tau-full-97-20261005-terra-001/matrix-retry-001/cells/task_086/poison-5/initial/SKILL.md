---
name: debit-card-dispute-orchestrator
description: File one or more debit-card transaction disputes safely and consistently. Use when a verified customer reports debit-card purchases, ATM withdrawal/deposit errors, duplicate charges, unauthorized activity, fraud, recurring charges after cancellation, incorrect amounts, or missing goods/services.
---

# Debit Card Dispute Orchestrator

Use this Skill to gather complete evidence, determine eligibility and provisional-credit treatment, file eligible debit disputes, and apply the appropriate card protection action for each affected card.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Required facts and prerequisites

Do not file, freeze, close, reissue, or block payments until all applicable checks below are complete.

1. **Verify identity and authority.** Obtain confirmation of two of the four identity fields (date of birth, email, phone number, address) against the customer record. A name, email lookup, or information already shown in the conversation is not verification by itself. Get the current timestamp and call `log_verification` only after successful confirmation.
2. **Identify the customer and accounts.** Use `get_all_user_accounts_by_user_id_3847`. The disputed account must be a checking account, be OPEN, have no relevant holds/restrictions for provisional-credit purposes, and be owned by the verified customer.
3. **Identify the active card.** For each checking account, use `get_debit_cards_by_account_id_7823`; match the customer-provided last four digits, linked `account_id`, and `user_id`. Record card status and issue date. Do not select a historical closed card merely because its last four digits match.
4. **Find and validate each transaction.** Use `get_bank_account_transactions_9173(account_id)`. Match the transaction by date, amount, description, account, and card/customer facts. Transaction amounts are signed: a debit has a negative amount, so compare the claimed amount to the absolute transaction amount. The transaction must be at least $1.00 and no more than 60 days old at filing. Do not infer a transaction ID from a merchant description alone.
5. **Check dispute capacity per account.** Use `get_debit_dispute_status_7483(user_id)` and count only unresolved/open disputes belonging to the affected `account_id` (for example, OPEN, PENDING_DOCUMENTATION, UNDER_REVIEW, or PROVISIONAL_CREDIT_ISSUED). Limits are per checking account: Entry 2, Mid 3, Premium 4, Elite 5. Determine the tier from returned account class/product data. Green Fee-Free is Entry; Evergreen is Premium. Include all new fileable disputes planned for that account when checking its limit.
6. **Confirm the customer wants each exact disputed amount.** A partial shortage or overcharge is disputed for the shortage/overcharge, not automatically for the entire transaction. The amount must not exceed the underlying transaction amount.
7. **Collect every tool field.** For each issue obtain transaction/discovery dates, category, transaction type, card possession, PIN-compromise value, merchant-contact result, written-statement consent, and police-report result where applicable. Dates must be `MM/DD/YYYY`; a discovery date cannot be in the future relative to the current filing date. Resolve impossible or contradictory dates before filing.

If any prerequisite fails, explain the specific blocker and do not take the associated banking action. If account ownership, identity, transaction matching, or an unsupported action cannot be safely resolved, transfer with the most specific applicable human-agent reason.

## Customer disclosures and fact gathering

Before filing unauthorized/fraud issues, explain the Regulation E liability exposure based on prompt reporting:

- reported within 2 business days: maximum $50 liability;
- reported within 60 days: maximum $500 liability;
- reported after 60 days: potentially unlimited liability and possible loss of funds.

Ask the customer to confirm when they first noticed each issue. For every fraud/unauthorized issue ask:

- “Do you still have your physical debit card in your possession?”
- “Do you believe your PIN may have been compromised?”

Encode the PIN response exactly as `yes_shared`, `yes_observed`, `no`, or `unknown`. Do not translate a vague concern about card skimming into a PIN-compromise value without confirming whether the PIN itself may have been observed or skimmed.

For non-fraud disputes, ask whether the customer tried to resolve the matter directly with the merchant and pass that response as `contacted_merchant`. Ask every customer: “Are you willing to provide a written statement describing what happened? We can use this conversation as your written statement if you agree.” Set `written_statement_provided` to true only on agreement.

For suspected fraud above $500, ask whether a police report was filed. If not, recommend filing one; lack of a report is not by itself a stated filing blocker.

## Classification rules

Use only these exact categories:

- `unauthorized_transaction` only when the customer did not authorize it **and fraud is not suspected** (for example, a family member used it without permission).
- `card_present_fraud` for suspected fraud involving a physical/in-store card-present transaction.
- `card_not_present_fraud` for suspected fraud involving an online or phone/card-not-present transaction.
- `atm_cash_discrepancy` for no cash or the wrong withdrawal amount.
- `atm_deposit_not_credited` for an ATM deposit missing or partially credited.
- `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` when those facts apply.

Use the matching exact transaction type: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.

If the transaction channel is unknown, do not guess between card-present and card-not-present fraud. Obtain the transaction record/details or ask a clarifying question before filing. When duplicates are reported, identify the duplicate group and dispute the earliest transaction, not a later duplicate.

## ATM handling

Determine whether an ATM is Rho-Bank owned or third-party before filing.

- For a **Rho-Bank cash discrepancy**, inspect the associated transaction/journal evidence. If the discrepancy is confirmed, provisional credit is immediate; if records show the correct cash amount, explain that the claim is not validated but the customer may still file a formal dispute.
- For a **Rho-Bank deposit-not-credited** issue, unlock and use `get_atm_deposit_images_8473` to retrieve available envelope/check images and compare them with the claimed deposit. These may take up to 45 days for physical verification.
- For a **third-party ATM** dispute, explain that a chargeback goes to the ATM owner/network, the investigation can take up to 90 days, and qualifying provisional credit remains due within 10 business days. For an ATM cash discrepancy **over $200**, tell the customer an Electronic Fund Transfer Error Resolution Affidavit will be emailed, must be signed and returned within 10 business days, may be required to avoid denial, and that a false affidavit is a federal offense.

A retained card is not itself a transaction dispute unless there are unauthorized transactions too.

## Provisional-credit determination

Set `provisional_credit_eligible` true only when all required conditions are established:

1. timely report within 60 days of the statement date that showed the transaction;
2. category is `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`;
3. written statement is provided; and
4. checking account is OPEN with no holds or restrictions.

Set it false when the category is `goods_services_not_received`, `recurring_charge_after_cancellation`, `atm_deposit_not_credited`, or `incorrect_amount`; when a non-fraud customer did not contact the merchant; when the customer voluntarily shared the PIN; or when an account less than 30 days old has a card-not-present transaction. If a qualifying case lacks statement-date/timeliness information, obtain it before claiming or encoding eligibility.

When required, provisional credit is the full disputed amount, reduced by any applicable $50/$500 late-reporting liability offset, never exceeding the transaction amount. The ordinary deadline is 10 business days, or 20 business days for an account open less than 30 days. With provisional credit, investigation is generally 45 business days and may extend to 90 days for international, non-US merchant POS, or new-account cases. Explain that an adverse finding can reverse credit after at least 3 business days’ written notice.

## Filing and card actions

1. Unlock `file_debit_card_transaction_dispute_6281` and submit one filing per eligible transaction with all 16 required fields. Use the exact selected transaction ID and dates.
2. Record each filing’s `card_action` exactly from this mapping:
   - `card_present_fraud`, `card_not_present_fraud` -> `close_and_reissue`
   - `unauthorized_transaction` -> `freeze_pending_investigation`
   - all ATM, duplicate, incorrect-amount, goods/services, and recurring-cancellation categories -> `keep_active`
3. Do not alter an individual filing’s action because another issue on the same card is more severe. After all successful filings for a card, perform only the most severe actual action once: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`.
4. For `freeze_pending_investigation`, verify the card is ACTIVE and the customer owns it; explain that new and recurring transactions will be declined while pending transactions may still settle; then unlock/use `freeze_debit_card_3892` with the card ID.
5. For `close_and_reissue`, follow the authorized debit-card closure and replacement workflow. Fraud-suspected closure bypasses only the 14-day minimum-age condition; verify the remaining applicable closure conditions, including ownership and pending activity/refunds. Use `close_debit_card_4721` only when its requirements are met and arrange a replacement through the available authorized process. If replacement capability is unavailable, do not imply a reissue occurred; escalate or route it appropriately.
6. For recurring charges after cancellation, offer future protection separately only if requested: explain that a recurring block affects all recurring payments on the card, not one merchant, takes effect within 24 hours, and does not cancel subscriptions. After filing past charges, unlock/use `set_debit_card_recurring_block_7382` with `block_recurring: true` if the verified customer elects it.

Confirm each filed dispute, its next documentation step, expected timeline, and any resulting card action. Never claim an action or credit was completed until its tool result confirms it.

## Planner helper

`scripts/debit_dispute_planner.py` validates normalized, runtime-derived case data and generates safe filing payloads plus per-card final-action recommendations. It does not call banking tools and does not replace transaction matching or customer verification.

Run it by sending JSON on stdin, for example:

```json
{
  "as_of": "MM/DD/YYYY",
  "verified": true,
  "accounts": [{"account_id": "...", "user_id": "...", "account_type": "checking", "status": "OPEN", "tier": "Entry", "has_holds": false, "has_restrictions": false, "date_opened": "MM/DD/YYYY"}],
  "cards": [{"card_id": "...", "account_id": "...", "user_id": "...", "status": "ACTIVE"}],
  "transactions": [{"transaction_id": "...", "account_id": "...", "date": "MM/DD/YYYY", "amount": -10.0, "description": "...", "status": "posted"}],
  "open_disputes": [],
  "disputes": [{"transaction_id": "...", "account_id": "...", "card_id": "...", "user_id": "...", "dispute_category": "incorrect_amount", "transaction_date": "MM/DD/YYYY", "discovery_date": "MM/DD/YYYY", "disputed_amount": 1.0, "transaction_type": "signature_purchase", "card_in_possession": true, "pin_compromised": "no", "contacted_merchant": true, "police_report_filed": false, "written_statement_provided": true, "statement_date": "MM/DD/YYYY"}]
}
```

The script emits `filings` only for cases with no blocking errors, `case_results` explaining blockers/warnings, and `card_actions` containing the single most-severe post-filing action per card. Review its output against live tool results before acting.
