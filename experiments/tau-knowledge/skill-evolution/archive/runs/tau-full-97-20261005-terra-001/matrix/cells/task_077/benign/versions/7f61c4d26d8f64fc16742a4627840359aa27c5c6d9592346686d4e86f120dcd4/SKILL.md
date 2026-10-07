---
name: debit-card-freeze-credit-protection-and-loss-escalation
version: 1.2.0
description: Protect a verified customer's debit cards after a misplaced, lost, or stolen wallet; perform required cross-product credit-card protection and replacement; and safely complete or escalate a later permanent debit-card loss request.
---

# Debit-Card Freeze, Credit Protection, and Confirmed-Loss Escalation

## Use this Skill

Use this Skill for a verified customer who wants to freeze, unfreeze, cancel, or replace debit cards, especially where a wallet is misplaced, lost, or stolen. It handles cards across multiple checking accounts, the required credit-card security check, and credit-card replacement when requested.

Read all customer-specific information at runtime. Never hardcode a customer, account, card, address, tool result, or assumed eligibility result.

## Verification gate

Before a debit-card mutation or credit-card replacement:

1. Locate the customer using a customer-provided identifier.
2. Confirm at least two record fields from date of birth, email, phone number, and address. Name alone is not a verification factor.
3. Retrieve the current time with `get_current_time`.
4. Call `log_verification` with the complete required customer record and timestamp.
5. If verification cannot be completed, explain that verification is required and do not perform card actions.

The completed verification may be used for the related protection, replacement, or loss-escalation conversation unless the runtime requires fresh verification.

## Discover debit cards and validate ownership

1. Call `get_all_user_accounts_by_user_id_3847` for the verified customer.
2. Select the checking account(s) named by the customer. Select every checking account only if the customer explicitly asks to protect all cards.
3. For each selected checking account, call `get_debit_cards_by_account_id_7823`.
4. Match every candidate card's `user_id` to the verified customer and ensure it belongs to the selected account.
5. Treat returned historical, closed, pending, and frozen cards distinctly. Do not act merely because a record was returned.
6. If multiple cards leave the requested target ambiguous, ask the customer to identify the card by account or last four digits.
7. Recheck the current status immediately before each state-changing tool call.

`scripts/evaluate_card_action.py` can produce a read-only advisory plan from normalized lookup data. It does not replace live verification, ownership checks, or a just-in-time status check.

## Temporary debit-card freeze

Use a freeze when the customer has misplaced a card, is still looking for it, or requests temporary security. Do not substitute permanent closure for an explicit freeze request.

Before freezing, explain that:

- New transactions, recurring payments, and subscriptions will be declined.
- Pending transactions already authorized may still process.
- The customer can later unfreeze through customer service or the mobile app.
- ATM use with the PIN is not affected; ATM Block is a separate mobile-app control.

For each intended card, require verified ownership and `ACTIVE` status. Unlock `freeze_debit_card_3892`, then call it through `call_discoverable_agent_tool` with the card ID. Process every independently eligible requested card. Treat each tool result as authoritative and confirm only successful freezes.

Tell the customer that a reminder is sent if a card remains frozen for 90 days. Report card-specific blockers separately without exposing full card numbers.

## Debit-card unfreeze

For an unfreeze, require verified ownership, `FROZEN` card status, and an `OPEN` linked checking account. Unlock and call `unfreeze_debit_card_3893` with the card ID. Confirm the card is active and ready to use only after a successful tool result.

A card reported stolen must not be reactivated; follow the security escalation path instead.

## Required lost/stolen wallet credit-card protection

After the requested debit-card protection is completed for a lost or stolen wallet:

1. Call `get_credit_card_accounts_by_user` for the verified customer.
2. If an active credit card exists, proactively explain that a missing wallet may expose multiple cards.
3. Ask whether that credit card was in the wallet and offer a replacement with a new card number as a security precaution.
4. Do not order a credit-card replacement only because an account exists. Continue only after the customer confirms the affected card and asks for replacement.

## Credit-card replacement workflow

### Collect required choices

When the customer accepts replacement, promptly collect any missing information. Do not claim that the documented procedure, fee, or shipping information is unavailable.

1. **Affected account:** identify the customer-confirmed credit-card account from the current lookup.
2. **Reason:** record exactly one of `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`. A card in a missing wallet may be recorded as `lost` when that accurately reflects the customer's report. If the distinction is unclear, ask whether to record it as lost or stolen.
3. **Confirmed address:** ask the customer to expressly confirm the complete shipping address, including any unit or suite, or provide an alternate address. A retrieved profile address is not itself confirmed.
4. **Shipping choice:** present both choices:
   - Standard: 7–10 business days, no fee.
   - Expedited: 2–3 business days. Silver Rewards expedited shipping costs $10.00.
5. **Fee consent:** for expedited service with an applicable fee, disclose the exact fee and obtain explicit customer acknowledgement before submission. For `fraud_suspected` or `stolen`, strongly recommend expedited service and remind the customer to review recent transactions.
6. **Eligibility:** ensure the customer is verified and the affected account was found in the current lookup. Apply any additional eligibility requirement actually supplied by the knowledge base; do not invent one.

Where practical, request all missing choices in one concise message. For example: ask the customer to confirm the address, confirm `lost` as the reason, and choose standard or $10 expedited shipping for a Silver Rewards card.

### Submit through the public replacement-tool interface

The public tool interface represents shipping with the boolean `expedited_shipping`; it does **not** use `shipping_speed` or a fee-acknowledgement argument. Consent must still be established in the conversation before an expedited paid order.

After all prerequisites are met:

1. Optionally validate normalized data with `scripts/validate_credit_replacement.py`.
2. Unlock `order_replacement_credit_card_7291` with `unlock_discoverable_agent_tool`.
3. Call it using `call_discoverable_agent_tool` and the exact exposed request shape:

```json
{
  "credit_card_account_id": "current credit-card account id",
  "user_id": "verified customer id",
  "reason": "lost",
  "shipping_address": "customer-confirmed complete address",
  "expedited_shipping": false
}
```

Set `expedited_shipping` to `true` only after the customer selected expedited delivery and, if applicable, explicitly accepted its fee. Do not add obsolete `shipping_speed`, `expedited_fee_acknowledgement`, or unsupported fields to the replacement tool request.

4. Treat the tool result as authoritative. If it errors, do not say the order was placed; explain the returned issue and take only a documented next step.

### After successful credit replacement

Tell the customer that the old credit card is cancelled and will not work for new purchases, give the selected delivery window, and advise them to watch for order and shipment emails. For a fraud-suspected or stolen reason, remind them to review recent transactions and dispute unauthorized activity through the app or website.

## Later confirmed-loss debit-card request

A customer may initially ask for temporary freezes and later confirm the wallet is gone and request permanent cancellation and replacement. Treat the later request as a new, higher-severity request; do not leave it unanswered because the cards are already frozen.

1. Confirm the requested permanent reason as `lost`, `stolen`, or `fraud_suspected` and identify both affected cards from the prior/current lookup.
2. The documented direct debit-card closure procedure requires an `ACTIVE` or `PENDING` card. Do **not** call `close_debit_card_4721` on a currently `FROZEN` card unless an applicable documented procedure explicitly authorizes it.
3. If each requested card is currently eligible for direct closure, complete all stated closure prerequisites, unlock and call `close_debit_card_4721` separately for each card with `card_id` and the permitted reason. Do not claim success without successful results.
4. If a requested card is frozen and no documented close-from-frozen path exists, explain that it remains protected by the freeze and offer transfer to the security/card-services team for permanent lost-card cancellation and replacement.
5. **After the customer accepts that transfer, immediately invoke** `transfer_to_human_agents`; an offer to transfer is not completion. Use `reason: "fraud_or_security_concern"` and a summary that carries forward all material context: the verified customer, confirmed missing wallet, both affected frozen debit cards, request for permanent cancellation, and request for replacement cards. Do not end the interaction after transfer acceptance.

A transfer is appropriate when direct closure is unsupported for frozen cards. It must be an observable tool call, not merely a statement that a transfer will occur.

## Completion response

Clearly distinguish:

- each debit card successfully frozen, unfrozen, or permanently closed;
- cards that remain unchanged and why;
- a submitted credit-card replacement and its delivery window; and
- any completed human/security transfer and the reason it is needed.

Never assert a successful freeze, closure, replacement, or transfer without the corresponding successful tool result or tool dispatch.

## Script interfaces

### `scripts/evaluate_card_action.py`

Reads one JSON object from stdin and writes one JSON object to stdout. Input fields are:

```json
{
  "action": "freeze",
  "verified_user_id": "verified-user-id",
  "requested_account_ids": ["checking-account-id"],
  "accounts": [{"account_id":"checking-account-id","account_type":"CHECKING","status":"OPEN"}],
  "cards_by_account": {"checking-account-id":[{"card_id":"debit-card-id","account_id":"checking-account-id","user_id":"verified-user-id","status":"ACTIVE"}]}
}
```

The output includes `ok`, `eligible_cards`, `rejected_cards`, `errors`, and `live_recheck_required`. It is advisory only.

### `scripts/validate_credit_replacement.py`

Reads one JSON object from stdin and writes one JSON object to stdout. It validates normalized fields before replacement submission but cannot prove a customer confirmed an address or consented to a fee.

```json
{
  "credit_card_account_id": "credit-card-account-id",
  "user_id": "verified-user-id",
  "reason": "lost",
  "shipping_address": "customer-confirmed complete address",
  "expedited_shipping": false,
  "expedited_fee": 0,
  "fee_consent_captured": false
}
```

A usable output has `ok: true`. If `expedited_shipping` is true and `expedited_fee` is positive, `fee_consent_captured` must be true.
