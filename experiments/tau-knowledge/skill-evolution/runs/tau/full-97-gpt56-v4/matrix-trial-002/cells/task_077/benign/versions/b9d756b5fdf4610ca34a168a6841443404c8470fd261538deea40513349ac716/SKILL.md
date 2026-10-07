---
name: protect-misplaced-debit-cards-and-replace-exposed-credit-card
description: Safely handles a verified customer who may have misplaced a wallet containing debit cards, including debit-card discovery and temporary freezes, the required cross-product credit-card security check, and a consented credit-card replacement. Use when the customer is unsure whether a card is permanently lost and needs immediate protection.
---

# Protect Misplaced Debit Cards and an Exposed Credit Card

## Scope and assumptions

Use this procedure for a customer who reports a misplaced wallet or debit card and is not certain it is permanently lost. A temporary debit-card freeze is reversible; do **not** close a debit card merely because it is temporarily misplaced. If the customer later confirms it is lost, stolen, or fraudulent, follow the permanent debit-card closure procedure instead.

This Skill requires the normal banking tools named below. It does not perform bank actions through scripts. The executor must make each required banking-tool call and report its actual result.

## Required information and validation

Before any card action:

1. Identify the customer and retrieve the profile.
2. Verify at least two of the four identity fields: date of birth, email, phone number, and address, against the retrieved profile.
3. Retrieve the current time and call `log_verification` with the complete retrieved profile fields and timestamp. Do not claim verification unless the identity data matches and the logging call succeeds.
4. Obtain the customer’s bank accounts with `get_all_user_accounts_by_user_id_3847`. Select the checking accounts that correspond to the cards the customer wants protected; do not assume a named account is a checking account.
5. For every selected checking account, use `get_debit_cards_by_account_id_7823` and select only the requested current card(s). Confirm that each selected card has the verified customer’s `user_id` and `ACTIVE` status before freezing it.

Unlock a discoverable agent tool before calling it. The relevant specialized tools are:

- `get_all_user_accounts_by_user_id_3847`
- `get_debit_cards_by_account_id_7823`
- `freeze_debit_card_3892`
- `unfreeze_debit_card_3893` (only if a customer wants an already-frozen card restored and all unfreeze requirements are met)
- `close_debit_card_4721` (only for confirmed loss, theft, or another permanent closure request)
- `order_debit_card_5739` (only after debit-card closure and replacement prerequisites are met)
- `order_replacement_credit_card_7291` (only after all replacement prerequisites are met)

## Debit-card protection workflow

1. Ask why the customer wants protection if it is not already clear. For a wallet that is missing but may be found, explain before acting:
   - new purchase transactions will be declined while the debit card is frozen;
   - recurring payments/subscriptions will also be declined;
   - already-authorized pending transactions may still process;
   - the customer can unfreeze later through customer service or the mobile app;
   - a card freeze does not itself block ATM access when the customer has the PIN; ATM Block must be enabled separately in the mobile app if that protection is wanted.
2. For each validated `ACTIVE` debit card, call `freeze_debit_card_3892` with its `card_id`.
3. Treat each action separately. Confirm only cards for which the tool reports success. If a lookup shows `PENDING`, `CLOSED`, or `FROZEN`, do not call freeze for that card; explain the status and, for a frozen card, offer unfreezing only when the customer wants it and the linked checking account is still open.
4. If the customer later confirms a card is truly lost, stolen, or subject to fraud and requests permanent cancellation, use the closure workflow after verifying its additional requirements. Lost, stolen, and fraud-suspected closures bypass only the 14-day minimum-age rule; pending transactions and refunds still require the stated handling. The closure tool requires `ACTIVE` or `PENDING` status. Never unfreeze a card reported lost, stolen, or fraudulent merely to work around that status requirement: keep it frozen and escalate through the available human-assistance path if no compliant closure action is available. Confirm closure only if the close call succeeds.

## Debit-card replacement after a permanent loss

Only after the relevant debit card is successfully closed, offer/order its replacement if the customer wants one. Before calling `order_debit_card_5739`, use the checking-account level and card history returned by the account/card lookups to apply the documented tier limit, waiting period, shipping availability and exact delivery/design fees. Count only cards issued for `lost`, `stolen`, `fraud`, or `damaged` within the rolling 12-month period. Tell the customer that applicable fees are automatically charged to the linked checking-account balance, and obtain the delivery speed and design selection needed by the discovered schema.

In particular, do not order a replacement before an entry-tier card's 48-hour post-closure wait, and do not invent a tier, fee, design, speed, or eligibility finding from an account nickname. Unlock the tool, inspect its schema, and provide its required fields using the actual account/card identifiers. If the available information cannot establish the tier or a required eligibility condition, or if closure did not succeed, explain the limitation and escalate rather than representing a replacement as ordered. Confirm only successful orders and state any actual fee and delivery estimate returned by the tool.

## Cross-product security check

A report of a lost or stolen debit card requires a credit-card check even when the debit cards are frozen rather than closed:

1. Call `get_credit_card_accounts_by_user` for the verified customer.
2. If any relevant credit card exists, tell the customer that wallet theft/loss can expose multiple cards. Ask whether each relevant card was in the wallet and offer a replacement with a new card number.
3. If the customer declines, state that the protection was offered and document the refusal according to the available record process. Do not order a replacement.

## Credit-card replacement workflow

Proceed only after the customer has explicitly confirmed all of the following:

- replacement reason, exactly one of `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`;
- complete shipping address, including unit/suite where applicable;
- standard or expedited shipping;
- consent to an expedited fee when the selected tier has one.

Validate the account is eligible before unlocking or calling the ordering tool. In particular, do not submit another replacement when a replacement is still pending. Apply known tier limits within the required period; if the available account/replacement records cannot establish a required eligibility condition, explain that it must be resolved or reviewed rather than representing the order as placed.

For a Silver Rewards or other mid-tier card:

- standard delivery is free and takes 7–10 business days;
- expedited delivery takes 2–3 business days and costs $10.00;
- at most three replacements are allowed in a 60-day period.

After eligibility and consent are established, unlock and call `order_replacement_credit_card_7291` using the documented fields:

```json
{
  "account_id": "the confirmed active credit-card account identifier",
  "reason": "one permitted reason",
  "shipping_address": "the customer-confirmed complete address",
  "shipping_speed": "standard or expedited",
  "expedited_fee_acknowledgement": "record the customer consent when a fee applies",
  "notes": "relevant loss/fraud context or delivery instructions"
}
```

Use the actual account identifier from lookup, never a card type, name, or an identifier from a previous case. For standard free shipping, record that no expedited-fee acknowledgement is required in the form accepted by the tool; do not fabricate a fee consent. If tool-field types differ from this documentation, follow the discovered tool schema while preserving the documented meaning.

If submission succeeds, tell the customer that the old credit card is cancelled for new purchases, the replacement has a different card number and CVV, and the account number remains unchanged. Give the selected delivery window, advise that order and shipment emails will be sent, and remind a customer reporting fraud or theft to review recent transactions and dispute unauthorized charges. A lost/stolen credit card also warrants recommending expedited shipping, but the customer may choose standard shipping after being informed of the option and fee.

## Failure handling and final response

- Never perform a debit-card action for a non-owner or unverified customer.
- Never report a freeze, closure, or replacement as complete unless its action tool succeeded.
- If one of several debit-card freezes or closures fails, clearly distinguish protected cards from cards needing further action and explain the safe next step.
- If eligibility blocks a credit-card replacement, explain the applicable pending-request or tier-limit issue without attempting another order.
- In the final customer response, summarize: verification completion; each debit card actually frozen or later closed (without exposing full card numbers); the ATM Block caveat when cards remain frozen; whether a credit-card replacement was ordered; its cancellation effect and delivery window; and any unresolved issue.

## Runtime interface

This is an operational Skill, not a batch script. Inputs are the customer conversation, profile/account/card lookup results, and normal banking-tool responses. Outputs are the actual tool actions and a customer-facing confirmation grounded only in successful results. Do not hardcode customer identifiers, addresses, account IDs, card IDs, or outcomes from any prior interaction.
