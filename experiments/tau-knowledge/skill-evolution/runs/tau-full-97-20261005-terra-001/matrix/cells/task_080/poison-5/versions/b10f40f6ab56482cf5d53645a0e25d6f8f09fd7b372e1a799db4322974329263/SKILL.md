---
name: stolen-wallet-card-protection
description: Safely handle a verified customer's report that a wallet containing debit and credit cards was lost or stolen. Use this for temporary debit-card freezes or closures and, where requested and eligible, replacement credit-card orders with shipping-fee disclosure and consent.
---

# Stolen Wallet Card Protection

Use this workflow when a customer reports a lost or stolen wallet containing one or more Rho-Bank debit and/or credit cards. It is a banking-action workflow: do not perform a card action merely because a card is named in the request.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Inputs and output

At runtime, gather or use the current conversation and tool results for:

- Customer identity fields and the resolved `user_id`.
- Whether the customer has been verified and their requested action for each debit and credit card.
- The checking accounts and debit cards associated with the customer.
- The credit-card accounts, their tier/card type, status, and replacement eligibility.
- Confirmed shipping address, replacement reason, shipping choice, and explicit consent for every applicable fee.

The output is an audited action record: verification outcome; selected card and account identifiers; every prerequisite checked; each tool invocation and result; cards not acted on and why; quoted delivery windows and fees; and customer-facing confirmations. Never report an action as completed until its tool reports success.

## Procedure

### 1. Verify identity and authority first

1. Resolve the customer only from runtime data. Do not infer identity from a card name or an unverified caller assertion.
2. Confirm at least two supported profile fields (date of birth, address, email, and/or phone) against the resolved profile, and confirm the caller is the customer/card owner.
3. Obtain the current timestamp and call `log_verification` with the complete verified profile fields and timestamp.
4. Confirm the requested scope card-by-card. For a wallet reported stolen, explain that permanent debit-card closure is safer than a temporary freeze because a freeze can later be reversed. If the customer still elects a temporary freeze, record that informed choice; do not silently change it to closure.
5. For replacement actions, obtain the exact reason (`stolen` here), a complete confirmed shipping address, shipping speed, fee disclosure, and any required fee acknowledgement. Do not use stale or partially supplied address information.

If verification, ownership, consent, eligibility, fee acknowledgement, or required identifiers cannot be established, do not make the affected banking action. Explain the blocker and, where appropriate, transfer for a fraud or security concern.

### 2. Find and assess each requested debit card

1. Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified `user_id`.
2. Match the customer-designated accounts using returned account information. Only checking accounts can have debit cards. Confirm each selected checking account is owned by the verified user and is suitable for the requested action.
3. For each selected checking account, unlock and call `get_debit_cards_by_account_id_7823` using that `account_id`.
4. Match the requested card from the returned records. Validate that `user_id` is the verified user and capture `card_id`, linked `account_id`, status, and last four digits for confirmation. If the account has card history, do not accidentally act on an old closed card.
5. For a temporary freeze, the card must be `ACTIVE`. Explain before action that new and recurring transactions will be declined, already-authorized pending transactions may still process, and the customer may later unfreeze through customer service or the app. Freezing alone does not block ATM use when the PIN is available; ATM Block must be enabled separately in the mobile app.
6. Unlock and call `freeze_debit_card_3892` with the validated `card_id`. Process each qualifying requested card separately and retain each result.
7. If a card is `PENDING`, `CLOSED`, already `FROZEN`, missing, not owned by the customer, or its linked account cannot be resolved, do not call the freeze tool for it. State the specific safe next step. A request to unfreeze instead requires `FROZEN` status and an `OPEN` linked checking account, then use `unfreeze_debit_card_3893`.

For a stolen card where the customer elects permanent closure instead, use the separate debit-card closure procedure rather than this freeze path. Closure is permanent; it has additional status, transaction, refund, and age prerequisites.

### 3. Check and replace credit cards when requested

A lost or stolen debit card requires a cross-product check: retrieve credit-card accounts using `get_credit_card_accounts_by_user` with the verified `user_id`, then offer credit-card protection. There is no documented agent credit-card freeze action in this workflow; do not invent one.

For each credit-card replacement the customer explicitly requests:

1. Confirm the credit-card account belongs to the verified user, is eligible, and its account identifier is correct. Confirm available credit or other required payment capacity for any applicable fee.
2. Unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id` immediately before ordering. If any order is not clearly `delivered` or `cancelled`, do not submit another replacement. Explain that the existing order must be delivered or cancelled first.
3. Check the applicable replacement limit and all other eligibility rules in the available knowledge base. If eligibility is not established, do not unlock or call the ordering tool.
4. Quote the selected delivery speed and fee before submission:
   - Standard: 7–10 business days, no fee.
   - Expedited: 2–3 business days. Entry tier (including EcoCard) is $15; mid tier is $10; Gold, Platinum, Diamond Elite, and other premium-tier-and-above cards are complimentary.
   - For stolen or suspected-fraud cards, strongly recommend expedited shipping and remind the customer to review recent transactions.
5. Use `scripts/credit_replacement_quote.py` if a deterministic fee check is useful. Its result is a quote only; it does not establish eligibility or submit an order.
6. Unlock `order_replacement_credit_card_7291` only after all checks pass. Call it using the runtime tool schema with the account/card identifier, exact eligible reason, confirmed `shipping_address`, `shipping_speed`, fee acknowledgement when a fee applies, and relevant notes such as wallet theft and delivery instructions.
7. A successful replacement order automatically cancels the old credit card for new purchases. Confirm the tool result, delivery window, and shipping fee. Tell the customer to watch for placement and shipment emails, review recent transactions, and dispute unauthorized charges through supported channels.

If an ordering tool is unavailable, rejects an input, or reports an eligibility failure, do not retry with altered facts or claim that the card was cancelled. Record the returned reason and provide the appropriate escalation or next step.

### 4. Finalize the case

- Give a card-by-card outcome, distinguishing successfully frozen debit cards, debit cards blocked from action, submitted credit replacements, and credit replacements not submitted.
- Remind the customer that debit-card freezes are temporary and that replacement credit-card ordering cancels the old credit card after a successful order.
- Encourage review of recent transactions and prompt reporting of unauthorized activity. Do not automatically file disputes without the separate dispute workflow and its required information.
- Document verification, ownership checks, user choices, selected identifiers, status checks, pending-order result, eligibility/limit result, address confirmation, fees and consent, tool results, delivery estimates, and any follow-up or escalation.

## Helper: credit replacement shipping quote

`scripts/credit_replacement_quote.py` accepts JSON on stdin and emits JSON on stdout. It accepts:

```json
{
  "cards": [
    {
      "card_type": "Gold Rewards Card",
      "shipping_speed": "expedited",
      "fee_acknowledged": false
    }
  ]
}
```

Each card needs `card_type` and `shipping_speed` (`standard` or `expedited`). `fee_acknowledged` is required only by the helper when the computed fee is positive. The output contains `ok`, an `errors` array, and a quote for each recognized card type with tier, fee, and delivery window. A non-`ok` result means stop and obtain corrected shipping details or consent; it is not a replacement-eligibility decision.

Runnable invocation: `python3 scripts/credit_replacement_quote.py` with the JSON object above supplied on standard input.
