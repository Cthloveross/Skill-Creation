---
name: secure-stolen-wallet-cards
version: 1.2.0
description: Secure a verified customer's debit cards after a lost or stolen wallet report, perform the required related-credit-card protection offer, restore a found temporarily frozen debit card, and provide a contextual human handoff when requested. Use for lost/stolen wallet reports, debit-card freeze or closure requests, credit-card replacement offers, and later debit-card unfreeze requests.
---

# Secure Stolen-Wallet Cards

## Scope and safety boundary

Use this Skill when a customer reports a lost or stolen wallet or debit card, asks to secure debit cards, later finds a temporarily frozen debit card, or requests human assistance with the resulting security case.

A debit-card **freeze** is a temporary, reversible lock. A debit-card **closure** is permanent and cannot be reversed. For confirmed loss or theft, recommend closure rather than a temporary freeze, but perform only the action the verified owner authorizes and only after all documented prerequisites are satisfied. Do not alter the status of other cards merely because one card is frozen, closed, or later unfrozen.

No documented agent workflow in this Skill freezes or locks a credit card. Do not describe a credit-card replacement as a reversible freeze. For a lost/stolen wallet, check related credit-card accounts and offer the documented replacement process.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Verify identity and authority first

Before any banking action:

1. Locate the customer using customer-supplied information, such as full name, email, or phone number.
2. Obtain confirmation of two profile fields among date of birth, email, phone number, and address. A lookup result alone is not confirmation by the customer.
3. Retrieve the full profile as needed, get the current timestamp, and call `log_verification` only after two fields are confirmed. Supply the complete required profile fields and timestamp.
4. Treat the customer as verified only after a successful verification log result.
5. For every selected debit card, verify its `user_id` matches the verified user. For every selected credit-card account, verify it belongs to that user.

If identity, authority, ownership, or the requested card selection is uncertain, do not take a banking action. Ask for the missing information or provide an appropriate supported escalation.

## Locate products and establish current status

1. Call `get_all_user_accounts_by_user_id_3847(user_id)` to obtain checking and savings accounts, including current status.
2. For each requested checking account, call `get_debit_cards_by_account_id_7823(account_id)`. Match the requested account/card description to the returned card. The lookup supplies card ID, linked account ID, owner, last four digits, and status.
3. Call `get_credit_card_accounts_by_user(user_id)` whenever a debit card or wallet is reported lost or stolen, even if the customer initially mentions only debit cards.
4. Use current tool results to determine ownership, status, eligibility, and requested targets. Ask for a non-sensitive clarifier if more than one returned card could match the customer's description.

`scripts/plan_card_security.py` can validate a supplied inventory and prepare a non-executable review checklist. It cannot verify identity, retrieve live data, authorize an action, or perform a banking action.

## Temporary debit-card freeze

Use a freeze only when the verified owner chooses a temporary lock rather than permanent closure.

### Freeze eligibility

For each target card, establish all of the following before calling a freeze tool:

- Identity has been verified and logged.
- The card belongs to the verified customer.
- The card currently has status `ACTIVE`.
- The customer has confirmed the particular target card(s) and temporary-freeze action.

Do not freeze a `PENDING`, `CLOSED`, or already `FROZEN` card.

### Required pre-freeze disclosure

Before a freeze, tell the customer:

- New transactions will be declined while the card is frozen.
- Recurring payments and subscriptions will also be declined.
- Pending transactions already authorized may still process.
- The card can be unfrozen through customer service or the mobile app.
- Freezing does not affect ATM access when the customer has the PIN; an ATM block must be enabled separately through the mobile app.
- A reminder notification is sent if the card remains frozen for 90 days.

### Execute and confirm

For every eligible, confirmed target, call `freeze_debit_card_3892` with that card's `card_id`. Enumerate the eligible targets rather than treating a multi-card request as an unspecified blanket action. Confirm a freeze only after a successful result establishes `FROZEN` status. If a call fails or is ambiguous, do not claim the card is protected; communicate the outcome and use an available escalation path if needed.

## Debit-card unfreeze when a card is found

A verified owner who finds a temporarily frozen card may request its restoration. Do not state that unfreezing is unavailable when the documented conditions below are met.

### Unfreeze eligibility

For the selected card, verify:

- The customer remains verified.
- The card owner matches the verified user.
- The debit card currently has status `FROZEN`.
- The checking account linked by `card.account_id` currently has status `OPEN`.
- The owner has requested unfreezing that particular card.

Use `get_all_user_accounts_by_user_id_3847` and `get_debit_cards_by_account_id_7823` when current status is not already established by unambiguous, recent workflow results. Do not unfreeze any other frozen card without a separate request.

### Execute and confirm

Call `unfreeze_debit_card_3893` with:

```json
{"card_id":"selected frozen debit-card ID"}
```

If this workflow is exposed as a discoverable agent tool rather than a direct banking tool, first call `unlock_discoverable_agent_tool` for `unfreeze_debit_card_3893`, then call `call_discoverable_agent_tool` with the same `card_id` argument. Unlocking is not a reason to substitute a transfer for the documented action.

Confirm success only from a non-error result establishing that the card is `ACTIVE`. Tell the customer it is active and ready to use immediately. If the result fails, is ambiguous, or does not establish `ACTIVE`, do not say the card is usable; explain the outcome and escalate if appropriate. Leave all unrequested cards in their existing states.

## Permanent debit-card closure alternative

For a confirmed lost, stolen, or fraud-affected debit card, recommend permanent closure. Closure is irreversible. The permitted documented reasons are exactly `lost`, `stolen`, `fraud_suspected`, `damaged`, `no_longer_needed`, and `account_closing`.

Before calling `close_debit_card_4721(card_id, reason)`, establish verified ownership and all applicable closure requirements:

- The card is currently `ACTIVE` or `PENDING`.
- There are no pending or processing transactions.
- There are no pending refunds, unless the customer supplies the documented written acknowledgement that refunds will credit the linked checking account.
- The card has been active at least 14 days based on `date_issued`, except that loss, theft, and suspected fraud bypass only this minimum-age condition.

For lost, stolen, or suspected-fraud reasons, explain that pending authorized transactions may still process, offer the applicable debit replacement process, and advise the customer to review transactions and file disputes for unauthorized activity. After successful closure, explain that the card cannot be reactivated and recurring merchants need updated payment details.

### Frozen-card closure blocker

Do not call `close_debit_card_4721` for a card known to be `FROZEN`: the documented closure workflow requires `ACTIVE` or `PENDING` status. Do not unfreeze a card merely to work around that closure condition. Explain the status blocker and preserve the card's frozen protection while arranging the available next step or requested human support.

## Credit-card protection and replacement

A lost/stolen debit-card or wallet report requires a credit-card account check. For each active owned credit account, explain that wallet theft may expose multiple cards, ask whether that card was also in the wallet, and offer a replacement with a new card number. Record a decline through the available customer-record process when applicable.

Do not submit a replacement solely because it was offered or because the customer requested a card “freeze.” A replacement order requires the verified owner to provide or confirm all of the following for each selected account:

1. Correct active credit-card account/card and eligibility.
2. A confirmed complete shipping address, including unit or suite information where applicable.
3. Exactly one reason: `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`.
4. Shipping selection: `standard` (7–10 business days, no fee) or `expedited` (2–3 business days).
5. Consent to an applicable expedited fee: $15 for entry tier, $10 for mid tier, or $0 for premium tier and above. Strongly recommend expedited shipping for `stolen` or `fraud_suspected`.
6. Explicit authorization to submit the replacement order.
7. No pending replacement order and no applicable replacement-limit or other eligibility blocker. When available, check `get_pending_replacement_orders_5765` using the credit-card account ID. A pending or shipped order blocks another order; delivered and cancelled orders are final.

When all requirements are complete, unlock `order_replacement_credit_card_7291` using `unlock_discoverable_agent_tool`, then invoke it through `call_discoverable_agent_tool` with the selected account/card identifier, reason, confirmed `shipping_address`, `shipping_speed`, applicable expedited-fee acknowledgement, and relevant notes.

After a successful order, say that the old credit card is automatically cancelled for security and will no longer work for new purchases. State the selected delivery window, advise the customer to watch for order and shipping emails, and for theft/fraud remind them to review transactions and dispute unauthorized charges.

If address, shipping speed, fee acknowledgement, authorization, or eligibility information is missing, do not place a replacement order. Ask for the missing information or retain the offer for a later interaction.

## Human-assistance escalation and handoff

When the customer asks for a human agent, human assistance, a specialist, supervisor, or equivalent help, use `transfer_to_human_agents` after completing any safe, already-authorized action that can be completed. Use the reason most accurately supported by the request; for a general direct request for human help, `customer_requests_human_no_specific_reason` is appropriate, while an active security case may warrant `fraud_or_security_concern`.

A successful handoff must preserve the security context in the `summary`. Build it from live case facts, not assumptions. In particular, where applicable, distinguish:

- each card the customer reports stolen, using its customer-facing account/card label, and its current `FROZEN` status;
- the outstanding closure or **replacement** assistance the customer seeks for those stolen cards; and
- any different card that was found, successfully unfrozen, and is now `ACTIVE`.

For example, adapt this structure to the actual customer labels and statuses: `Verified customer requests human assistance. [stolen card label 1] and [stolen card label 2] are reported stolen and currently FROZEN; closure/replacement assistance is requested. [found card label] was found, successfully unfrozen, and is currently ACTIVE.` Do not collapse different card states into a generic statement such as “all cards secured.” Confirm transfer only after a successful, non-error transfer result.

## Failure handling

- **Identity unverified, ownership mismatch, or target unclear:** do not take card action; obtain the missing information.
- **Debit card not `ACTIVE` for freeze:** do not freeze it; explain the status.
- **Debit card not `FROZEN` for unfreeze:** do not call unfreeze; explain the status.
- **Linked checking account not `OPEN` for unfreeze:** do not unfreeze; explain the account-status blocker.
- **Known `FROZEN` card requested for closure:** do not close or unfreeze it as a workaround; retain protection and arrange the supported next step.
- **No matching checking account or debit card:** report that no qualifying card was found and re-check product details.
- **Credit-card lock unavailable:** do not invent a lock capability; offer the documented replacement process or transfer if requested.
- **Replacement prerequisites missing or order pending:** do not submit an order; explain the blocker.
- **Tool failure or unclear result:** do not claim success; preserve verified context and escalate when necessary.

## Helper script

`scripts/plan_card_security.py` reads one JSON object from stdin and emits one JSON object to stdout. It performs deterministic inventory validation only and makes no tool calls.

Input schema:

```json
{
  "user_id":"verified customer ID",
  "identity_verified":true,
  "reported_lost_or_stolen":true,
  "requested_debit_account_ids":["optional checking account IDs"],
  "debit_cards":[
    {"card_id":"...","account_id":"...","user_id":"...","status":"ACTIVE","card_number_last_4":"..."}
  ],
  "credit_accounts":[
    {"account_id":"...","user_id":"...","account_status":"ACTIVE","card_type":"...","card_last_4_digits":"..."}
  ]
}
```

Run it with `relative_path` set to `scripts/plan_card_security.py` and live tool results as input. Review `blocking_errors`, candidate ownership, and statuses before taking any action. A valid helper result is not authorization: the executor must still verify and log identity, give required disclosures, obtain action-specific confirmation, and use the normal banking tools.
