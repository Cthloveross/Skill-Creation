---
name: lost-wallet-debit-card-security
version: 1.0.0
description: Secure a verified customer's debit cards after a lost or stolen wallet report, then assess and prepare eligible replacement-card orders. Use for multi-account debit-card freeze, closure, and replacement requests.
---

# Lost-wallet debit-card security and replacement workflow

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety rules

Use this workflow when a customer reports a lost/stolen wallet or debit card and asks to freeze, close, or replace one or more debit cards.

- Treat a reported lost or stolen card as a security event. A freeze is temporary; a closure is permanent and cannot be reversed.
- Never identify cards solely from a customer-supplied account nickname if the retrieved account data cannot map that nickname to one exact account. Ask for a safe discriminator or clarify which displayed account is intended.
- Never freeze, close, or order for a card unless the verified customer's user ID matches the card's `user_id` and the card is linked to the selected checking account.
- Do not infer delivery/design choices, fee acceptance, replacement-limit choices, or a permanent closure authorization. Obtain each required customer decision explicitly.
- Do not unfreeze a card merely to work around a closure or ordering restriction. Preserve the security protection and seek an authorized operational path if documented requirements conflict.
- Scripts only calculate recommendations. They never perform banking actions.

## 1. Verify before an action

1. Obtain an account locator (for example, name or email), retrieve the customer record, and ask for enough identity fields to confirm **at least two of the four**: date of birth, email, phone number, and address.
2. Compare the customer-provided values to the retrieved record; do not count an unconfirmed value as verification.
3. Retrieve the current time and, after successful verification, call `log_verification` with the retrieved `name`, `user_id`, `address`, `email`, `phone_number`, `date_of_birth`, and `time_verified`.
4. If verification fails, is incomplete, or finds more than one possible person, do not perform any banking action. Continue verification or transfer when appropriate.

## 2. Find and validate the requested cards

1. Call `get_all_user_accounts_by_user_id_3847(user_id)`.
2. Match every requested account to a returned account. Debit cards are eligible only on checking accounts. Confirm each selected account is OPEN when evaluating a replacement; account retrieval also establishes that the account belongs to the verified customer.
3. Unlock and use `get_debit_cards_by_account_id_7823` for each selected checking account. Review all returned cards rather than assuming the first is current.
4. For a requested freeze, select only the card(s) that both belong to the verified user and have status `ACTIVE`. A PENDING, CLOSED, or already FROZEN card cannot be frozen. If there is not exactly one intended current card for an account, explain the ambiguity and ask the customer to identify it; do not affect an old or another cardholder's card.
5. Before a card action, state the effect relevant to a freeze: new and recurring transactions will be declined, authorized pending transactions may still settle, and unfreezing remains available. A freeze does not block ATM access for someone with the PIN; ATM Block is a separate mobile-app setting.

## 3. Freeze the cards the customer explicitly requested

1. Unlock `freeze_debit_card_3892` once it is needed.
2. Call it separately with each validated `card_id`. Check each tool result before moving to the next card; never assume a batch succeeded.
3. Record and communicate per-card outcomes. For a success, confirm it is frozen. For a failure or ineligible status, retain the result, explain the specific blocker without exposing unnecessary card data, and do not claim it was secured.
4. A lost/stolen report normally warrants discussing permanent closure because a found card can be unfrozen but a closed card cannot be reactivated. If the customer asked for an immediate freeze first, complete valid freezes first and obtain any later permanent-closure decision separately.
5. After completing the debit-card freeze/close procedure, call `get_credit_card_accounts_by_user(user_id)`. If credit cards exist, explain the wallet-theft risk, ask whether those cards were also in the wallet, and offer a replacement with a new number. If none exist, state no credit-card replacement action is needed.

## 4. Permanent closure only when supported and authorized

For lost, stolen, or fraud-suspected cards, closure is normally recommended instead of a temporary freeze.

- Obtain the reason (`lost`, `stolen`, `fraud_suspected`, `damaged`, `no_longer_needed`, or `account_closing`) and confirm the customer wants permanent deactivation.
- Retrieve/inspect the card and ensure it belongs to the customer. The documented closure status requirement is ACTIVE or PENDING. Pending transactions and pending refunds must be handled before closure under the closure policy; lost/stolen/fraud-suspected bypasses the 14-day minimum card-age requirement, but not the stated status and transaction/refund requirements.
- Unlock and call `close_debit_card_4721` with exactly `card_id` and `reason` only after all documented prerequisites are met.
- If a card was frozen first and the documented close procedure does not permit its current status, do not unfreeze it to bypass the rule. Keep it protected, explain that a replacement cannot yet be represented as completed, and obtain an authorized escalation/operational resolution.
- Confirm a successful closure is permanent; recurring payments must be updated and refunds route to the linked checking account.

## 5. Collect and assess replacement requirements

Do this before calling `order_debit_card_5739`; a request for a replacement is not a substitute for all ordering confirmations.

For each intended replacement, collect and validate:

1. The specific OPEN checking account and its account class/tier.
2. That it is a checking account, open at least 3 business days, has at least $25 available, and the customer is at least 18 based on date of birth.
3. Debit-card history for that account: no pending card order and no more than one active card. For replacement-limit history, count cards issued in the prior 12 months whose `issue_reason` is `lost`, `stolen`, `fraud`, or `damaged`; do not count `new_account`, `first_card`, `expired`, `upgrade`, or `bank_reissue`.
4. Any applicable replacement waiting period after closure and whether the customer elects a permitted excess-replacement fee option.
5. A valid US domestic mailing address, the delivery option, and card design. Explicitly confirm the address.
6. The exact delivery and design fees, any applicable excess replacement fee, sufficient balance for automatic charges, and the customer's authorization for those charges.

Use `scripts/replacement_quote.py` to calculate tier rules consistently. It does not establish all eligibility: the live account/card records and the ordering tool remain authoritative.

### Tier rules

- **ENTRY:** maximum 2 replacements in 12 months; 48-hour wait after closure; STANDARD only ($0 delivery); excess is optional at $25. CLASSIC $0, PREMIUM $10, CUSTOM $25.
- **MID:** maximum 3; no wait; STANDARD $0 or EXPEDITED $15; excess is optional at $15. CLASSIC $0, PREMIUM $10, CUSTOM $25.
- **PREMIUM:** maximum 5; no wait; STANDARD or EXPEDITED $0, RUSH $35; no excess-fee option. CLASSIC/PREMIUM $0, CUSTOM $15.
- **ELITE:** unlimited; no wait; STANDARD, EXPEDITED, and RUSH are $0. All designs are $0.

All applicable replacement shipping, design, and excess fees are automatically charged to the linked checking account. State this before ordering. Supply the exact `delivery_fee` and `design_fee` required by the order tool. Do not invent an argument for an excess fee: inspect the unlocked tool schema and follow it only if it exposes a supported way to collect that fee.

## 6. Place and report an order

1. Unlock `order_debit_card_5739` and inspect its available parameters.
2. Only after every prerequisite and confirmation above is satisfied, use the unlocked schema to submit one order per eligible selected account with the customer-confirmed delivery, design, address, and exact fees.
3. Check every result independently. Report successful orders with the selected delivery estimate and charged fees. Clearly distinguish a failed, blocked, or not-yet-authorized order from a submitted one.
4. Do not expose full card numbers. If the customer has not selected delivery/design or approved the fees, finish the security action and ask for those choices rather than ordering.

## Script interface and runnable example

`replacement_quote.py` receives one JSON object on standard input and emits one JSON object on standard output. Input fields are:

- `account_class`: `ENTRY`, `MID`, `PREMIUM`, or `ELITE`
- `cards`: list of objects with `issue_reason` and `date_issued`
- `as_of`: ISO date or timestamp used for a deterministic quote
- `delivery_option`: `STANDARD`, `EXPEDITED`, or `RUSH`
- `design`: `CLASSIC`, `PREMIUM`, or `CUSTOM`
- optional `closed_at`: ISO timestamp for the just-closed card
- optional `accept_excess_fee`: boolean

Example invocation in a runtime that supports scripts:

```json
{"account_class":"MID","cards":[],"as_of":"2025-01-15","delivery_option":"EXPEDITED","design":"CLASSIC","accept_excess_fee":false}
```

Validate the response before use: `valid` must be true, `eligible_to_order` must be true, and `delivery_fee`/`design_fee` must match the selected tier option. Then separately validate live ownership, account/card status, age, balance, address, pending-order state, closure state, and customer authorization.
