---
name: stolen-wallet-card-protection
description: Handle a verified customer's lost or stolen wallet involving debit cards and credit cards. Use for debit-card freezes/unfreezes and requested credit-card replacement orders, including pending-order eligibility checks, shipping selection, fee consent, and post-order safety guidance.
---

# Stolen Wallet Card Protection

Use this workflow for a customer reporting a lost or stolen wallet or cards. It covers actual banking actions, not merely advice. Complete actions only after their documented prerequisites are satisfied and never state that an action succeeded until its tool result confirms success.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Runtime inputs and required outcome

Use only the current conversation and runtime tool results to obtain:

- A resolved customer profile and `user_id`.
- Verification evidence, card ownership, and the requested action for every affected card.
- Selected checking accounts, debit-card records, and current card statuses.
- Credit-card account identifiers, card tiers, current status, and pending-replacement results.
- A complete confirmed shipping address, one allowed replacement reason, shipping choice, and explicit consent for each applicable expedited fee.

Produce a card-by-card outcome that records verification, prerequisites, tool calls/results, any action not taken and why, quoted fees/delivery windows, and customer-facing confirmation.

## 1. Verify identity and determine scope

1. Resolve the customer from a runtime profile lookup; do not identify a caller solely from card names.
2. Verify at least two profile fields from date of birth, address, email, or phone against the profile. Confirm the caller is the owner/authorized customer.
3. Get the current time and call `log_verification` with all required profile fields and `time_verified`.
4. Confirm the customer’s requested action separately for each debit and credit card. A stolen debit card is generally safer to close, but if the verified customer expressly requests a temporary freeze, perform the freeze workflow rather than silently changing the instruction.
5. Before any credit replacement, confirm the full delivery address, the exact allowed reason, shipping speed, disclosed charge, and explicit acknowledgement of every charge.

If identity, authority, ownership, required data, consent, or eligibility is missing, do not perform the affected action. Explain the blocker and escalate security concerns when appropriate.

## 2. Locate and act on requested debit cards

1. Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified `user_id`.
2. Match the customer-named accounts from runtime data. Confirm each selected account is a checking account owned by the verified customer.
3. For each selected checking account, unlock and call `get_debit_cards_by_account_id_7823` with that `account_id`.
4. Select the current requested card only after confirming its `card_id`, linked account, owner `user_id`, and status. Do not act on historical closed cards.
5. For a temporary freeze, require `ACTIVE` status. Before freezing, explain that new and recurring transactions are declined, authorized pending transactions may still process, the card can later be unfrozen, and freezing alone does not block PIN ATM access.
6. Unlock `freeze_debit_card_3892`, then call it once per qualifying card with `{"card_id": "<validated card id>"}`. Retain and confirm each successful result.
7. For unfreeze requests, require verified ownership, card status `FROZEN`, and an `OPEN` linked checking account. Unlock and call `unfreeze_debit_card_3893` with the validated `card_id`, then confirm the successful active status.

Do not freeze a missing, non-owned, non-`ACTIVE`, or already frozen card. For a requested permanent debit-card closure, use the separate closure workflow and satisfy its pending transaction, refund, and other prerequisites.

## 3. Replace requested stolen credit cards

A lost or stolen debit card requires a cross-product check. Unlock and call `get_credit_card_accounts_by_user` with the verified `user_id`, identify accounts owned by that customer, and offer replacement protection. This workflow documents no agent credit-card freeze tool; do not invent one.

For **each** credit-card account for which the verified customer requests a replacement, complete the following sequence separately. Do not skip the pending-order check merely because another account was checked.

1. Confirm ownership, active/eligible account status, correct account-level identifier, requested reason, confirmed shipping address, shipping selection, applicable fee disclosure/consent, and any available-credit or other documented eligibility requirements.
2. Unlock `get_pending_replacement_orders_5765` and call it immediately before ordering with:
   ```json
   {"credit_card_account_id":"<credit-card account id>"}
   ```
3. Review the returned orders. If any replacement is not clearly `delivered` or `cancelled`, stop for that account: do not unlock/order another replacement; explain that the existing replacement must be delivered or cancelled. Also apply any documented tier replacement limit or other eligibility bar.
4. Quote the delivery choice before submitting:
   - `standard`: 7–10 business days and no fee.
   - `expedited`: 2–3 business days. Entry-tier cards, including EcoCard, cost $15; mid-tier cards cost $10; Gold and other premium-tier-and-above cards are complimentary.
   - For `stolen` or `fraud_suspected`, recommend expedited shipping and advise the customer to review recent transactions.
5. After a clear pending-order result and all eligibility checks pass, unlock `order_replacement_credit_card_7291` and submit exactly one order for that eligible account. Use the runtime wrapper with arguments shaped as follows:
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
   Use one allowed reason only: `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`. Set `expedited_fee_acknowledgement` to `true` when the selected tier has an expedited fee and the customer expressly approves it. For complimentary expedited shipping, provide the field only if accepted by the runtime schema; never represent an unapproved fee as acknowledged.
6. Inspect the order result. Only a successful result means the order was submitted. A successful replacement automatically cancels the old card for new purchases. If the tool rejects the request or reports ineligibility, preserve the returned reason, do not retry using altered facts, and provide the appropriate next step.

Use `scripts/credit_replacement_quote.py` to validate a shipping quote and fee acknowledgement before calling the ordering tool when useful. It is informational only: it neither checks account eligibility nor submits an order.

## 4. Close the interaction

- State separately which debit cards were successfully frozen or unfrozen and which credit replacements were successfully submitted.
- For successful expedited credit replacements, give the 2–3 business-day delivery expectation; standard replacements take 7–10 business days.
- Advise the customer to watch for replacement and shipment emails, review credit-card activity, and dispute unauthorized credit-card transactions through the supported channels.
- Do not automatically file a dispute without its separate workflow and required facts.
- Document verification, ownership/status checks, customer decisions, pending-order outcome for each requested credit account, eligibility/limit results, address confirmation, fee acknowledgement, tool results, delivery estimate, and any escalation.

## Helper: credit replacement shipping quote

Run with `python3 scripts/credit_replacement_quote.py` and provide JSON on stdin:

```json
{
  "cards": [
    {
      "card_type": "EcoCard",
      "shipping_speed": "expedited",
      "fee_acknowledged": true
    }
  ]
}
```

Input must be an object with a nonempty `cards` array. Every card needs `card_type` and `shipping_speed` (`standard` or `expedited`); `fee_acknowledged: true` is required by the helper for a positive expedited fee. It emits:

```json
{"ok":true,"quotes":[{"card_type":"...","tier":"...","shipping_fee":"$...","delivery_window":"...","fee_acknowledgement_required":true}],"errors":[]}
```

Proceed only if `ok` is true and separately confirm pending-order and replacement eligibility at runtime.
