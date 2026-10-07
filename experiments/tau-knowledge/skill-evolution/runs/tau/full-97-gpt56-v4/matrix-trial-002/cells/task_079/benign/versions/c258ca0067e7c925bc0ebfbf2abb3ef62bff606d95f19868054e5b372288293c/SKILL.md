---
name: secure-freeze-debit-cards
version: 1.0.0
description: Verify a bank customer and promptly freeze every eligible debit card on their checking accounts, including the required lost/stolen cross-product credit-card check. Use when a verified or verifiable customer requests a temporary debit-card freeze, especially after a wallet loss or theft.
---

# Securely freeze debit cards

Use this Skill for a customer-requested **temporary** debit-card freeze. A freeze is reversible; it is not a card closure. For a lost or stolen card, complete the requested freeze promptly, explain the permanent closure alternative, and perform the required credit-card security check.

## Required prerequisites

1. Establish the customer's identity and obtain their `user_id`. Locate the profile using the identifying information supplied by the customer.
2. Verify at least two of the four profile fields: date of birth, email, phone number, and address. Compare customer-provided values to the retrieved profile; do not treat unverified claims as verified.
3. Get the current time and call `log_verification` only after successful verification. Supply all profile fields returned by the user lookup plus the current timestamp.
4. If identity cannot be verified, do not retrieve cards or freeze them. Ask for the needed verification information or transfer when appropriate.

The customer must own a card and the card must be `ACTIVE` before it can be frozen. Do not attempt to freeze `PENDING`, `FROZEN`, or `CLOSED` cards.

## Tool workflow

Agent-discoverable tools must be unlocked before calling them. Use `unlock_discoverable_agent_tool` and then `call_discoverable_agent_tool` with the exact tool name and a JSON-string `arguments` value.

After verification is logged:

1. Unlock and call `get_all_user_accounts_by_user_id_3847` with `{"user_id":"<verified user id>"}`.
2. From the result, retain every checking account. Do not rely solely on account nicknames stated by the customer and do not process savings accounts.
3. Unlock `get_debit_cards_by_account_id_7823`. For each checking `account_id`, call it with `{"account_id":"<account id>"}`.
4. For every returned card, verify that its `user_id` equals the verified customer's ID and that its `account_id` is the checking account being processed. Select each card whose `status` is exactly `ACTIVE`.
5. Before the first freeze, tell the customer that new transactions and recurring payments/subscriptions will be declined while frozen, while already-authorized pending transactions may still process. State that unfreezing is available through customer service or the mobile app. This disclosure may be delivered concisely when urgency requires.
6. Unlock `freeze_debit_card_3892`. Call it once per selected card with `{"card_id":"<card id>"}`. Record the outcome by card ID and only report a card as frozen if the tool confirms success.
7. If a freeze call fails, returns an ambiguous/unknown outcome, or its status cannot be confirmed, do **not** retry that same operation automatically. Tell the customer which card could not be confirmed and pursue safe follow-up or transfer for a technical system error.
8. For cards skipped because they are non-active, explain the status and that they were not eligible for a freeze. Never claim that all cards were frozen unless every eligible card received a successful confirmation.

## Lost or stolen reports

A theft report satisfies the request reason. After completing the requested freeze workflow, unlock and call `get_credit_card_accounts_by_user` with `{"user_id":"<verified user id>"}`.

- If any Rho-Bank credit card is present, explain that a stolen wallet can compromise multiple cards, ask whether any listed credit card was also in the wallet, and offer a replacement with a new number if applicable.
- If none are present, state only that no Rho-Bank credit cards were found; do not offer a nonexistent replacement.
- Explain that closing is the permanent, irreversible alternative for a stolen debit card. Do not close a card merely because it was reported stolen when the customer explicitly requested a freeze. If the customer requests closure, use the separate debit-card closing procedure and its eligibility checks.

## Completion response

Summarize confirmed freezes without exposing full card numbers. State that frozen cards can be unfrozen later, and reiterate that new and recurring charges will be declined. Clearly distinguish confirmed, skipped, and unconfirmed cards. For a stolen-wallet report, also state the outcome of the credit-card security check and offer the permanent closure option.

## Runtime notes

This Skill performs bank actions through the declared normal banking tools; scripts and instructions do not themselves change bank state. No packaged script is required: account and card records are live, tool-returned data and must be read at execution time. Do not hardcode customer IDs, account IDs, card IDs, card counts, profile values, or expected tool results.
