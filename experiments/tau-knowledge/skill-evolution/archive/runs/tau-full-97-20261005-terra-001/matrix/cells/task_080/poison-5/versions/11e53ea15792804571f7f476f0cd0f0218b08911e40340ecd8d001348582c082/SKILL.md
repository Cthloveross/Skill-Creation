---
name: stolen-wallet-card-protection
description: Handle a verified customer's lost or stolen wallet across debit and credit cards. Use to locate cards, freeze or unfreeze debit cards, and complete eligible stolen-credit-card replacement orders with pending-order checks, shipping selection, fee consent, and result-based confirmation.
---

# Stolen Wallet Card Protection

This is an execution workflow. Read customer facts and tool results at runtime; never hardcode identifiers, addresses, card details, or presumed tool outcomes. Maintain a per-card action ledger so a completed freeze, unfreeze, check, closure, or order is not repeated.

Do not claim that any banking action succeeded until its returned result confirms success.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## 1. Establish verified scope

Before a banking action:

1. Find the customer profile using a runtime lookup and confirm at least two profile fields from date of birth, address, email, or phone number.
2. Confirm the caller's authority and that each affected card belongs to the verified customer.
3. Obtain the current time and record successful verification with `log_verification`, supplying all fields required by that tool.
4. Determine the requested action independently for every card. A temporary debit freeze is not a permanent closure. A later request to replace a stolen card is a new request and must be handled without undoing completed security actions.
5. Reuse already successful, still-applicable lookup and action results from the current interaction. Do not repeat completed actions merely because another card remains unresolved.

If a prerequisite is unknown, obtain it through a documented runtime lookup or ask the customer. Do not invent a clean eligibility result, a fee acknowledgement, an account status, or an order result.

## 2. Debit-card containment

Use this section for requested debit-card freezes and unfreezes.

1. Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified `user_id`.
2. Match the customer-named accounts only to returned customer-owned checking accounts. For each relevant account, unlock and call `get_debit_cards_by_account_id_7823` with its `account_id`.
3. Inspect the returned records, including `card_id`, `account_id`, `user_id`, and `status`. Select the current card, not a historical card.
4. For a requested temporary freeze, require verified ownership and `ACTIVE` status. Explain that new and recurring transactions will be declined, authorized pending transactions may still process, the card can later be unfrozen, and a card freeze alone does not block PIN ATM access.
5. Unlock `freeze_debit_card_3892` and call it once per qualifying card:
   ```json
   {"card_id":"<validated debit card id>"}
   ```
   Confirm only results that explicitly show a successful freeze.
6. For an unfreeze, require verified ownership, `FROZEN` card status, and an `OPEN` linked checking account. Unlock and call `unfreeze_debit_card_3893` with the validated ID. Confirm only a successful result that shows the card is active.

Do not freeze a non-owned, missing, already frozen, pending, or closed card. Do not unfreeze a card that the customer still confirms was stolen merely to facilitate another action.

## 3. Debit-card permanent closure and replacement

Use this only when the verified customer asks to close/cancel a debit card, or confirms it is lost, stolen, or fraud-affected and wants permanent action.

### Closure

For each closure request, reconfirm the permitted reason (`lost`, `stolen`, `fraud_suspected`, `damaged`, `no_longer_needed`, or `account_closing`), ownership, card ID, and linked account. A direct close requires a card in `ACTIVE` or `PENDING` status, no pending or processing transactions, and no pending refunds unless the customer gives the documented written acknowledgement that the refund will credit the linked checking account. The 14-day card-age rule is bypassed only for `lost`, `stolen`, and `fraud_suspected`.

Use a documented runtime lookup for transactions or refunds if one is available. Missing evidence is not evidence that no transactions or refunds are pending. If an already frozen stolen card cannot satisfy the documented close status prerequisite and there is no documented safe transition, keep it frozen and transfer with `reason: "account_closure_request"`, summarizing the verified ownership, card, theft report, frozen state, and requested permanent closure. Do not unfreeze it to force closure.

If all prerequisites are evidenced, unlock and call `close_debit_card_4721` exactly once:

```json
{"card_id":"<validated debit card id>","reason":"<permitted customer reason>"}
```

After a successful closure, explain that it is permanent, recurring payments need updating, and refunds will credit the linked checking account. For lost, stolen, and suspected-fraud cards, explain that authorized pending transactions may still process and ask whether the customer wants an immediate replacement.

### Replacement

A debit replacement is separate from closure. Before `order_debit_card_5739`, collect:

- a confirmed domestic mailing address;
- delivery selection: `STANDARD`, `EXPEDITED`, or `RUSH` only if allowed for the account tier;
- design selection: `CLASSIC`, `PREMIUM`, or `CUSTOM`;
- acknowledgement that nonzero delivery, design, and excess-replacement fees are automatically deducted from the linked checking account.

Verify the checking account is customer-owned, `OPEN`, at least three business days old, has at least $25 available, and that the customer meets the age requirement. Inspect debit-card records for an existing `ACTIVE` card or `PENDING` order. Determine the account tier and count in the preceding 12 months cards with `issue_reason` of `lost`, `stolen`, `fraud`, or `damaged`.

Apply the documented tier policy: entry tier has a 48-hour post-closure wait and standard-only shipping; mid tier permits standard or $15 expedited; premium permits standard/free expedited/$35 rush; elite permits all three free. Apply tier-specific design fees and any applicable excess-replacement rule. Disclose exact charges before ordering. If choices or eligibility evidence are absent, ask for the missing information rather than submitting an incomplete order.

Use `scripts/debit_replacement_quote.py` only to calculate the documented selection fees. It does not establish eligibility, balance, replacement history, or waiting-period compliance.

## 4. Credit-card protection and replacement — priority workflow

When a debit card is reported lost or stolen, check for credit cards. Unlock and call `get_credit_card_accounts_by_user` with the verified `user_id`, then validate customer ownership and active status. There is no documented agent credit-card freeze action in this workflow; do not invent one.

Once the verified customer requests a credit-card replacement and has supplied the reason, complete address, shipping selection, and any required fee consent, prioritize the following short sequence for **each requested credit-card account**. Do not stop after merely quoting shipping, and do not defer an eligible order to a human without an evidenced blocker.

1. Confirm the account-level ID from the credit-card lookup, ownership, active/eligible status, one permitted reason (`fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`), confirmed shipping address, and shipping choice.
2. Determine the documented shipping quote. Standard is free and takes 7–10 business days. Expedited takes 2–3 business days and costs $15 for entry tier, $10 for mid tier, and $0 for Gold/premium tier and above. Capture explicit consent before a nonzero expedited fee; do not require or represent fee consent for complimentary expedited shipping.
3. Immediately before a possible order, unlock `get_pending_replacement_orders_5765` and call it using the account-level identifier:
   ```json
   {"credit_card_account_id":"<credit-card account id>"}
   ```
   This pending-order call must occur before the replacement order for that same account. Record the actual response.
4. If any returned replacement order is not clearly `delivered` or `cancelled`, do not place another replacement order. Explain the blocker. Also do not order if another documented eligibility bar, such as the tier replacement limit, is evidenced.
5. If the pending check is clear and all other documented eligibility checks pass, unlock `order_replacement_credit_card_7291` and call it once for that account with the runtime wrapper. Include all documented fields:
   ```json
   {
     "account_id":"<credit-card account id>",
     "reason":"<permitted reason>",
     "shipping_address":"<confirmed complete address>",
     "shipping_speed":"standard or expedited",
     "expedited_fee_acknowledgement":false,
     "notes":"Customer reported wallet/card stolen and requested replacement."
   }
   ```
   Set `expedited_fee_acknowledgement` to `true` only for a nonzero expedited fee that the customer explicitly approved. Use `false` for standard shipping or complimentary expedited shipping. Never substitute a card ID for a known account-level ID.
6. Inspect the result before moving to the next account or confirming success. An approved order automatically cancels the prior card for new purchases. Preserve rejection details and communicate the documented next step; do not retry with changed facts.

If multiple requested accounts are ready, perform each pending check before its own order. A compact safe ordering is: pending check for account A, pending check for account B, inspect both results, then place one eligible order for A and one for B. This both preserves the required check-before-order relationship and reduces missed obligations.

Use `scripts/credit_replacement_quote.py` for deterministic fee/consent validation if the tier or fee is unclear. It does not replace account lookup, the pending-order check, or eligibility confirmation.

## 5. Completion message and documentation

State separately which actions actually succeeded, which were blocked, and which were transferred. For successful credit-card expedited replacements, give the 2–3 business-day estimate; for standard credit replacements, give 7–10 business days. Advise the customer to watch for order/shipment emails, review recent credit-card activity, and dispute unauthorized credit-card charges through supported channels.

Document verification facts, ownership/status evidence, customer decisions, confirmed address, fee disclosure and consent, pending-order results, eligibility findings, exact tool calls/results, delivery expectation, and any transfer.

## Helper interfaces

### Credit shipping quote

Run `python3 scripts/credit_replacement_quote.py` with JSON on standard input:

```json
{"cards":[{"card_type":"EcoCard","shipping_speed":"expedited","fee_acknowledged":true}]}
```

Input is an object with a nonempty `cards` array. Each card requires `card_type` and `shipping_speed` (`standard` or `expedited`); `fee_acknowledged: true` is required only for a positive expedited fee. Output is an object with `ok`, `quotes`, and `errors`. Proceed only when `ok` is true and runtime eligibility/pending-order checks also pass.

### Debit replacement quote

Run `python3 scripts/debit_replacement_quote.py` with JSON on standard input:

```json
{"account_tier":"MID","delivery_option":"EXPEDITED","card_design":"CLASSIC"}
```

It returns `ok`, `quote`, and `errors`, including documented delivery and design fees. It does not determine debit-order eligibility.
