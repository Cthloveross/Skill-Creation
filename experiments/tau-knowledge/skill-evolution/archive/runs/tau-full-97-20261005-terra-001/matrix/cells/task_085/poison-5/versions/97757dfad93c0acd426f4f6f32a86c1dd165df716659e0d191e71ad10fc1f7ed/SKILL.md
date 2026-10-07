---
name: debit-card-dispute-intake
version: 1.0.0
description: Validate, prepare, file, and follow up debit-card transaction disputes, including ATM cash discrepancies, Regulation E disclosures, provisional-credit decisions, and card-action coordination.
---

# Debit Card Dispute Intake and Filing

Use this Skill when a verified customer asks to dispute a debit-card transaction, including unauthorized activity, merchant errors, duplicate charges, incorrect amounts, recurring charges, and ATM withdrawal or deposit errors. It supports one or more disputes on the same card; handle them one at a time while coordinating one final card action per card.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Safety and scope

- Do not file, freeze, close, reissue, or otherwise change a card until all applicable prerequisites below have been verified.
- Scripts in this package only evaluate supplied facts and prepare recommendations. They never perform banking actions.
- Use normal banking tools for all account, dispute, and card actions. Do not treat a recommendation from the script as a completed action.
- If supplied facts are missing, conflicting, or cannot be matched to a specific account, card, and transaction, stop preparation and request or retrieve the missing information.

## Required workflow

### 1. Verify and record identity

1. Identify the customer and retrieve their profile using the available customer-lookup tool.
2. Confirm at least two of the four identity fields: date of birth, email, phone number, and mailing address.
3. Retrieve the current time and call `log_verification` with the complete profile fields and verification timestamp after successful verification.
4. Confirm that the customer is authorized for the account and that the selected debit card belongs to the customer.

### 2. Give the required timing disclosure

Before filing an unauthorized-activity complaint, explain the customer’s maximum possible liability based on when they noticed/reported the activity relative to the statement:

- Within 2 business days: $50 maximum liability.
- Within 60 days: $500 maximum liability.
- After 60 days: unlimited liability; recovery may not be available.

Record the transaction date and the date the customer first noticed the problem. Do not infer either date.

### 3. Collect facts and classify the claim

Retrieve all customer accounts with `get_all_user_accounts_by_user_id_3847`. Select an OPEN checking account matching the customer’s stated account. Retrieve its debit cards with `get_debit_cards_by_account_id_7823` and select the applicable current card. Retrieve transactions with `get_bank_account_transactions_9173(account_id)` and match the claimed item by transaction ID, date, amount, and description.

For every claim collect:

- Transaction ID, date, posted/pending status, description, and full transaction amount.
- Discovery date and disputed amount.
- What happened, merchant/ATM name, and whether the transaction was physical, online/phone, ATM withdrawal, ATM deposit, recurring, or P2P.
- Whether the customer still has the physical card.
- PIN status: `yes_shared`, `yes_observed`, `no`, or `unknown`.
- Whether the customer attempted resolution directly with the merchant or relevant operator. Record this for all non-fraud claims.
- Whether fraud is suspected. If fraud above $500 is alleged, ask whether a police report was filed and recommend one if it was not.
- Whether the customer agrees to provide a written statement; the conversation can serve as the statement only if the customer agrees.

Use exactly one filing category:

- `unauthorized_transaction` only when the customer did not authorize it but fraud is **not** suspected.
- `card_present_fraud` for suspected fraud involving physical/in-store card use.
- `card_not_present_fraud` for suspected online or phone fraud.
- `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation` when applicable.

Use exactly one transaction type: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.

For duplicates, identify all matching duplicate transactions and dispute the earliest transaction first. Do not substitute a later duplicate merely because it is more recent.

### 4. Verify filing eligibility

Before filing each item, verify all of the following:

1. Identity and authority have been verified and recorded.
2. The matched transaction is at least $1.00 and the disputed amount does not exceed the transaction amount.
3. The transaction is no more than 60 days old under the dispute policy.
4. The card is linked to an OPEN checking account.
5. Open disputes for this **account** are below the account-tier limit: Entry 2, Mid 3, Premium 4, Elite 5. Retrieve history with `get_debit_dispute_status_7483(user_id)` and count only `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED` records for the selected account.
6. All required filing fields have been collected.

A customer’s failure to contact a merchant/operator should be recorded and can prevent required provisional credit for a non-fraud claim. Do not represent it as a substitute for the required factual checks.

### 5. Apply ATM-specific procedures

Ask whether the ATM is Rho-Bank branded or third-party.

**Rho-Bank ATM cash discrepancy**

- Review recent transactions/journal records for the matching withdrawal and compare the journal result with the customer’s claim before filing or recommending immediate credit.
- If the record confirms a discrepancy, recommend immediate provisional credit for the confirmed shortage.
- If it shows the amount was correctly dispensed, explain that the claim cannot be validated from the journal, but the customer may still file a formal dispute.

**Rho-Bank ATM deposit not credited**

- Retrieve and compare relevant deposit envelope/check images with `get_atm_deposit_images_8473` before completing the investigation. Physical verification may take up to 45 days.

**Third-party ATM**

- Submit the claim through the normal chargeback process to the ATM owner/network after filing.
- Explain that investigation may take up to 90 days and qualifying provisional credit is due within 10 business days.
- For an ATM cash-discrepancy amount over $200, tell the customer an Electronic Fund Transfer Error Resolution Affidavit will be emailed to the registered address, must be signed and returned within 10 business days, and that failure to return it may lead to denial. Explain that a false affidavit is a federal offense.

A card retained by a Rho-Bank ATM is not itself a transaction dispute. Offer retrieval within three business days or card replacement; file a dispute only for any separate unauthorized transaction.

### 6. Determine provisional credit

Set `provisional_credit_eligible` to true only when all conditions for required credit are met:

- Timely reporting within 60 days of the statement date;
- Category is `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`;
- A written statement is provided or the customer agreed that the conversation is the written statement; and
- The checking account is OPEN with no hold or restriction.

Do not mark required provisional credit when the customer voluntarily shared a PIN (`yes_shared`), the account is under 30 days old and the claim is card-not-present, or a non-fraud claim lacks prior merchant contact. Other categories are not required-credit categories, though credit may be offered at discretion.

When required, provisional credit is the full disputed amount, reduced by any applicable $50 or $500 late-report liability offset, never exceeding the transaction amount. It is due within 10 business days after filing, or 20 business days for an account open under 30 days. With provisional credit, normal investigation is 45 business days; international, outside-US merchant POS, and new-account investigations may extend to 90 days. For a Rho-Bank ATM cash discrepancy confirmed by the journal, credit is immediate.

### 7. File and act on the card

For each eligible item, call `file_debit_card_transaction_dispute_6281` with exactly these fields:

- `transaction_id`, `account_id`, `card_id`, `user_id`
- `dispute_category`, `transaction_date`, `discovery_date`, `disputed_amount`, `transaction_type`
- `card_in_possession`, `pin_compromised`, `contacted_merchant`, `police_report_filed`
- `written_statement_provided`, `provisional_credit_eligible`, `card_action`

Set the per-dispute `card_action` exactly as follows:

| Category | card_action |
|---|---|
| `card_present_fraud`, `card_not_present_fraud` | `close_and_reissue` |
| `unauthorized_transaction` | `freeze_pending_investigation` |
| all ATM, duplicate, amount, goods/services, and recurring categories | `keep_active` |

File each qualifying claim separately. After all filings for the same card, perform one actual card action using the highest severity recorded for that card: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`. For a freeze, use `freeze_debit_card_3892`; for close/reissue, use the available normal card-management tools. The per-dispute `card_action` metadata must not be overwritten with the combined action.

### 8. Confirm and monitor

Confirm each filed transaction, category, amount, written-statement status, provisional-credit determination, affidavit/document request if applicable, and card action. Explain that a negative investigation can reverse provisional credit only after written notice at least three business days in advance; customers may request supporting documentation.

For later status requests, use `get_debit_dispute_status_7483(user_id)`. Escalate if credit or investigation appears to exceed the applicable 10/20-day, 45-day, or 90-day timeline.

## Deterministic validator

Use `scripts/validate_dispute.py` after gathering live tool results and before any filing. It validates supplied records and builds filing payloads only for claims without blocking errors.

Input JSON schema:

```json
{
  "as_of_date": "MM/DD/YYYY",
  "identity_verified": true,
  "account": {"account_id": "...", "account_type": "checking", "account_class": "MID", "status": "OPEN", "date_opened": "MM/DD/YYYY", "holds_or_restrictions": false},
  "card": {"card_id": "...", "account_id": "...", "user_id": "...", "status": "ACTIVE"},
  "transactions": [{"transaction_id": "...", "account_id": "...", "date": "MM/DD/YYYY", "amount": -100.0, "description": "...", "status": "posted"}],
  "existing_disputes": [{"account_id": "...", "status": "OPEN"}],
  "claims": [{"transaction_id": "...", "dispute_category": "atm_cash_discrepancy", "discovery_date": "MM/DD/YYYY", "disputed_amount": 100.0, "transaction_type": "atm_withdrawal", "card_in_possession": true, "pin_compromised": "no", "contacted_merchant": false, "police_report_filed": false, "written_statement_provided": true, "timely_reporting_within_60_days_of_statement": true, "days_from_statement_discovery": 0, "atm_owner": "RHO_BANK", "atm_journal_result": "confirmed"}]
}
```

`account_class` accepts Entry/Mid/Premium/Elite case-insensitively. `existing_disputes` should contain the full history retrieved for the user. For duplicate claims, optionally include `duplicate_group_transaction_ids`, ordered or unordered; the validator will require the earliest dated transaction. `atm_journal_result` is required for a Rho-Bank ATM cash discrepancy and must be `confirmed`, `correct_amount`, or `unavailable`.

The script emits `{ready, blockers, warnings, filings, card_actions}`. `filings` contains the exact tool payload and computed provisional-credit details for each claim that is ready. Review every blocker and warning, then make live banking-tool calls only when `ready` is true for the intended filing set.

Example execution by the Skill runtime:

```text
run_skill_script(relative_path="scripts/validate_dispute.py", input_json=<assembled live records>)
```
