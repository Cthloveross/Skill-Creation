---
name: stolen-debit-card-close-and-replace
description: Securely handle a verified customer's report that debit cards were lost or stolen: identify the linked checking accounts and current cards, enforce debit-card closure prerequisites, close eligible cards, apply cross-product protections, and order replacements only after tier, eligibility, fee, delivery, design, and customer-confirmation requirements are satisfied.
---

# Stolen Debit Card Closure and Replacement

Use this Skill when a customer reports a debit card lost or stolen and wants it permanently cancelled, frozen, or replaced. A stolen card should normally be **closed**, not merely frozen: closing is permanent and the card cannot be reactivated. Do not use this Skill to disclose internal fraud-alert or decline-code reasons.

## Runtime inputs and assumptions

At runtime, obtain the customer's verified identity, requested affected accounts/cards, reason, delivery address confirmation, delivery/design choices, and any fee consent from the conversation and tool records. Treat a lookup result as account evidence, not identity verification by itself.

The packaged helper accepts JSON on stdin and writes one JSON object to stdout. It performs deterministic policy calculations only; it does not call banking tools or make customer-visible changes.

```json
{"action":"replacement_quote","tier":"PREMIUM","now":"2025-01-15","cards":[],"delivery":"RUSH","design":"PREMIUM"}
```

Run it with `scripts/debit_card_policy.py`. Its actions and schemas are documented in that file. Use its output as a check on, not a replacement for, the authoritative tool responses and the customer's choices.

## Required workflow

### 1. Verify and audit identity before any card action

1. Retrieve the customer record using a customer-supplied identifier.
2. Confirm at least two of these four fields with the customer: date of birth, email, phone number, and mailing address.
3. Obtain the current time and call `log_verification` only after the two-field threshold is met. Supply the complete retrieved identity record and current timestamp required by that tool.
4. Confirm that each selected card's `user_id` equals the verified user's `user_id`. Never close or order against a card owned by another user.

If the identity cannot be verified, do not disclose card details or act on the request.

### 2. Discover accounts, cards, and activity

Unlock and call the following agent tools as needed:

- `get_all_user_accounts_by_user_id_3847` with `user_id` to find accounts. Select only checking accounts named or confirmed by the customer.
- `get_debit_cards_by_account_id_7823` with each selected checking `account_id` to find cards and their status, owner, issue date, and history.
- `get_bank_account_transactions_9173` with each selected `account_id` to inspect pending activity.

For each requested account, identify the current target card(s) with status `ACTIVE` or `PENDING`. Historical `CLOSED` cards are not closure targets. If the request does not unambiguously identify one current card per requested account, ask the customer to clarify before closing any ambiguous card.

Inspect the available activity data for pending/processing debit-card transactions and pending refunds. If the runtime has a more specific card transaction/refund lookup, unlock and use it. Do not represent account-level activity as card-specific evidence when it cannot identify the card. A pending debit-card transaction blocks closure. A pending refund blocks closure unless the customer acknowledges **in writing** that the refund may be credited to the linked checking account. Record that acknowledgement in the interaction before proceeding.

For a lost/stolen report, also unlock and call `get_credit_card_accounts_by_user` with `user_id`. If any credit cards exist, ask whether they were in the wallet and proactively offer a replacement credit card. If none exist, simply continue; do not claim one was replaced.

### 3. Evaluate closure eligibility separately for every card

The closure reason must be one of `lost`, `stolen`, `fraud_suspected`, `damaged`, `no_longer_needed`, or `account_closing`. For this workflow use `stolen` only when that is what the customer reported.

Before closing, require all of the following:

- verified customer and matching card owner;
- card status is `ACTIVE` or `PENDING`;
- no pending or processing card transactions;
- no pending refunds, unless the required written linked-account credit acknowledgement was given;
- card issued at least 14 days ago.

For `lost`, `stolen`, and `fraud_suspected`, bypass **only** the 14-day card-age check. These reasons do not waive ownership, status, pending-transaction, or pending-refund requirements. If blocked, explain the precise condition and do not call the close tool for that card. For a non-security reason with a too-new card, give the earliest eligible closure date.

Use `closure_check` in the helper to apply the status, ownership, pending, acknowledgement, and age rules consistently. Unknown required facts must be treated as a blocker, not as a pass.

### 4. Close eligible stolen cards

Unlock `close_debit_card_4721`, inspect its runtime schema, then call it for each independently eligible card using the documented `card_id` and `reason`. Do not claim success until the tool confirms it.

After each successful closure, explain that:

- the card is permanently deactivated and cannot be reactivated;
- already-authorized pending transactions can still settle;
- recurring merchants using the old card need updated payment information; and
- refunds to the closed card are credited to the linked checking account.

If fraud is suspected, also recommend changing the online-banking password and reviewing recent transactions for disputes. Do not substitute a freeze for a requested stolen-card closure unless the customer changes the request; a freeze is reversible and is only available while a card is `ACTIVE`.

### 5. Quote and qualify each replacement independently

Only consider a replacement after the corresponding close succeeded. Re-fetch account/card state if necessary, then check generic ordering requirements: verified customer, OPEN checking account, at least three business days since opening, balance of at least $25, no active card, no pending order/card, and a confirmed valid US domestic mailing address. Use `order_precheck` to calculate the deterministic portions. If a tool exposes stricter current conditions, follow it.

Count cards issued in the prior rolling 12 months whose `issue_reason` is `lost`, `stolen`, `fraud`, or `damaged`; other issue reasons do not count. Use `replacement_quote` with the account tier and complete card history. The tier rules are:

| Tier | Replacement limit | Post-close timing | available delivery / delivery fee | Design fees (CLASSIC / PREMIUM / CUSTOM) |
|---|---:|---|---|---|
| ENTRY | 2 / 12 months | wait 48 hours | STANDARD $0 | $0 / $10 / $25 |
| MID | 3 / 12 months | immediate | STANDARD $0, EXPEDITED $15 | $0 / $10 / $25 |
| PREMIUM | 5 / 12 months | immediate | STANDARD $0, EXPEDITED $0, RUSH $35 | $0 / $0 / $15 |
| ELITE | unlimited | immediate | STANDARD, EXPEDITED, RUSH all $0 | $0 / $0 / $0 |

When at the replacement limit, ENTRY customers may wait until the oldest counted replacement leaves the rolling window or agree to a $25 excess replacement fee; MID customers have the analogous $15 option; PREMIUM customers must wait; ELITE has no limit. Do not invent an order parameter for an excess fee—inspect the unlocked ordering tool schema and, if it cannot represent the approved fee, do not place the order until the supported process is available.

Account class names can be mapped to tiers as follows: Light Blue Account, Light Green Account, and Green Fee-Free Account are ENTRY; Blue Account and Green Account (checking) are MID; Evergreen Account is PREMIUM; Bluest Account is ELITE. If the returned class is unknown or ambiguous, do not guess the tier or fee.

Explain all applicable delivery, design, and excess fees before ordering and obtain the customer's affirmative choice/consent. Fees are automatically deducted from the linked checking account. Do not infer a delivery or design choice merely because it was offered. A conditional preference such as “metallic only if free” resolves to PREMIUM only when its quoted design fee is $0; otherwise resolve it to CLASSIC, and tell the customer the resulting fee.

If choices are missing, request them precisely. For an ENTRY account, do not offer expedited/rush and advise of the 48-hour wait. For a MID account, do not offer rush. The normal published delivery estimates are standard 7–10 business days, expedited 3–5, and rush 1–2.

### 6. Place and confirm supported orders

Unlock `order_debit_card_5739` and inspect its actual parameter schema. Supply the exact `delivery_fee` and `design_fee` from the tier quote, along with every required account, delivery, design, and confirmed-address parameter exposed by that schema. Never fabricate a tool parameter. Call it only when all prerequisites, timing, customer choices, and fee consent are satisfied.

Report an order only after successful tool confirmation. State the account, selected delivery/design, expected delivery window, and charged fees. If a replacement cannot yet be ordered, state the exact remaining wait, missing choice, fee decision, or failed eligibility requirement and do not falsely confirm an order.

## Observable failure handling

- **No matching account/card:** explain that no eligible current card was found for the specified checking account; do not act on historical cards.
- **Owner/status mismatch:** do not close, freeze, or disclose more data; request correction or use the proper security escalation process.
- **Pending transaction/refund:** do not close; explain settlement or required written refund acknowledgement.
- **Tool failure:** do not state that the card is closed or ordered. Preserve the completed verification and give the customer the next safe step.
- **Unsupported replacement delivery, unknown tier, insufficient funds, inactive account, or replacement limit:** do not order; provide the policy-compatible alternative.

## Validation checklist

Before the final response, verify from tool results that every claimed closure has a successful close result and every claimed replacement has a successful order result. Ensure each ordered card has an OPEN checking account, permitted delivery option, exact tier fees, confirmed US address, documented consent, and no active/pending conflicting card. Ensure blocked cards are clearly separated from successfully closed cards.
