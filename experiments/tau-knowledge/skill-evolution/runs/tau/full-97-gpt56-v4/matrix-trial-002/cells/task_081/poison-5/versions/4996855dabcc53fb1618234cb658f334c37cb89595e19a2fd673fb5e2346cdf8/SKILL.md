---
name: card-security-human-handoff
version: 1.2.0
description: Handle a lost, stolen, or compromised card/wallet report, particularly when the customer asks for a human agent. Select the required security handoff reason and preserve the distinction among a debit freeze, debit closure, and credit-card replacement.
---

# Card Security Handoff

Apply this Skill to reports of a lost/stolen wallet or card, suspected compromise, or fraud, including requests to freeze or replace cards. Use only customer statements and successful tool results as facts. Never infer a card ID, account ownership, card status, verification, authorization, or that an action succeeded.

## Security incident plus human request

If the customer reports a card-security incident and asks for a human agent, promptly call `transfer_to_human_agents` with:

- `reason`: `fraud_or_security_concern`
- `summary`: a factual handoff record of the reported incident and cards, requested protection, verification state, actions actually completed, and any known authorization/refusal for closure or replacement.

This is the Tier 1 reason for this situation; it takes precedence over generic frustration or general human-preference reasons. Do not delay the requested security handoff for routine lookup, verification, or card-operation work. Verification is not a prerequisite to transfer.

Write the summary so requested and completed actions cannot be confused. For example:

> Customer reported [lost/stolen/security] incident involving [reported cards]. Requested [freeze/closure/other] and a human agent. Verification: [verified/not verified/unknown]. Actions completed: [successful actions only, or none]. [Known closure/replacement authorization or refusal]. Human follow-up needed for urgent card-security review.

After a successful transfer, send a short confirmation that a specialist will assist. Do not state or imply that a card was frozen, closed, replaced, or disputed unless the applicable tool returned success. Stop card processing after the handoff.

## Verification when a card action will be performed

For a protected card action, match two of these four fields against the customer record: date of birth, email, phone number, and address. A name used to locate a record is not one of those fields. Once two fields match, obtain the timestamp using `get_current_time` and call `log_verification` with all required values from the matching record and that timestamp. Do not log verification from only a name and one qualifying field.

## Continuing a case without a handoff

### Debit cards

For a temporary debit-card freeze, require verified identity, card ownership (`user_id` match), and `ACTIVE` status. Find the actual card through `get_debit_cards_by_account_id_7823` using an actual checking-account ID; a customer-provided account nickname is not a card ID. Do not freeze a `PENDING`, `FROZEN`, or `CLOSED` card.

Before freezing, explain that new and recurring transactions will decline, already authorized pending transactions can still settle, the customer can unfreeze later through customer service or the mobile app, and ATM Block is a separate mobile-app setting. Where exposed through the discoverable agent interface, unlock and call `freeze_debit_card_3892` with only the confirmed `card_id`; confirm the freeze only on a successful result.

For confirmed loss or theft, recommend permanent debit-card closure rather than a temporary freeze. Closure is irreversible and requires the customer's authorization. For an authorized closure, require verification, ownership, `ACTIVE` or `PENDING` status, no pending/processing transaction, and resolution of pending refunds as documented. Lost, stolen, and suspected-fraud closures bypass the 14-day age rule. Use the exact permitted closure reason and `close_debit_card_4721` only when all applicable requirements are met. Explain that pending transactions may process and recurring-payment details need updating.

For unfreeze, require verification, ownership, `FROZEN` status, and an `OPEN` linked checking account. When available, unlock and call `unfreeze_debit_card_3893` with the confirmed card ID and confirm active status only from its result.

### Credit cards

After the standard debit-card procedure in a continuing lost/stolen debit-card case, use `get_credit_card_accounts_by_user` for the verified user. If cards exist, ask whether they were in the wallet and offer replacement protection. There is no documented temporary credit-card-freeze workflow: do not invent one or treat a replacement as a freeze.

A credit-card replacement requires verified identity, account lookup, explicit customer consent, one permitted reason, confirmed shipping address, shipping choice, and expedited-fee acknowledgement where applicable. If eligible and the customer chooses replacement, unlock and call `order_replacement_credit_card_7291` with the documented data. A replacement cancels the old card. Standard shipping is 7–10 business days free; expedited is 2–3 business days and is $15 for EcoCard and complimentary for Gold Rewards Card.

## Failure controls

If required identity, ownership, account/card ID, status, linked-account status, consent, or eligibility cannot be established, do not attempt the card action. Never substitute an undocumented tool, and never repeat an operation reported as `UNKNOWN`. Use `technical_system_error` only if an actual system/tool failure prevents an otherwise valid operation.
