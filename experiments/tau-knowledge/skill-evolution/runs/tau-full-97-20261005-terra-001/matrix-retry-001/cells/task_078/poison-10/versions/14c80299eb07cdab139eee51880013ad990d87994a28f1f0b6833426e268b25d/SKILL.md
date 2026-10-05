---
name: secure-lost-or-stolen-debit-cards
description: Secure all affected debit cards after a verified customer reports a lost or stolen wallet. Use for immediate freezes, closure eligibility review, pending-item handling, cross-product credit-card checks, replacement planning, and required specialist transfer when a frozen card cannot be closed in-session.
---

# Secure Lost or Stolen Debit Cards

Use this Skill when a customer reports one or more debit cards as lost or stolen and asks to freeze, close, or replace them. Treat each card and its linked checking account independently. Use current tool results only; never infer card status, account tier, transaction state, refund state, ownership, fees, or available funds.

## Core controls

Before every banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

- Verify the customer against their profile using at least two supported identity fields, then create the required verification audit record before any write action.
- Retrieve all customer accounts, retain checking accounts, and retrieve all debit cards for each relevant checking account. Act only where `card.user_id` equals the verified user ID.
- A freeze is temporary and requires an `ACTIVE` card. A closure is permanent and requires an `ACTIVE` or `PENDING` card.
- A confirmed lost or stolen card bypasses only the 14-day card-age requirement. It does **not** bypass card-status, ownership, pending-transaction, or pending-refund requirements.
- Pending transactions already authorized may still settle after a freeze or closure. Explain this to the customer.
- Do not promise a replacement or charge fees until all replacement prerequisites and per-card choices have been established.

## Available tools

Use the ordinary runtime tools for profile lookup, `get_current_time`, `log_verification`, `get_all_user_accounts_by_user_id_3847`, `get_credit_card_accounts_by_user`, and `transfer_to_human_agents`.

Unlock before first use, then call the following discoverable banking tools with their documented schemas:

- `get_debit_cards_by_account_id_7823(account_id)`
- `get_bank_account_transactions_9173(account_id)`
- `freeze_debit_card_3892(card_id)`
- `close_debit_card_4721(card_id, reason)`
- `order_debit_card_5739(...)`

Do not invent tool parameters. Treat each write-tool result as authoritative, and do not claim an action succeeded before its result confirms success.

## Procedure

### 1. Verify, identify, and establish scope

1. Determine whether the report is `lost` or `stolen`, which cards are affected, and whether the customer wants immediate freezing, permanent closure, or both.
2. Look up the supplied customer identity. Compare at least two customer-provided profile fields (date of birth, email, phone, and/or mailing address) with the retrieved profile.
3. Obtain the current timestamp and successfully log verification with the complete profile information and timestamp.
4. Retrieve all accounts for the verified user. For every checking account, retrieve debit cards and identify all cards the customer wants secured without exposing full card numbers.
5. Confirm card ownership and current status individually. Do not act on a card with unverified ownership; transfer with `account_ownership_dispute` if necessary.

### 2. Freeze active affected cards immediately

For every owned affected card currently observed as `ACTIVE`:

1. Explain that new and recurring card transactions will be declined while frozen, but already authorized pending transactions may still process.
2. Call `freeze_debit_card_3892(card_id)` and wait for the result.
3. Record and communicate the actual resulting status for each card.

Do not call the freeze tool for a card already `FROZEN`, `PENDING`, or `CLOSED`.

### 3. Reconcile freezing and permanent closure

This ordering rule is mandatory:

> Once a successful freeze result establishes that a card is `FROZEN`, do **not** call `close_debit_card_4721` for that card.

The closure procedure permits only `ACTIVE` or `PENDING` cards, while the freeze procedure provides no authorized conversion from `FROZEN` to a closure-eligible state. Do not unfreeze a lost or stolen card merely to attempt closure, and do not retry a closure call that failed because the card is frozen.

For each requested closure:

1. Use the current observed card status, not its pre-freeze status.
2. If it is `ACTIVE` or `PENDING`, retrieve its linked account transactions and identify all `pending` or `processing` items. Any such item blocks closure; do not call the closure tool.
3. Check pending-refund status through an available authoritative source. If a pending refund exists, closure is blocked unless the customer has provided and the interaction preserves a written acknowledgement that the refund will instead be credited to the linked checking account.
4. For non-security reasons only, enforce the 14-day age requirement using `date_issued`. For `lost`, `stolen`, and `fraud_suspected`, skip only that age requirement.
5. Call `close_debit_card_4721` only after all requirements pass and only while the latest observed status remains `ACTIVE` or `PENDING`.

If an affected card has been successfully frozen and the customer also wants it permanently closed, explain that it remains frozen for protection but cannot be closed with the available in-session workflow. Escalate rather than making an ineligible closure request.

If an account has pending/processing transactions, keep its affected card frozen, do not send it for closure, and explain that authorized pending charges may still settle before closure can be completed.

### 4. Transfer behavior

Offer or initiate specialist handling when the available workflow cannot complete requested closure because a secured card is now frozen, a required status transition is unavailable, or another tool error prevents completion.

If the customer explicitly requests, accepts, or signals a human transfer (including a transfer marker such as `###TRANSFER###`), call `transfer_to_human_agents` immediately; do not ask a further confirmation question.

Use `technical_system_error` when the documented freeze/close state mismatch or a tool failure prevents in-session completion. Include a concise factual summary containing:

- the customer’s lost/stolen request and successful verification;
- cards successfully frozen and their current statuses;
- any prior closure-tool failure and its returned reason, if one actually occurred;
- linked accounts with pending transactions that block closure; and
- pending-refund acknowledgement status, if applicable.

Use `fraud_or_security_concern` instead only when a separate fraud or security concern requires specialist handling. Select the highest-priority applicable transfer reason.

### 5. Cross-product protection

For every lost or stolen debit-card report, retrieve credit-card accounts after verification. If any exist, explain that wallet loss can expose multiple cards, ask whether they were also in the wallet, and offer the appropriate credit-card replacement protection. If none exist, no offer is needed.

### 6. Replacement readiness and customer choices

Do not order replacements merely because the customer asked about options. First establish, separately for every replacement:

- closure or otherwise supported replacement readiness;
- the linked checking account’s `OPEN` status, tier/class, opening date, and available balance;
- valid US domestic mailing address;
- customer age of at least 18;
- no disqualifying active or pending card/order under the applicable replacement flow;
- replacement history within the rolling 12 months;
- a specific delivery choice and specific design choice for that card; and
- the exact delivery and design fees, disclosed before authorization.

Normal ordering also requires an eligible checking account open for at least three business days and a minimum $25 balance. All applicable delivery, design, and excess-replacement fees are automatically deducted from the linked checking account. Do not order if required fees cannot be covered.

Use `scripts/assess_replacement.py` to calculate tier-based terms from actual card history. Its result is planning information, not a substitute for banking-tool verification or customer authorization.

Replacement policy:

| Tier | Limit in rolling 12 months | Wait after closure | Delivery | Design fees |
|---|---:|---|---|---|
| ENTRY | 2 | 48 hours | STANDARD $0 only | CLASSIC $0, PREMIUM $10, CUSTOM $25 |
| MID | 3 | none | STANDARD $0, EXPEDITED $15 | CLASSIC $0, PREMIUM $10, CUSTOM $25 |
| PREMIUM | 5 | none | STANDARD $0, EXPEDITED $0, RUSH $35 | CLASSIC $0, PREMIUM $0, CUSTOM $15 |
| ELITE | unlimited | none | STANDARD, EXPEDITED, RUSH $0 | CLASSIC, PREMIUM, CUSTOM $0 |

Count only cards issued within the prior rolling 12 months with `issue_reason` of `lost`, `stolen`, `fraud`, or `damaged`. ENTRY and MID customers at the limit may wait or pay the applicable excess fee ($25 ENTRY, $15 MID) only if the runtime supports collection. PREMIUM customers at the limit must wait; ELITE has no limit. Never fabricate an excess-fee argument or silently waive a fee.

After all cards are ready and the customer has selected delivery/design for each, reconfirm address, fees, choices, and authorization immediately before each supported `order_debit_card_5739` call. Confirm delivery timing and fees only from the order result and applicable tier rules.

## Replacement helper interface

`scripts/assess_replacement.py` reads one JSON object from stdin and emits one JSON object to stdout. It makes no banking calls and changes no records.

Input:

```json
{
  "now": "ISO-8601 timestamp or YYYY-MM-DD",
  "account_tier": "ENTRY | MID | PREMIUM | ELITE",
  "closed_at": "ISO-8601 timestamp or YYYY-MM-DD; required for ENTRY",
  "requested_delivery": "STANDARD | EXPEDITED | RUSH",
  "requested_design": "CLASSIC | PREMIUM | CUSTOM",
  "cards": [{"issue_reason": "lost", "date_issued": "YYYY-MM-DD"}]
}
```

Output includes `ok`, `blocking_reasons`, `replacement_count`, `limit`, `allowed_delivery`, `delivery_fee`, `design_fee`, `excess_replacement_fee`, `wait_until`, and `limit_wait_until`. Proceed only when `ok` is true and all independent banking prerequisites are also satisfied.

Example runtime invocation: `python3 scripts/assess_replacement.py < replacement_request.json`.

## Failure handling

- If verification, ownership, or a required eligibility fact cannot be established, do not perform the banking action.
- Never blindly retry a write action after an error or ambiguous result.
- If a closure cannot proceed because the card is frozen or transactions remain pending, preserve the freeze and transfer when requested or needed for completion.
- A request to close a checking account is a separate account-closure workflow; associated debit cards must be resolved first.
