---
name: debit-card-dispute-filing
description: Verify a customer, collect required facts, validate account/card/transaction records, and file eligible debit-card transaction disputes under Regulation E. Use for debit-card duplicate, amount-error, merchant, ATM, unauthorized, and fraud claims.
---

# Debit Card Dispute Filing

Use this Skill only for debit-card/EFT disputes. Treat a customer description as a lead, not as a transaction identifier. Use only the normal banking tools made available by the runtime; never invent a tool or claim that an action or credit occurred unless its tool response confirms it. Do not reveal sensitive card data returned by a lookup (beyond an appropriate last four digits).

## 1. Verify and obtain a complete report

1. Identify the customer by registered name or email and retrieve the user record.
2. Before any account, card, transaction, dispute, or card-status action, have the customer confirm at least two of registered date of birth, email, phone number, or address. Compare them to the record. Once two match, get the current time and call `log_verification` with the complete returned identity record and that time. If verification is incomplete or fails, stop and request it.
3. For **each** proposed claim obtain the merchant/ATM, transaction date, statement amount, amount contested, explanation, and discovery date. For unauthorized activity, explain liability before filing: reported within 2 business days of the statement has a maximum $50 liability; within 60 days has a maximum $500 liability; after 60 days liability may be unlimited and funds may not be recoverable.
4. Obtain the following facts, without guessing:
   - Unauthorized claim: whether fraud is suspected; physical/in-store versus online/phone/card-not-present use; whether the card remains in possession; and PIN status: `yes_shared`, `yes_observed`, `no`, or `unknown`.
   - Non-fraud merchant claim: whether the customer contacted the merchant.
   - ATM claim: whether it was a Rho-Bank or third-party ATM.
   - All claims: agreement to provide a written statement. Agreement to use the conversation is sufficient.
   - Fraud over $500: whether a police report was filed; recommend one if not.
5. Ask whether an in-store purchase used PIN or signature if transaction data does not establish it. Reuse a card-wide possession/PIN answer or written-statement agreement only when the customer clearly made it applicable to the additional claim.

Ask a focused follow-up for missing information before filing that particular claim. Do not treat a merchant name alone as proof of transaction type.

## 2. Validate banking records after verification

1. Retrieve accounts using `get_all_user_accounts_by_user_id_3847(user_id)`. Select the checking account identified by the customer/card. It must be `OPEN` and customer-owned. Review any returned standing/hold/restriction data; a reported hold or restriction prevents required provisional-credit eligibility.
2. Retrieve its cards with `get_debit_cards_by_account_id_7823(account_id)`. Confirm the specified card belongs to the user and checking account and is current/appropriate, rather than a closed historical card with the same last four digits.
3. Retrieve transactions with `get_bank_account_transactions_9173(account_id)`. Match a claim by date, description, debit amount, debit-card/EFT nature, and status, then use the returned `transaction_id`. Do not file an unmatched transaction, a credit, a claim under $1.00, an unsupported transaction type, or a transaction more than 60 days old.
4. For duplicates, find every matching posting and file the earliest/first duplicate as required. Do not confuse the valid original with an erroneous duplicate; clarify if the records cannot distinguish them.
5. Retrieve history with `get_debit_dispute_status_7483(user_id)`. Count only `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED` disputes for the **selected account**. The per-account caps are Entry 2, Mid 3, Premium 4, and Elite 5. Never aggregate accounts. If a record does not expose a standard tier, do not assume a higher cap: filing up to the lowest cap (2) is safe; obtain a tier or stop before exceeding it.

## 3. Classify and calculate

Use exactly one category:

- `unauthorized_transaction`: not authorized, but fraud is not suspected.
- `card_present_fraud`: suspected fraudulent physical/card-present use.
- `card_not_present_fraud`: suspected fraudulent online or phone/card-not-present use.
- `atm_cash_discrepancy`, `atm_deposit_not_credited`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation`: use the matching customer circumstance.

Use exactly one transaction type: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`. For example, an EveryonePay-style transfer is `person_to_person` when that is what occurred, even if fraud used card details.

Set `card_action` metadata as follows: `card_present_fraud` or `card_not_present_fraud` → `close_and_reissue`; `unauthorized_transaction` → `freeze_pending_investigation`; all other categories → `keep_active`.

Set `provisional_credit_eligible` true only when reporting is timely within 60 days of the statement, the category is `unauthorized_transaction`, `card_present_fraud`, `card_not_present_fraud`, `atm_cash_discrepancy`, or `duplicate_charge`, there is a written statement, and the checking account is OPEN without a hold/restriction. Set it false for the other categories, voluntary PIN sharing, a card-not-present claim on an account under 30 days, or a non-fraud claim without merchant contact. Do not say credit was issued merely because it is eligible; the filing response controls that statement.

If the current filing-tool schema requires `customer_max_liability_amount`, use `0` for a non-unauthorized merchant/processing error. For unauthorized/fraud claims, use the applicable timely-reporting maximum, capped at the disputed amount: $50 within 2 business days of the statement, $500 within 60 days, or `-1` after 60 days. Obtain a needed statement-date fact rather than inventing it.

## 4. File and perform the card action

Call `file_debit_card_transaction_dispute_6281` once per validated transaction. Include every required field in the tool's current schema. The base filing shape is:

```json
{
  "transaction_id": "matched ID",
  "account_id": "open checking account ID",
  "card_id": "linked card ID",
  "user_id": "verified user ID",
  "dispute_category": "allowed category",
  "transaction_date": "MM/DD/YYYY",
  "discovery_date": "MM/DD/YYYY",
  "disputed_amount": 1.0,
  "transaction_type": "allowed type",
  "card_in_possession": true,
  "pin_compromised": "no",
  "contacted_merchant": false,
  "police_report_filed": false,
  "written_statement_provided": true,
  "provisional_credit_eligible": false,
  "card_action": "keep_active"
}
```

Some runtime schemas also require `customer_max_liability_amount`; supply it when declared. Check each response. Never retry a result that is unknown.

For multiple successful claims on one card, preserve each claim's own metadata. Then perform the single most severe **actual** action: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`. Use a declared normal card-action tool, and report only what succeeds. If a required close/reissue tool is not supplied, do not invent one; transfer with `specialized_department_required` and clearly state that the specialist must complete the required card action.

## 5. Closeout

State the claims actually filed, amounts, investigation next step, card action actually completed, and any documentation or provisional-credit limitation. For follow-up, use `get_debit_dispute_status_7483`. Escalate a regulatory timing issue: provisional credit later than 10 days (20 for a new account), or investigation later than 45 days (90 for international/foreign POS or new-account cases).

## Optional local plan validation

Run `scripts/validate_dispute_plan.py` with JSON on stdin; it emits JSON on stdout. It performs no lookup or banking action. Input has `identity_verified`, an `account` object (`status`, `tier` or `max_open_disputes`, `has_holds_or_restrictions`, `open_dispute_count`), and claim objects with `transaction_id`, `transaction_age_days`, `amount`, `category`, `transaction_type`, `written_statement_provided`, `timely_statement_reporting`, `contacted_merchant`, `pin_compromised`, and `account_age_days`. Its output has `valid` plus per-claim errors, provisional-credit eligibility, and card-action metadata. A valid result does not replace record validation or tool calls.
