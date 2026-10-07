---
name: stolen-wallet-card-protection
description: Execute a verified customer's lost or stolen wallet response across debit and credit cards. Use for debit-card freeze, unfreeze, closure, and replacement requests; and for credit-card replacement orders requiring address, shipping, fee consent, pending-order checks, and confirmation.
---

# Stolen Wallet Card Protection

Use this Skill when a customer reports a lost or stolen wallet or cards. It is an action workflow, not advice-only. Complete a card action only after the applicable prerequisites are evidenced in the conversation or tool results. Never say an action succeeded unless its tool result confirms success.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Runtime inputs and outcome

Obtain at runtime rather than hardcoding:

- Customer profile, `user_id`, identity verification, and ownership authority.
- Affected checking accounts, debit-card records, card statuses, and credit-card accounts.
- The customer's current instruction for each card: freeze, unfreeze, close, or replace.
- For every replacement: an allowed reason, confirmed complete US address, delivery selection, all applicable disclosed fees and consent, and eligibility evidence.

Maintain a card-by-card case record containing checks performed, tool calls and results, completed actions, blockers, fees, and delivery expectations.

## 1. Verify identity, authority, and scope

1. Resolve the customer through a runtime profile lookup; do not identify a caller solely from account or card names.
2. Verify at least two profile fields from date of birth, address, email, or phone against the profile and confirm the caller is the owner or authorized party.
3. Obtain the current time and call `log_verification` using the complete required profile fields and `time_verified`.
4. Identify every affected debit and credit card and confirm the requested action for each. Do not silently convert a requested freeze into a closure. If the customer later confirms a card is stolen and asks for permanent closure, treat that as a new closure request.
5. Before any replacement order, confirm the complete shipping address, one permitted reason, selected shipping speed, every applicable fee, and explicit consent for a nonzero fee.

If verification, authority, ownership, consent, eligibility, or required card details are absent, do not perform the affected banking action. State the concrete blocker and take a documented escalation action when required.

## 2. Locate debit cards and perform temporary freezes or unfreezes

1. Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified `user_id`.
2. Match the customer-named accounts only from returned runtime data. Confirm each selected account is a checking account, is owned by the verified customer, and has the needed status.
3. For every selected checking account, unlock and call `get_debit_cards_by_account_id_7823` with its `account_id`.
4. From the result, select the current requested card only after validating `card_id`, linked account, `user_id`, and current status. Do not act on a historical closed card.
5. For a requested temporary freeze, require `ACTIVE` status. Before the action, explain that new and recurring transactions will be declined, authorized pending transactions may still process, the card can later be unfrozen, and freezing alone does not block PIN ATM access.
6. Unlock `freeze_debit_card_3892`, then call it once for every qualifying requested card with:
   ```json
   {"card_id":"<validated debit card id>"}
   ```
   Retain the result and confirm only successful freezes.
7. For an unfreeze request, require verified ownership, `FROZEN` card status, and an `OPEN` linked checking account. Unlock and call `unfreeze_debit_card_3893` with the validated `card_id`; confirm the tool result indicates the card is active and ready for use.

Do not freeze a card that is missing, non-owned, non-`ACTIVE`, or already frozen. Do not unfreeze a card merely because the customer found it if security facts still require a permanent stolen-card response.

## 3. Permanent debit-card closure and replacement

When the verified customer confirms a debit card is lost, stolen, or affected by suspected fraud and requests closure, follow this section; do not stop at a claim that the closure workflow is unavailable.

### Closure procedure

For each card requested for closure:

1. Reconfirm ownership, `card_id`, linked checking account, and one closure reason: `lost`, `stolen`, `fraud_suspected`, `damaged`, `no_longer_needed`, or `account_closing`.
2. Determine whether the card meets closure prerequisites: it must be `ACTIVE` or `PENDING`; there must be no pending/processing transactions and no pending refunds, unless the customer provides the documented written acknowledgement that refunds will credit to the linked checking account. For ordinary closures, also validate the 14-day age requirement from `date_issued`; `lost`, `stolen`, and `fraud_suspected` bypass only that age requirement.
3. Use documented runtime lookup capabilities to obtain pending transaction and refund evidence where available. Do not invent a lookup, a clean result, or customer acknowledgement. Pending transactions or missing required refund handling block closure and must be explained.
4. A card already frozen is secure, but frozen status is not among the documented closure-eligible statuses. Do not unfreeze a confirmed stolen card merely to force a closure. Clearly document this status blocker and use `transfer_to_human_agents` with `reason: "account_closure_request"` and a concise summary requesting secure permanent closure if no documented supported transition is available.
5. If all requirements are met, unlock `close_debit_card_4721` and call it once with:
   ```json
   {"card_id":"<validated debit card id>","reason":"stolen"}
   ```
   Substitute the customer's exact permitted reason when different. Inspect the result before confirming closure. A successful closure is permanent; explain that recurring payments need updating and any refunds will credit to the linked checking account.
6. For lost, stolen, or suspected-fraud cards, explain that authorized pending transactions can still process, ask whether immediate replacement is desired, and encourage transaction review and disputes where appropriate. Do not auto-file a dispute without its separate required facts and workflow.

### Debit replacement procedure

A debit replacement is separate from closure. Before ordering, collect a delivery selection (`STANDARD`, `EXPEDITED`, or `RUSH` where allowed), card design (`CLASSIC`, `PREMIUM`, or `CUSTOM`), confirmed domestic address, and acknowledgement that applicable delivery, design, and excess-replacement fees are automatically deducted from the linked checking account.

For each requested debit replacement:

1. Confirm identity and that the linked account is a customer-owned `checking` account, `OPEN`, at least three business days old, has at least $25 available, and has a valid US domestic address. Confirm age eligibility from the profile.
2. Check debit-card records for an existing `ACTIVE` card and any `PENDING` replacement. Do not order if the documented one-active-card or pending-order restriction applies.
3. Determine the account tier and replacement history from all card records. Count cards issued in the rolling 12 months with `issue_reason` of `lost`, `stolen`, `fraud`, or `damaged`. Apply the tier limit and waiting period after closure. Entry-tier replacements have a 48-hour wait and standard shipping only; mid-tier and above have no post-closure wait; premium and elite shipping and design fees follow the documented tier schedule.
4. Disclose exact delivery, design, and any excess replacement fee before ordering, and verify the account has sufficient funds for automatic deductions.
5. If eligible and all selections are known, unlock and call `order_debit_card_5739` using the runtime schema and the documented exact delivery and design fee amounts. Inspect the result before confirming the order. If delivery or design choices are missing, ask for those choices rather than pretending an order was submitted.
6. State the confirmed delivery expectation and charges. New debit cards activate on first PIN use; the existing card remains active until replacement activation only where it has not already been permanently closed.

Use `scripts/debit_replacement_quote.py` to validate tier delivery/design choices and quoted fee amounts before an order. It does not establish account eligibility, calculate account age, or submit an order.

## 4. Requested stolen credit-card replacements

A lost or stolen debit card requires a cross-product check. Unlock and call `get_credit_card_accounts_by_user` with the verified `user_id`, validate account ownership and active status, and offer replacement protection for cards that may have been in the wallet. There is no documented agent credit-card freeze action in this workflow; do not invent one.

For **each** credit-card account for which the verified customer requests replacement, process independently and in this order:

1. Confirm the correct account-level identifier, ownership, eligible/active status, allowed reason, confirmed address, selected shipping speed, applicable fee disclosure and consent, and any available-credit or documented replacement-limit requirements.
2. Unlock `get_pending_replacement_orders_5765` and call it for that account immediately before its potential order:
   ```json
   {"credit_card_account_id":"<credit-card account id>"}
   ```
3. Review the response. If any order is not clearly `delivered` or `cancelled`, do not submit another replacement. Explain that the current order must be delivered or cancelled. Apply all documented tier replacement limits and other eligibility bars.
4. Quote shipping before submission:
   - `standard`: free, 7–10 business days.
   - `expedited`: 2–3 business days; entry tier is $15, mid tier is $10, and Gold/premium tier and above are complimentary.
   - For `stolen` or `fraud_suspected`, recommend expedited shipping and remind the customer to review transactions.
5. After a clear pending-order result and satisfied eligibility, unlock `order_replacement_credit_card_7291` and call it exactly once for that eligible account using the runtime wrapper. Provide the documented fields:
   ```json
   {
     "account_id":"<credit-card account id>",
     "reason":"stolen",
     "shipping_address":"<confirmed complete address>",
     "shipping_speed":"expedited",
     "expedited_fee_acknowledgement":true,
     "notes":"Wallet reported stolen; customer requested replacement."
   }
   ```
   Use exactly one allowed reason: `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`. Set `expedited_fee_acknowledgement` to `true` only when expedited shipping has a nonzero fee and the customer expressly approves it. For complimentary expedited shipping, use the runtime schema's appropriate no-fee value; never represent a fee as approved when none was consented to.
6. Inspect the result. Only a successful result confirms an order. A successful credit replacement automatically cancels the old card for new purchases. If rejected, preserve the actual error and provide the corresponding next step; do not retry with altered facts.

Use `scripts/credit_replacement_quote.py` to validate documented credit shipping fees and consent before calling the order tool. The helper is informational only and does not check pending orders or replacement eligibility.

## 5. Close the interaction

- State separately every debit freeze, unfreeze, closure, escalation, debit replacement, and credit replacement that actually succeeded.
- Give 2–3 business days for successful expedited credit replacements and 7–10 business days for standard credit replacements. Use the selected debit delivery option's documented timing for debit orders.
- Advise the customer to monitor replacement and shipment emails, review credit-card transactions, and dispute unauthorized credit-card activity through supported channels.
- Document verification, ownership/status evidence, customer decisions, all pending-order outcomes, prerequisite and eligibility findings, address confirmation, fees and consent, tool results, delivery estimates, and any transfer.

## Helper: credit replacement shipping quote

Run `python3 scripts/credit_replacement_quote.py` with JSON on stdin:

```json
{"cards":[{"card_type":"EcoCard","shipping_speed":"expedited","fee_acknowledged":true}]}
```

Input must be an object containing a nonempty `cards` array. Each entry requires `card_type` and `shipping_speed` (`standard` or `expedited`). For a positive expedited fee, `fee_acknowledged` must be `true`. Output is:

```json
{"ok":true,"quotes":[{"card_type":"...","tier":"...","shipping_fee":"$...","delivery_window":"...","fee_acknowledgement_required":true}],"errors":[]}
```

Proceed only if `ok` is true and runtime pending-order and eligibility checks independently pass.

## Helper: debit replacement quote

Run `python3 scripts/debit_replacement_quote.py` with JSON on stdin:

```json
{"account_tier":"MID","delivery_option":"EXPEDITED","card_design":"CLASSIC"}
```

Input requires `account_tier` (`ENTRY`, `MID`, `PREMIUM`, or `ELITE`), `delivery_option`, and `card_design`. Output reports whether the selection is permitted and the exact documented `delivery_fee` and `design_fee`. It does not include a possible excess replacement fee and does not determine eligibility.
