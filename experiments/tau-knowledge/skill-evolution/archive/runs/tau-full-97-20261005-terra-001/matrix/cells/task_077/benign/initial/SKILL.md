---
name: debit-card-freeze-unfreeze
version: 1.0.0
description: Safely freeze one or more debit cards when a verified cardholder requests a reversible temporary lock, or unfreeze an eligible frozen card. Use for misplaced-card, temporary-security, travel, and spending-restriction requests; do not use it to reactivate a card reported lost or stolen.
---

# Debit Card Freeze / Unfreeze

## Purpose

Use this Skill to identify the customer’s intended debit cards, validate ownership and card/account status, perform the appropriate reversible card-state action, and clearly communicate the outcome. It supports multiple checking accounts without assuming that every historical card returned by a lookup is a target.

## Required runtime inputs

Obtain at runtime; do not infer or hardcode values:

- Customer identity claims and a matching customer record.
- The customer’s explicit requested action: `freeze` or `unfreeze`.
- Which cards or checking accounts the request covers. “All my debit cards” may be interpreted as all current debit cards on the customer’s checking accounts. Otherwise ask which account/card is intended.
- Customer accounts from `get_all_user_accounts_by_user_id_3847`.
- Debit cards for each selected checking account from `get_debit_cards_by_account_id_7823`.

The lookup tools may be agent-discoverable in the host. When they are not available directly, unlock each documented tool with `unlock_discoverable_agent_tool`, then call it through `call_discoverable_agent_tool` using its documented name and JSON arguments.

## Verification gate

1. Locate the customer record using a customer-provided identifier.
2. Confirm **two of these four fields** with the customer and compare them with the record: date of birth, email, phone number, and address. A name alone is not one of the four verification fields.
3. Obtain the current time with `get_current_time` and create the audit record with `log_verification`, supplying the retrieved record’s required identity fields and timestamp.
4. Do not disclose card details, retrieve cards for action, or make state changes until verification succeeds. If claims do not match or two fields cannot be confirmed, explain that verification is required and stop the transaction.

## Decide the proper action

- A **freeze** is a temporary, reversible lock and is appropriate when a card is misplaced or the customer wants temporary security.
- A **close** is permanent and is appropriate when the customer confirms a card is lost/stolen or wants it cancelled. Do not substitute a close for an explicit freeze request.
- If the request is motivated by a lost or stolen wallet, complete the requested eligible debit-card protection workflow and then run the cross-product check described below.
- A card previously reported stolen must not be reactivated. Follow the stolen-card/security escalation procedure rather than unfreezing it.

## Card discovery and eligibility

1. Retrieve all customer accounts. Select only checking accounts that the customer explicitly identified, or all checking accounts only when the customer explicitly requested every debit card.
2. Retrieve debit cards for each selected checking account. Match every candidate card’s `user_id` to the verified customer’s `user_id`; never act on a card owned by another user.
3. Prefer a customer-selected last four/card ID when more than one current eligible card exists for an account. Do not act on historical cards merely because they appear in lookup results.
4. Immediately before each state change, validate the current status:
   - **Freeze:** card must be `ACTIVE`.
   - **Unfreeze:** card must be `FROZEN`, and its linked checking account must be `OPEN`.
5. Do not call a state-changing tool for cards failing a prerequisite. State the specific blocker, such as already frozen, closed, pending, not owned by the customer, or linked account not open.
6. A mixed result is possible. Process each independently eligible requested card; retain and report the result for every requested card rather than treating one failure as success for all cards.

Use `scripts/evaluate_card_action.py` after normalized lookup results are available to generate a deterministic candidate/rejection plan. Its result is advisory validation; the live lookup immediately before a mutation remains authoritative.

## Freeze workflow

1. Complete the verification gate and determine the intended cards.
2. Before freezing, tell the customer:
   - New transactions will be declined while the card is frozen.
   - Recurring payments and subscriptions will also be declined.
   - Pending transactions that were already authorized may still process.
   - They can unfreeze later through customer service or the mobile app.
   - Freezing does not affect ATM access when the customer has their PIN; blocking ATM access requires the separate mobile-app ATM Block setting.
3. For each currently eligible card, unlock `freeze_debit_card_3892` if necessary and call it with `{"card_id":"<card_id>"}`.
4. Treat the tool response as the source of truth. Confirm only cards for which the tool reports success. If a call fails or returns an unexpected result, do not claim the card was frozen; report that outcome and escalate only if required by the returned condition.
5. Confirm each successful freeze and remind the customer that a reminder is sent if a frozen card remains frozen for 90 days.

## Unfreeze workflow

1. Complete the verification gate, identify the requested card, and confirm the card is `FROZEN` and the linked checking account is `OPEN`.
2. Unlock `unfreeze_debit_card_3893` if necessary and call it with `{"card_id":"<card_id>"}`.
3. Confirm success only from the tool response. Tell the customer a successfully unfrozen card is active and ready to use immediately.

## Lost/stolen wallet cross-product protection

When the customer reports a debit card lost or stolen, check for credit cards with `get_credit_card_accounts_by_user` after protecting the debit card(s). If one or more credit-card accounts exist, proactively ask whether any was in the wallet and offer a replacement with a new card number. Explain that a missing wallet can expose multiple cards.

Do not order a replacement merely because a credit card exists. If the customer confirms a credit card was affected and requests replacement, follow the separate credit-card replacement procedure: verify eligibility, confirm the shipping address, obtain exactly one permitted replacement reason, discuss shipping/fees, unlock and call `order_replacement_credit_card_7291`, and document the result.

## Completion record and customer response

For every requested card, retain the account/card identifier needed for audit, pre-action eligibility result, tool outcome, and timestamp. In the final customer response, distinguish successful cards from cards not changed, avoid exposing full card numbers, summarize the temporary-lock effects, and make the credit-card protection offer when applicable.

## Helper usage

`evaluate_card_action.py` receives JSON on stdin and emits JSON on stdout. It does not call banking tools or perform any account action.

Example input:

```json
{
  "action": "freeze",
  "verified_user_id": "user-id-from-verification",
  "requested_account_ids": ["checking-account-id"],
  "accounts": [{"account_id": "checking-account-id", "account_type": "CHECKING", "status": "OPEN"}],
  "cards_by_account": {
    "checking-account-id": [{"card_id": "card-id", "account_id": "checking-account-id", "user_id": "user-id-from-verification", "status": "ACTIVE", "card_number_last_4": "1234"}]
  }
}
```

Run it through the packaged-script runtime with `scripts/evaluate_card_action.py`. For a freeze, a valid output has `ok: true` and one or more entries in `eligible_cards`; only those IDs are candidates for the live recheck and freeze tool. Any entries in `rejected_cards` must not be actioned unless a fresh lookup changes the prerequisite result.
