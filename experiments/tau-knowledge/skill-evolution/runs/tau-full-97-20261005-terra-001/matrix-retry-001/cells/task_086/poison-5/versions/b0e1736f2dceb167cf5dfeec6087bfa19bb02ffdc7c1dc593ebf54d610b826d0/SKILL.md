---
name: debit-card-dispute-orchestrator
description: Safely gather, validate, and file one or more debit-card transaction disputes, including ATM errors, merchant disputes, duplicate charges, incorrect amounts, and fraud. Use when a verified customer asks to dispute debit-card activity.
---

# Debit Card Dispute Orchestrator

Use this Skill to verify eligibility, identify the correct checking account/card/transaction, gather all required filing facts, submit eligible debit-card disputes, and perform the required card protection action.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Required prerequisites

Do not file a dispute or perform a card action until the relevant checks are complete.

1. **Verify customer identity and authority.** Confirm two of date of birth, email, phone number, or address against the customer record. A lookup result, name, or identifier alone is not verification. After successful confirmation, obtain the current timestamp and call `log_verification`.
2. **Find the checking account.** Use `get_all_user_accounts_by_user_id_3847`. The disputed account must be owned by the verified customer, be a checking account, and be OPEN. Identify holds/restrictions when assessing provisional credit.
3. **Find the card.** Use `get_debit_cards_by_account_id_7823` for each affected checking account. Match the card's last four digits, `account_id`, and `user_id`; do not select an old closed card.
4. **Find the transaction.** Use `get_bank_account_transactions_9173(account_id)`. Match transaction ID, account, date, amount, and description to the claim. Debits have negative amounts, so compare a claimed amount to the absolute transaction amount. It must be at least $1.00, within 60 days of filing, and the disputed amount cannot exceed the underlying transaction amount.
5. **Check open-dispute capacity.** Use `get_debit_dispute_status_7483(user_id)`. Count unresolved disputes for each affected account, including new filings planned for it. Limits per account are Entry 2, Mid 3, Premium 4, Elite 5. Green Fee-Free is Entry and Evergreen is Premium.
6. **Confirm partial amounts.** File only the confirmed shortage, missing deposit portion, or overcharge when the customer selected a partial amount.
7. **Collect tool fields.** Each filing requires dates, category, transaction type, card possession, PIN status, merchant-contact response, police-report response, written-statement response, provisional-credit boolean, and card action. Dates use `MM/DD/YYYY`; do not use a discovery date in the future.

If account ownership, identity, transaction matching, a required filing field, or eligibility cannot be safely established, do not perform that specific action. Explain the blocker and transfer with the most specific applicable reason if it cannot be resolved.

## Required disclosures and fact gathering

Before filing unauthorized or suspected-fraud claims, disclose Regulation E liability exposure:

- reported within 2 business days: maximum $50 liability;
- reported within 60 days: maximum $500 liability;
- reported after 60 days: potentially unlimited liability and possible loss of recovery.

For fraud/unauthorized claims, ask whether the customer still has the physical card and whether their PIN was compromised. Encode PIN status only as `yes_shared`, `yes_observed`, `no`, or `unknown`. Do not infer a PIN compromise merely from suspected card skimming.

For non-fraud claims, ask whether the customer attempted to resolve the issue directly with the merchant or relevant operator and record the answer in `contacted_merchant`. This response is a required filing fact, not a universal prerequisite to filing. In particular, do not block a third-party ATM cash-discrepancy filing merely because the customer has not contacted the ATM owner/operator.

Ask every customer: “Are you willing to provide a written statement describing what happened? We can use this conversation as your written statement if you agree.” Set `written_statement_provided` to true only on agreement.

For suspected fraud above $500, ask about a police report and recommend one if none was filed. A missing police report is not itself a stated filing blocker.

## Classification

Use exactly one permitted category:

- `unauthorized_transaction`: unauthorized activity where fraud is **not** suspected.
- `card_present_fraud`: suspected fraud in an in-person/physical card-present channel.
- `card_not_present_fraud`: suspected fraud in an online or phone/card-not-present channel.
- `atm_cash_discrepancy`: no cash or a wrong ATM withdrawal amount.
- `atm_deposit_not_credited`: an ATM deposit that was not credited or only partly credited.
- `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation`: use when their facts apply.

Use exactly one transaction type: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.

Do not guess between `card_present_fraud` and `card_not_present_fraud`. If a suspected-fraud transaction channel is unknown, obtain transaction detail or customer confirmation before filing it. For duplicate claims, dispute the earliest transaction in the duplicate group.

## ATM-specific procedure

Determine whether the ATM is Rho-Bank-owned or third party.

- **Rho-Bank cash discrepancy:** inspect relevant transaction/journal evidence. If confirmed, provisional credit is immediate. If journal evidence shows correct cash, explain the claim is not validated but the customer may still formally dispute it.
- **Rho-Bank deposit not credited:** use `get_atm_deposit_images_8473` to retrieve and compare available envelope/check images. Physical verification can take up to 45 days.
- **Third-party ATM:** explain that a chargeback request is sent to the ATM owner/network and investigation may take up to 90 days. For a cash discrepancy over $200, tell the customer that an Electronic Fund Transfer Error Resolution Affidavit will be emailed, must be returned within 10 business days, may be needed to avoid denial, and false signing is a federal offense.

## Provisional-credit field

The filing tool requires a boolean `provisional_credit_eligible`. Required provisional credit is established only when all of these are known:

1. reporting was within 60 days of the statement date showing the transaction;
2. the category is `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`;
3. a written statement was provided; and
4. the checking account is OPEN and has no holds or restrictions.

Set the boolean to `false` when credit is not required, including the excluded categories (`goods_services_not_received`, `recurring_charge_after_cancellation`, `atm_deposit_not_credited`, `incorrect_amount`), voluntary PIN sharing, a non-fraud claim with no merchant contact, or the stated new-account card-not-present exclusion.

A missing statement date means mandatory provisional-credit eligibility has **not** been established. It does not prevent filing an otherwise eligible dispute, and it does not justify inventing a statement date or claiming that credit is required. Because the filing interface requires a boolean, submit `provisional_credit_eligible: false` in that case, clearly document that statement-date timeliness remains unconfirmed, and arrange any required follow-up or discretionary review. Do not block a valid ATM discrepancy solely for missing statement-date information.

When required, provisional credit is the full disputed amount subject to applicable liability offset and cannot exceed the transaction amount. Ordinary timing is 10 business days, or 20 for accounts open less than 30 days. Explain that an adverse finding can reverse provisional credit after at least 3 business days' written notice.

## Filing and card actions

1. Unlock `file_debit_card_transaction_dispute_6281` and file one complete payload per eligible transaction.
2. Use the selected transaction ID and the exact validated account, card, user, dates, and amount.
3. Set the filing-level `card_action` exactly as follows:
   - `card_present_fraud`, `card_not_present_fraud` → `close_and_reissue`
   - `unauthorized_transaction` → `freeze_pending_investigation`
   - all other permitted categories → `keep_active`
4. After all successful filings for one card, perform only its most severe actual action once: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`. Do not modify an individual filing's action due to another filing.
5. Before freezing, confirm the customer owns an ACTIVE card and explain that new and recurring transactions will decline while pending transactions may still settle. Unlock and use `freeze_debit_card_3892`.
6. For close-and-reissue, follow the debit-card closure/replacement requirements. Fraud bypasses only the minimum card-age requirement; ownership and pending activity/refund conditions still apply. Do not claim replacement completion without a confirmed authorized tool result.
7. For post-cancellation recurring charges, offer a future recurring block only if requested. Explain it blocks all recurring payments, takes effect within 24 hours, and does not cancel subscriptions. Then use `set_debit_card_recurring_block_7382` only after filing the past-charge dispute.

Confirm each successful filing, next documentation step, applicable timeframes, and actual completed card action. Never claim a filing, credit, freeze, closure, or replacement was completed unless the tool result confirms it.

## Planner helper

`scripts/debit_dispute_planner.py` validates normalized runtime-derived data and produces tool-ready payloads. It does not verify customers, retrieve records, call banking tools, or replace review of live results.

Send one JSON object on stdin. Required top-level fields are `as_of` (`MM/DD/YYYY`), `verified` (boolean), `accounts`, `cards`, `transactions`, `open_disputes`, and `disputes`. Each dispute supplies the filing fields plus optional `statement_date`, `timely_reporting_within_60_days_of_statement`, `atm_owner`, and `duplicate_group`.

Example invocation input:

```json
{
  "as_of": "MM/DD/YYYY",
  "verified": true,
  "accounts": [{"account_id": "...", "user_id": "...", "account_type": "checking", "status": "OPEN", "tier": "Entry", "has_holds": false, "has_restrictions": false}],
  "cards": [{"card_id": "...", "account_id": "...", "user_id": "...", "status": "ACTIVE"}],
  "transactions": [{"transaction_id": "...", "account_id": "...", "date": "MM/DD/YYYY", "amount": -100.0}],
  "open_disputes": [],
  "disputes": [{"transaction_id": "...", "account_id": "...", "card_id": "...", "user_id": "...", "dispute_category": "atm_cash_discrepancy", "transaction_date": "MM/DD/YYYY", "discovery_date": "MM/DD/YYYY", "disputed_amount": 1.0, "transaction_type": "atm_withdrawal", "card_in_possession": true, "pin_compromised": "no", "contacted_merchant": false, "police_report_filed": false, "written_statement_provided": true}]
}
```

It emits JSON containing `filings`, `case_results`, and `card_actions`. A case with unavailable statement-date timeliness remains fileable when all filing prerequisites are met; its payload uses `provisional_credit_eligible: false` and its result includes a warning that mandatory eligibility is unconfirmed.