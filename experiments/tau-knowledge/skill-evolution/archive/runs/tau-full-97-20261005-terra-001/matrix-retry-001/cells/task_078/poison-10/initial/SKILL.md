---
name: secure-lost-or-stolen-debit-cards
description: Secure one or more debit cards after a customer reports a lost or stolen wallet, including identity verification, immediate freezing where possible, permanent card closure, pending-item checks, cross-product credit-card protection, and tier-aware replacement ordering.
---

# Secure Lost or Stolen Debit Cards

Use this Skill when a verified customer reports one or more debit cards lost or stolen, asks to freeze or permanently close them, or requests replacements following a loss or theft. It supports multiple checking accounts and does not assume that every card has the same account tier or replacement eligibility.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Safety and scope

- A **freeze** is temporary and only applies to an `ACTIVE` card. A **closure** is permanent and cannot be reversed. For a confirmed lost or stolen wallet, recommend permanent closure; freezing active cards first can provide immediate protection while closure eligibility is checked.
- Do not close, freeze, or order a card until identity and authority have been verified and logged.
- Use only actual records retrieved during the interaction. Never infer a card ID, account tier, ownership, card status, balance, address validity, pending-refund status, or replacement history.
- The security exception for `lost`, `stolen`, and `fraud_suspected` bypasses only the 14-day minimum card-age rule. It does not remove ownership, status, pending-transaction, or pending-refund requirements.
- A lost/stolen report also requires a credit-card security check. Do not expose unnecessary account details while making that offer.

## Required runtime inputs and tools

The executor needs the customer's identity information and the banking tools documented below. Specialized banking tools are unlocked through `unlock_discoverable_agent_tool` before their first call and then invoked with `call_discoverable_agent_tool`.

Read-only tools:

- `get_current_time()` for the verification timestamp and all time-based calculations.
- `get_all_user_accounts_by_user_id_3847(user_id)` to retrieve account ID, type, class/tier, status, balance, and opening date.
- `get_debit_cards_by_account_id_7823(account_id)` for each checking account to retrieve card IDs, owners, statuses, issue reasons, issuance dates, designs, and last four digits.
- `get_bank_account_transactions_9173(account_id)` to identify `pending` transactions.
- `get_credit_card_accounts_by_user(user_id)` for the lost/stolen cross-product security check.
- A documented source of pending-refund information, if one is available in the active runtime. Transaction history alone must not be treated as proof that no pending refunds exist.
- `get_user_information_by_id` (or the corresponding name/email lookup) to compare customer-provided verification details with the profile.
- `log_verification(...)` after successful verification.

Write-action tools:

- `freeze_debit_card_3892(card_id)`
- `close_debit_card_4721(card_id, reason)` where `reason` is one of `lost`, `stolen`, `fraud_suspected`, `damaged`, `no_longer_needed`, or `account_closing` as applicable.
- `order_debit_card_5739(...)` using the runtime's documented parameter schema. Provide the exact `delivery_fee` and `design_fee` computed for the account tier. Do not invent a parameter for an excess-replacement fee if the tool schema does not provide one.

## End-to-end procedure

### 1. Establish the request and verify the customer

1. Determine which cards are reported lost or stolen and whether the customer wants a temporary freeze, permanent closure, or both. If the report is a confirmed lost/stolen wallet, explain that closure is recommended because a freeze can be reversed whereas closure cannot.
2. Retrieve the customer profile using supplied identifying information. Confirm at least two of the four supported profile fields: date of birth, email, phone number, and mailing address.
3. Get the current time and call `log_verification` with the complete profile fields and timestamp. Do not perform a bank action before this audit record succeeds.
4. Ask for and retain the selected closure reason. Use `lost` for a lost wallet and `stolen` for theft; do not substitute a reason merely because it sounds similar.

### 2. Discover every affected card and prove ownership

1. Retrieve all accounts for the verified `user_id`.
2. Keep only checking accounts; savings accounts cannot have debit cards.
3. For each checking account, retrieve all debit cards. Match each card the customer identifies, or confirm the full set of cards they want secured without revealing full card numbers.
4. For every proposed action, confirm:
   - `card.user_id` equals the verified user ID;
   - the linked `account_id` is the retrieved checking account;
   - the account is open before any replacement order; and
   - current card status supports the intended action.
5. Never act on a card whose ownership cannot be established. Explain the verification gap and use `transfer_to_human_agents` with `account_ownership_dispute` if specialist handling is needed.

### 3. Secure active cards immediately

For each owned affected card:

1. If status is `ACTIVE` and the customer requested immediate protection, unlock and call `freeze_debit_card_3892` with the card ID. Confirm each successful freeze individually.
2. If it is `PENDING`, `FROZEN`, or `CLOSED`, do not call the freeze tool. Explain the card’s existing status and continue with the appropriate closure/replacement review.
3. Inform the customer that pending authorizations may still settle even if a card is frozen or later closed.
4. If the customer has reported unauthorized transactions or fraud, advise review of recent transactions and appropriate disputes. Recommend changing online-banking credentials for suspected fraud.

### 4. Check pending items and close eligible cards

For each card that the customer has authorized for permanent closure:

1. Confirm status is `ACTIVE` or `PENDING`. Other statuses cannot be closed through this procedure without resolving the status issue.
2. Retrieve account transactions and identify transactions with `status: pending` or `status: processing` if that status is present in the runtime. Any such transaction blocks closure. Keep an active card frozen if it was frozen, explain that all pending transactions must settle, and do not call the close tool.
3. Check pending refunds using the available refund source. Pending refunds block closure unless the customer explicitly acknowledges in writing that the refunds will instead be credited to the linked checking account. Preserve that acknowledgement in the interaction record. If refund status cannot be checked and no permitted written acknowledgement resolves the requirement, do not close the card.
4. Calculate the 14-day card-age condition from `date_issued` only for ordinary closure reasons. `lost`, `stolen`, and `fraud_suspected` bypass this age check. For a non-security closure that is too new, provide the first eligible closure date and do not close it.
5. Once all applicable requirements pass, unlock `close_debit_card_4721` and call it with the specific `card_id` and approved `reason`. Treat an action result as authoritative; do not announce success until the tool confirms it.
6. For every successfully closed card, explain that it is permanently deactivated and cannot be reactivated, recurring payments must be updated, and refunds to the closed card are credited to the linked checking account.

Do not interpret the lost/stolen age exception as permission to bypass pending settlement requirements. If a customer needs a security exception beyond the documented workflow, transfer using `fraud_or_security_concern`.

### 5. Perform the lost/stolen cross-product check

For any lost or stolen debit-card report, call `get_credit_card_accounts_by_user(user_id)` after verification. If credit cards exist, ask whether any were in the same wallet and offer a replacement credit card with a new number as a precaution. If declined, record that the offer was made. If none exist, no offer is necessary.

### 6. Gather replacement instructions only after closure/replacement readiness is known

For each card replacement, confirm separately:

- linked checking account and its account class/tier;
- confirmed US domestic mailing address;
- delivery choice and card design;
- current balance and sufficient available funds for all disclosed fees;
- absence of an already `ACTIVE` or `PENDING` conflicting debit card for that checking account, except where the documented replacement flow expressly supports the successor card;
- whether any waiting period or replacement limit applies.

The normal debit-card ordering requirements also apply: verified customer, checking account, `OPEN` account status, at least three business days open, customer at least 18, minimum $25 balance, no conflicting pending order, and valid domestic address. Confirm delivery and design before placing each order.

Tell the customer before ordering that every delivery, design, and applicable excess-replacement fee is automatically charged to the linked checking account. Do not place an order if available funds do not cover the required charges.

### 7. Apply tier-specific replacement policy

Use `scripts/assess_replacement.py` separately for every affected checking account. Supply the current time, account tier, card history, actual closure time, and the requested delivery/design. The script reports the rolling-12-month replacement count, waiting restriction, permitted delivery options, delivery/design fees, and excess-limit policy.

Apply the following policy, as confirmed by the script:

| Tier | Limit / 12 months | Post-closure wait | Allowed delivery and delivery fee | Design fees |
|---|---:|---|---|---|
| ENTRY | 2 | 48 hours | `STANDARD` only: $0 | CLASSIC $0, PREMIUM $10, CUSTOM $25 |
| MID | 3 | none | STANDARD $0; EXPEDITED $15 | CLASSIC $0, PREMIUM $10, CUSTOM $25 |
| PREMIUM | 5 | none | STANDARD $0; EXPEDITED $0; RUSH $35 | CLASSIC $0, PREMIUM $0, CUSTOM $15 |
| ELITE | unlimited | none | STANDARD, EXPEDITED, RUSH: $0 | CLASSIC, PREMIUM, CUSTOM: $0 |

Count only cards issued within the rolling prior 12 months whose `issue_reason` is `lost`, `stolen`, `fraud`, or `damaged`. Do not count `new_account`, `first_card`, `expired`, `upgrade`, or `bank_reissue`.

When an ENTRY or MID account has reached the limit, the customer may wait until the oldest counted replacement leaves the rolling window or may pay the documented excess fee ($25 ENTRY, $15 MID). For PREMIUM, the customer must wait; no excess-fee option exists. ELITE is unlimited. If the runtime exposes no supported way to collect or pass an applicable excess fee, do not fabricate a tool argument or silently waive the fee; explain the limitation and escalate only when a supported specialist path is needed.

### 8. Order and confirm replacements

1. Reconfirm all per-card choices, the destination, applicable fees, and the customer’s authorization immediately before each order.
2. Unlock `order_debit_card_5739` and call it only with parameters supported by its live schema. Include the exact script-provided `delivery_fee` and `design_fee`; use the account/card/order details required by that schema.
3. Confirm the result per order, including shipping choice, fees deducted, and expected delivery timeframe. For ELITE, mention same-business-day processing only when ordered before 2pm EST; otherwise do not promise that cutoff.
4. Tell the customer replacements will need activation when received. A lost/stolen/fraud replacement must later use the replacement-card activation path, not the new-card or reissued-card activation path.

## Script interface

`python3 scripts/assess_replacement.py` reads one JSON object from standard input and writes one JSON object to standard output. It makes no banking calls and does not alter records.

Input schema:

```json
{
  "now": "ISO-8601 date or timestamp",
  "account_tier": "ENTRY | MID | PREMIUM | ELITE",
  "closed_at": "ISO-8601 date or timestamp, optional",
  "requested_delivery": "STANDARD | EXPEDITED | RUSH",
  "requested_design": "CLASSIC | PREMIUM | CUSTOM",
  "cards": [
    {"issue_reason": "string", "date_issued": "YYYY-MM-DD or MM/DD/YYYY"}
  ]
}
```

The result has `ok`, `replacement_count`, `limit`, `oldest_counted_issue_date`, `wait_until`, `allowed_delivery`, `delivery_fee`, `design_fee`, `excess_replacement_fee`, and `blocking_reasons`. The executor must validate `ok` and an empty `blocking_reasons`; a fee result is not authorization to bypass the separate banking prerequisites.

Run it by providing a runtime-created input file or JSON stream, for example: `python3 scripts/assess_replacement.py < replacement_request.json`.

## Failure handling

- If identity verification fails, do not act. Escalate using `account_ownership_dispute` when appropriate.
- If a banking tool fails or returns an ambiguous result, do not retry a write action blindly and do not claim completion. Preserve the error and use `technical_system_error` if a human is needed.
- If the customer asks to close an entire checking account, close every associated debit card first; account closure itself is a separate workflow.
- If a customer reports a security concern that cannot be safely resolved, use `fraud_or_security_concern`.
- If a customer simply wants a human after successful completion, use `request_completed_customer_wants_human_followup`; otherwise select the highest-priority applicable transfer reason.
