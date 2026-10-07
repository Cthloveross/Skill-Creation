---
name: debit-card-dispute-intake-and-filing
description: Safely verify, validate, file, and follow up on one or more debit-card transaction disputes under Regulation E, including provisional-credit assessment and the single most-severe card action per card.
---

# Debit-card dispute intake and filing

Use this Skill for a customer who asks to dispute debit-card purchases, ATM activity, recurring payments, or debit-card-funded P2P activity. Scripts only validate data and recommend calls. The executor must make all banking calls using normal banking tools.

## 1. Explain rights and collect a complete claim

Before submitting a dispute, tell the customer that unauthorized-transaction liability is at most $50 when reported within two business days of the statement, at most $500 when reported within 60 days, and may be unlimited after 60 days. For **each** transaction collect:

- merchant/ATM/recipient, date, posted amount, amount claimed, why it is wrong, and date first noticed;
- channel (PIN store, signature store, online/phone, ATM withdrawal/deposit, recurring, or P2P); fraud suspicion and, if fraud, whether it was physical or card-not-present;
- whether the customer has the physical card and one PIN value: `yes_shared`, `yes_observed`, `no`, or `unknown`;
- merchant-contact result for a non-fraud merchant claim; ATM owner for an ATM claim;
- police-report status for fraud over $500 (recommend a report if absent, but do not make it a filing blocker); and
- consent to use the conversation as the written statement.

For duplicate entries, locate every matching posted entry and file only against the earliest transaction. Do not dispute both copies merely because both appear in history.

## 2. Verify and retrieve authoritative data

1. Look up the customer and compare at least two of DOB, email, phone, and address. Obtain the current time and call `log_verification` with the retrieved profile after success.
2. Unlock and call `get_all_user_accounts_by_user_id_3847`. Only an OPEN checking account can support this dispute. Record account ID, account tier, opening date, and any hold/restriction. Tool displays may name the checking type `class` and product/tier `level`; do not mistake the checking type for a tier.
3. Unlock and call `get_debit_cards_by_account_id_7823` for every claimed account. Match user, account, card ending, and status.
4. Unlock and call `get_bank_account_transactions_9173` for every claimed account. Match an exact posted debit by description, date, and absolute amount. Retain its transaction ID. Do not use credit-card transaction history for a debit-card dispute.
5. Unlock and call `get_debit_dispute_status_7483` once. Count only `OPEN`, `PENDING_DOCUMENTATION`, `UNDER_REVIEW`, and `PROVISIONAL_CREDIT_ISSUED` as open, separately for each account.

The account maximum is Entry 2, Mid 3, Premium 4, Elite 5. Never submit more claims than remaining capacity. If the retrieved product label does not state one of these tiers and no authoritative tier mapping is available, use the lowest published maximum (2) as a conservative ceiling rather than assuming a higher one. Explain any capacity-blocked claims and do not submit them until a slot opens. When several requested claims compete for a limited number of slots and the customer has not prioritized them, submit the oldest eligible transaction first (it is closest to the 60-day filing cutoff), then explain which remaining claims are blocked. This is an execution-order safeguard, not a reclassification of claims.

Reject or pause a claim if its live transaction is not found, is below $1, is more than 60 calendar days old, is not tied to the verified customer/card/open checking account, or required facts are missing. Do not invent IDs, statement dates, PIN status, account tier, or whether a card has holds.

## 3. Classify each validated claim

Use exactly one category:

- suspected fraud: `card_present_fraud` for physical/in-store use, `card_not_present_fraud` for online, phone, or card-not-present use;
- unauthorized but not suspected fraud: `unauthorized_transaction`;
- ATM error: `atm_cash_discrepancy` or `atm_deposit_not_credited`;
- otherwise: `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, or `recurring_charge_after_cancellation`.

Transaction types are exactly `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`. A P2P fraud claim is normally `card_not_present_fraud` with `person_to_person`. For incorrect amount, dispute the error portion, not automatically the whole posted amount.

Metadata card actions are: fraud categories → `close_and_reissue`; `unauthorized_transaction` → `freeze_pending_investigation`; all other categories → `keep_active`.

## 4. Provisional credit and submission

Required provisional credit requires all of: reporting within 60 days of the statement, category `unauthorized_transaction`, either fraud category, `atm_cash_discrepancy`, or `duplicate_charge`; written statement; and an OPEN account without holds/restrictions. It is not required for the other categories, a non-fraud claim where merchant was not contacted, a voluntarily shared PIN, or a card-not-present claim on an account open under 30 days. Required credit is the full disputed amount, subject to applicable late-report liability offset. Record `timely_reporting_confirmed` only after establishing reporting was within 60 days of the statement. A statement date is preferred. If the customer first noticed the item while reviewing that statement and reports it within 60 days of that discovery, the statement necessarily predates discovery, so this may establish the 60-day condition; record that rationale. Otherwise, an unknown date is not proof of eligibility. If the exact liability tier cannot be established, use the full disputed amount as a conservative maximum in the filing field rather than inventing a $50 or $500 tier.

Use `scripts/dispute_plan.py` with normalized live facts to validate capacity, payloads, provisional-credit reasoning, and the required `customer_max_liability_amount`. For every `eligible_to_file` result, unlock and call `file_debit_card_transaction_dispute_6281` exactly once with `filing_payload`. If a result is indeterminate, do not retry; check dispute status first.

## 5. Security action after filing all claims

Group **successful** filings by card. Carry each filing's own metadata, but act once per card using `close_and_reissue` > `freeze_pending_investigation` > `keep_active`.

- Keep active: no tool call.
- Freeze: verify the card is ACTIVE and owned by the verified customer, then unlock/call `freeze_debit_card_3892`.
- Close/reissue: obtain authorization, verify ownership and ACTIVE/PENDING status, and check pending transactions/refunds. Fraud bypasses only the 14-day age rule. If eligible, unlock/call `close_debit_card_4721` with `reason: fraud_suspected`. A close is permanent; use the standard ordering process for a replacement if no reissue tool is supplied.

Confirm filed and capacity-blocked claims, card action, credit eligibility/timing (10 business days, 20 for a new account), and the 45-day investigation timeline (90 days for international/POS outside US/new accounts). Explain reversal notice is at least three business days.

## Script interface

`python3 scripts/dispute_plan.py` reads one JSON object from stdin and emits one JSON object to stdout. Required top-level fields are `filing_date`, `user_id`, `accounts`, `cards`, `open_disputes`, and `claims`. An account has `account_id`, `account_type`, `account_tier` (or a tier-bearing `account_class`), `status`, `date_opened`, and optional `has_holds_or_restrictions`. A claim includes the exact transaction/card/account IDs, dates, amounts, category/type, fraud flag, all four boolean fields required by the filing tool, PIN value, `statement_date`, optional boolean `timely_reporting_confirmed`, and optional `customer_max_liability_amount`. It may include `duplicate_group` and `duplicate_sequence`.

The output has per-claim errors/warnings, `eligible_to_file`, a complete `filing_payload` including the tool-required liability field, and aggregate `card_actions`. Validate that no payload is emitted for an invalid/capacity-blocked claim and that each emitted payload has all required filing fields before calling a banking tool.
