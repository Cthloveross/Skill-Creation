---
name: secure-lost-or-stolen-debit-cards
description: Handle a verified customer's lost or stolen debit-card report: promptly freeze eligible cards with the required advance notice, evaluate permanent closure safely, perform cross-product protection, plan replacements, and transfer unresolved work to a human specialist.
---

# Secure Lost or Stolen Debit Cards

Use this Skill when a customer reports a lost or stolen debit card or wallet and asks to freeze, close, cancel, or replace one or more debit cards. Treat each card and its linked checking account independently. Use only current tool results; do not infer ownership, card status, pending items, account tier, fees, address validity, or successful completion.

## Controls and action order

Before a banking write action, establish customer identity, authority, ownership, applicable product eligibility, balances, fees, limits, required customer selections, and confirmation requirements.

For a lost-wallet report, do not stop after finding or unlocking a documented tool. After identity verification, execute the operational checklist below using the available tools. A discoverable tool must first be unlocked with `unlock_discoverable_agent_tool`, then invoked through `call_discoverable_agent_tool` with its inner arguments encoded as a JSON object string.

1. Verify the customer against their retrieved profile using at least two customer-provided identity fields.
2. Obtain the current time and create the required verification audit record with `log_verification` before any write action.
3. Retrieve all accounts with `get_all_user_accounts_by_user_id_3847`.
4. Unlock and call `get_debit_cards_by_account_id_7823` for every relevant checking account.
5. Verify each card belongs to the verified user and inspect its current status.
6. Give the required freeze-effects notice before the first freeze call, then freeze every affected owned `ACTIVE` card.
7. Check credit-card accounts with `get_credit_card_accounts_by_user` as part of the lost/stolen cross-product protocol.

If a required tool call actually returns an error or needed facts cannot be safely established, do not fabricate an action or claim it occurred. When the customer explicitly requests a human handoff, immediately invoke `transfer_to_human_agents`; do not merely offer a transfer or end the interaction.

## Tool use

Ordinary runtime tools used by this workflow include:

- `get_current_time`
- profile lookup by supplied name, email, or user ID
- `log_verification`
- `get_all_user_accounts_by_user_id_3847`
- `get_credit_card_accounts_by_user`
- `transfer_to_human_agents`

Unlock before first use and then call these discoverable tools using their documented schemas:

- `get_debit_cards_by_account_id_7823(account_id)`
- `get_bank_account_transactions_9173(account_id)`
- `freeze_debit_card_3892(card_id)`
- `close_debit_card_4721(card_id, reason)`
- `order_debit_card_5739(...)`

Do not invent parameters for any tool. Wait for every write-tool result and report success only if that result confirms it.

## 1. Verification and scope

1. Establish whether the report is lost or stolen, which cards are affected, and whether the current request is a temporary freeze, permanent closure, replacement, or a combination.
2. Look up the customer and compare at least two customer-supplied profile fields, such as date of birth, mailing address, email, or phone number, against the returned profile.
3. Get the current timestamp and successfully call `log_verification` with all required profile fields and that timestamp.
4. Retrieve all accounts for the verified user. Retain checking accounts and retrieve their debit-card records.
5. Act only on cards whose `user_id` matches the verified user ID. Do not expose full card numbers.
6. For every affected card, record the latest observed status. A card must be `ACTIVE` to freeze; it must be `ACTIVE` or `PENDING` to be considered for closure.

If ownership cannot be established and specialist handling is needed, use the applicable transfer reason such as `account_ownership_dispute`.

## 2. Freeze affected active cards

A freeze is temporary, requires a verified owner, and is available only for an `ACTIVE` card. The customer's lost-wallet report supplies the reason for freezing; do not delay immediate protection by asking redundant questions after verification.

Before the **first** `freeze_debit_card_3892` call, give a customer-facing notice covering all of these points:

> Before I freeze the cards: all new transactions and recurring payments or subscriptions will be declined while they are frozen. Pending transactions that were already authorized may still process or settle. The freeze is temporary, and you can unfreeze the cards later through customer service or the mobile app.

The notice must appear before tool use; a tool result or post-freeze confirmation is too late.

Then:

1. Unlock `freeze_debit_card_3892` if necessary.
2. Call it once for each affected, owned card whose latest observed status is `ACTIVE`.
3. Wait for and inspect every result.
4. Confirm only cards whose results actually show a successful freeze. State their resulting status accurately.

Do not call the freeze tool for `FROZEN`, `PENDING`, or `CLOSED` cards. Do not claim that a failed or missing result protected a card.

## 3. Permanent closure after a freeze

Closure is permanent. It requires verified ownership, a current status of `ACTIVE` or `PENDING`, no pending/processing transactions, and no pending refunds unless the customer has provided a written acknowledgement that the refund will be credited to the linked checking account. Lost or stolen status bypasses only the 14-day card-age requirement.

**Mandatory reconciliation rule:** once a successful freeze result establishes that a card is `FROZEN`, never call `close_debit_card_4721` for that card. The documented closure workflow permits only `ACTIVE` or `PENDING`, and the available freezing workflow does not provide an authorized frozen-to-closure-eligible transition. Do not unfreeze a lost or stolen card merely to attempt closure, and do not retry a close call rejected because a card is frozen.

For a closure request involving a card not known to be frozen:

1. Confirm the latest card status is `ACTIVE` or `PENDING`.
2. Unlock and call `get_bank_account_transactions_9173` for the linked account. Pending or processing transactions block closure. Explain that already-authorized pending charges may still settle.
3. Check pending-refund status through an authoritative available source. Do not close while a refund is pending unless the required written acknowledgement has been obtained and preserved.
4. For non-security reasons, calculate the 14-day minimum age from `date_issued`. For `lost`, `stolen`, and `fraud_suspected`, skip only this age test.
5. Call `close_debit_card_4721(card_id, reason)` only when every prerequisite has passed and the latest status remains `ACTIVE` or `PENDING`.

When a customer requests permanent closure after successful freezes, preserve the freezes, explain the documented status limitation, and arrange specialist handling rather than issuing an ineligible closure request.

## 4. Human transfer

Check every new customer message for an explicit request to transfer, accept a transfer, or marker such as `###TRANSFER###`. Such a request is an immediate action trigger: call `transfer_to_human_agents` before further questions or explanations, wait for its result, and report only the confirmed outcome.

Also transfer unresolved permanent-closure work after successful freezes when the available documented process has no authorized `FROZEN`-to-eligible transition.

Choose the highest-priority supported reason code based on actual facts. `technical_system_error` is reserved for an actual system error or outage preventing completion; a documented workflow or status limitation is not a technical system error.

For a frozen-card closure limitation where no more specific reason applies, use `reason: "other"` and a detailed factual summary. Include, when known:

- the lost or stolen report and successful verification;
- cards successfully frozen and their `FROZEN` status;
- the customer's later permanent-closure request;
- that closure requires `ACTIVE` or `PENDING` status and no authorized transition is available;
- pending transactions or refund-acknowledgement status, if observed; and
- any previous tool failure and its actual returned reason, if one occurred.

Never describe a workflow limitation as an outage. A transfer call is not successful unless its tool result confirms success.

## 5. Cross-product protection

After verification, call `get_credit_card_accounts_by_user` for every lost or stolen debit-card report. If credit cards exist, explain that wallet loss can expose multiple cards, ask whether they were in the wallet, and offer appropriate replacement protection. If none exist, no offer is needed.

## 6. Replacement planning and ordering

Do not order replacements merely because the customer requested options or replacements. Determine readiness separately for every card and linked checking account. Before ordering, establish:

- supported closure or replacement readiness;
- verified customer ownership and age of at least 18;
- an `OPEN` checking account that has been open at least three business days;
- account tier/class and sufficient available balance, including the $25 minimum balance requirement;
- valid domestic US mailing address;
- no conflicting active or pending debit card/order under the applicable flow;
- replacement history in the rolling prior 12 months;
- a delivery choice and design choice for each card; and
- exact applicable delivery, design, and any excess-replacement fees disclosed before final authorization.

All applicable fees are automatically charged to the linked checking account when ordered. Do not promise unsupported delivery choices or silently waive a fee. Reconfirm per-card choices, address, fees, and authorization immediately before each supported `order_debit_card_5739` call.

Use `scripts/assess_replacement.py` for deterministic tier/history planning. It does not make banking calls, establish account eligibility, collect fees, or authorize an order.

| Tier | 12-month limit | Post-closure wait | Delivery choices and fee | Design fees |
|---|---:|---|---|---|
| ENTRY | 2 | 48 hours | STANDARD $0 | CLASSIC $0; PREMIUM $10; CUSTOM $25 |
| MID | 3 | none | STANDARD $0; EXPEDITED $15 | CLASSIC $0; PREMIUM $10; CUSTOM $25 |
| PREMIUM | 5 | none | STANDARD $0; EXPEDITED $0; RUSH $35 | CLASSIC $0; PREMIUM $0; CUSTOM $15 |
| ELITE | unlimited | none | STANDARD, EXPEDITED, RUSH $0 | CLASSIC, PREMIUM, CUSTOM $0 |

Count only cards issued in the last rolling 12 months with `issue_reason` of `lost`, `stolen`, `fraud`, or `damaged`. At the ENTRY or MID limit, an excess fee may be possible only if the available ordering/payment workflow supports it and the customer has been informed and authorized it. PREMIUM customers at their limit must wait; ELITE has no stated limit.

## Replacement helper interface

`scripts/assess_replacement.py` reads one JSON object from stdin and writes one JSON object to stdout. It performs no banking actions.

Input schema:

```json
{
  "now": "ISO-8601 timestamp, YYYY-MM-DD, or MM/DD/YYYY",
  "account_tier": "ENTRY | MID | PREMIUM | ELITE",
  "closed_at": "date/timestamp; required for ENTRY",
  "requested_delivery": "STANDARD | EXPEDITED | RUSH",
  "requested_design": "CLASSIC | PREMIUM | CUSTOM",
  "cards": [{"issue_reason": "lost", "date_issued": "YYYY-MM-DD"}]
}
```

Output includes `ok`, `blocking_reasons`, `replacement_count`, `limit`, `allowed_delivery`, `delivery_fee`, `design_fee`, `excess_replacement_fee`, `wait_until`, and `limit_wait_until`. Treat `ok` as only a planning result; independently verify all banking requirements and authorization before ordering.

Example: `python3 scripts/assess_replacement.py < replacement_request.json`

## Failure handling

- Do not perform a write action when verification, ownership, status, or another required fact is missing.
- Never blindly retry a failed or ambiguous write action.
- If pending transactions block closure, retain the freeze and explain that authorized pending charges may still settle.
- If the customer explicitly requests a transfer, call the transfer tool immediately even when other work is incomplete.
- Closing a checking account is a separate workflow; resolve associated debit cards first.
