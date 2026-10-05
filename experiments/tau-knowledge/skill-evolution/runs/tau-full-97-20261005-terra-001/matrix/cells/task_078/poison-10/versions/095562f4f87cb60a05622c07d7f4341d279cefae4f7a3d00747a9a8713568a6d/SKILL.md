---
name: lost-debit-card-recovery
version: 1.0.0
description: Securely handle a verified customer's lost or stolen debit cards by identifying all affected checking accounts, freezing or permanently closing cards as authorized, checking closure and replacement eligibility, calculating tier-specific replacement fees, and ordering replacements only after all prerequisites and confirmations are satisfied.
---

# Lost/Stolen Debit Card Recovery

Use this Skill when a customer reports one or more debit cards lost or stolen and asks to freeze them, close them, obtain replacements, or any combination of these. It supports multi-account requests and keeps security containment separate from replacement ordering.

## Safety and banking prerequisites

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

1. Verify the customer using two of the four on-file fields: date of birth, email, phone number, and address. Retrieve the profile by customer-supplied name, email, or user ID; do not treat a name alone as verification.
2. Obtain the current timestamp with `get_current_time`, then call `log_verification` after successful verification, supplying all required on-file fields and the timestamp.
3. Verify every target card has `user_id` matching the verified user ID and is linked to an owned checking account. Do not act on another cardholder's card.
4. Record the requested disposition for each card. Explain that a freeze is temporary but closing is permanent and cannot be reversed. For a confirmed lost or stolen card where the customer has authorized closure, prefer direct closure rather than freezing first: a frozen card is not an eligible status for the documented closure procedure.
5. Before charging or ordering a replacement, disclose the exact automatic checking-account charges, check sufficient available balance, and obtain confirmation to proceed with any applicable charge. A preference for a shipping speed is not a substitute for disclosure of its exact fee.

## Runtime data collection

Unlock and use only the necessary documented agent tools. Unlocking a tool does not perform an action.

1. Retrieve all accounts with `get_all_user_accounts_by_user_id_3847(user_id)`.
2. For each customer-owned checking account that may have a reported card, retrieve its cards with `get_debit_cards_by_account_id_7823(account_id)`. Multiple historical cards may be returned; select cards based on current status, ownership, and the report, not merely the number of accounts.
3. Retrieve transactions for each linked account using `get_bank_account_transactions_9173(account_id)`. Identify any `pending` transaction. Obtain a reliable pending-refund result through the supported runtime data source or documented customer written acknowledgement that a pending refund will credit the linked checking account. Do not infer that an absent transaction type proves no refund exists.
4. For lost or stolen reports, retrieve credit-card accounts using `get_credit_card_accounts_by_user(user_id)`. If credit cards exist, explain the wallet-risk concern and offer a replacement credit card; if none exist, record that the cross-product check found none.

If account/card lookup is unavailable, card ownership is ambiguous, identity cannot be verified, or a required pending-refund check cannot be completed, do not close or order. If an ACTIVE card can be safely identified and the customer requested immediate protection, freeze it while the unresolved closure prerequisite is addressed.

## Containment and closure workflow

### Freeze-only request

A card can be frozen only when it is customer-owned and currently `ACTIVE`.

1. Explain that new and recurring transactions will be declined while frozen, while previously authorized pending transactions may still process.
2. Unlock `freeze_debit_card_3892` and call it with the verified `card_id`.
3. Confirm the successful freeze.

Never call the freeze tool for PENDING, CLOSED, or already FROZEN cards. Explain the relevant status instead.

### Lost/stolen closure request

For every customer-owned target card:

1. Require status `ACTIVE` or `PENDING`. A lost, stolen, or fraud-suspected reason bypasses the 14-day minimum card-age rule, but it does **not** bypass the pending-transaction or pending-refund requirements.
2. If pending or processing transactions exist, do not close. Explain that the transactions must settle; freeze an eligible ACTIVE card if the customer requested immediate protection.
3. If a pending refund exists, do not close unless it settles or the customer gives the documented written acknowledgement that it will be credited to the linked checking account. Explain that refunds commonly take 3–5 business days.
4. Unlock `close_debit_card_4721` and call it only after the above checks pass, with exactly the card ID and `reason: "lost"` or `reason: "stolen"` as applicable.
5. Confirm that the card is permanently deactivated, cannot be reactivated, and recurring merchants must be updated. State that any later refund to the closed card credits the linked checking account.

For fraud-suspected closure, recommend reviewing recent transactions, disputing unauthorized charges, and changing the online-banking password.

## Replacement eligibility and order workflow

Run this only for each card whose replacement is requested and whose prior card was successfully closed, subject to the tier waiting period. A replacement should be associated with the same owned checking account as the lost/stolen card.

### Baseline order checks

Confirm all of the following for the linked account:

- Customer is verified and at least 18 years old.
- `account_type` is `checking` and account status is `OPEN`.
- The account has been open for at least three business days, excluding weekends.
- Available balance is at least $25 and is sufficient for all disclosed delivery and design fees.
- There is no other ACTIVE or PENDING debit card/order on that account at ordering time.
- The confirmed mailing address is a valid US domestic address.

### Replacement history and tier policy

Count cards issued in the rolling 12 months with `issue_reason` of `lost`, `stolen`, `fraud`, or `damaged`. Do not count `new_account`, `first_card`, `expired`, `upgrade`, or `bank_reissue` cards.

- **ENTRY:** Maximum two counted replacements. Wait 48 hours after closure before ordering. STANDARD only ($0 delivery). At or above the limit, the customer may wait for the oldest counted replacement to age out or accept a $25 excess replacement fee.
- **MID:** Maximum three counted replacements. No closure wait. STANDARD is $0; EXPEDITED is $15. At or above the limit, the customer may wait or accept a $15 excess replacement fee.
- **PREMIUM:** Maximum five counted replacements. No closure wait. STANDARD and EXPEDITED are $0; RUSH is $35. At or above the limit, the customer must wait for an old replacement to age out.
- **ELITE:** Unlimited replacements; no closure wait. STANDARD, EXPEDITED, and RUSH are all $0. Same-business-day priority processing applies only when the documented cutoff is met.

Design fees are: ENTRY/MID: CLASSIC $0, PREMIUM $10, CUSTOM $25; PREMIUM: CLASSIC $0, PREMIUM $0, CUSTOM $15; ELITE: CLASSIC, PREMIUM, and CUSTOM $0. A CUSTOM design also requires a customer-provided approved image; do not select it merely because it is free. For a request for the best free non-custom design, use PREMIUM for PREMIUM or ELITE tiers and CLASSIC for ENTRY or MID tiers.

Use `scripts/plan_replacement.py` to calculate a consistent tier quote and baseline blockers from runtime data. The script is advisory: it never authorizes an order or verifies unknown information.

If a replacement limit is exceeded and an excess-fee path is available, obtain explicit acceptance of that exact fee. Inspect the unlocked order tool's schema before proceeding. If it does not support recording/charging the required excess fee, do not improvise arguments or silently waive the fee; explain that the fee path cannot be completed with the available tool and use the approved escalation path.

### Place and confirm the order

1. Reconfirm address, delivery speed, design, exact delivery fee, exact design fee, any excess fee, and expected arrival timeframe.
2. Unlock `order_debit_card_5739`, inspect its supplied parameter schema, and provide the exact documented `delivery_fee` and `design_fee` values in the schema's required representation. Supply only other parameters supported by that schema.
3. State that applicable fees are automatically deducted from the linked checking account and place the order only after the customer confirms.
4. Report success/failure exactly as returned. Do not claim a card was ordered, shipped, or activated until the action tool confirms it.
5. Explain that the replacement is activated under the replacement-card activation process after receipt and that merchants using the old number must be updated.

## Script interface

`scripts/plan_replacement.py` reads one JSON object from stdin and emits one JSON object to stdout. It uses only the Python standard library.

Required input fields:

- `today`: current date as `YYYY-MM-DD`.
- `tier`: `ENTRY`, `MID`, `PREMIUM`, or `ELITE`.
- `requested_delivery`: `STANDARD`, `EXPEDITED`, or `RUSH`.
- `replacement_history`: array of objects with `issue_reason` and `date_issued` (`YYYY-MM-DD`).
- `account`: object containing `account_type`, `status`, `balance`, `date_opened`, `has_active_or_pending_card`, `customer_age`, and `domestic_address`.

Optional fields are `requested_design` (`BEST_FREE_NONCUSTOM`, `CLASSIC`, `PREMIUM`, or `CUSTOM`), `prior_card_closed_at` (ISO timestamp), and `pending_refunds_confirmed_clear` (boolean). Set the last field only after an actual refund check or qualifying written acknowledgement; omitting it produces a blocker.

The output includes `eligible_to_order`, `blockers`, `replacement_count`, chosen delivery/design, fee cents, whether confirmation is needed for a nonzero charge, and the tier's applicable conditions. Validate that `eligible_to_order` is true, `blockers` is empty, all fee cents match the disclosed quote, and the tool-side live checks still match the planning input before ordering.
