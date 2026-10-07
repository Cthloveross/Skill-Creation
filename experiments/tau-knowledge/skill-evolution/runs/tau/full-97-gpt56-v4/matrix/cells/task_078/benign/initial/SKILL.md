---
name: secure-lost-debit-cards-and-arrange-replacements
description: Securely handle a verified customer's report that one or more debit cards are lost or stolen: identify the requested cards, close them permanently, perform the required cross-product check, and arrange policy-compliant replacements when the customer has made the required choices and eligibility is confirmed.
---

# Lost or Stolen Debit Cards

Use this Skill when a customer says their debit card is lost or stolen, particularly when several cards or checking accounts may be affected. A confirmed lost/stolen card should be **closed**, not merely frozen. A closure is permanent and cannot be undone.

## Required tools to unlock

Unlock only the tools needed for the case through `unlock_discoverable_agent_tool`, then call them through `call_discoverable_agent_tool`:

- `get_all_user_accounts_by_user_id_3847` — retrieve the customer's accounts.
- `get_debit_cards_by_account_id_7823` — retrieve card history for each checking account.
- `get_bank_account_transactions_9173` — check each requested card's linked account for pending transactions.
- `close_debit_card_4721` — permanently close an eligible card; supply `card_id` and reason `lost` or `stolen` as applicable.
- `order_debit_card_5739` — order a replacement only after all ordering requirements, waiting periods, customer selections, and fees are satisfied. Supply the exact tool parameters, including the policy-derived `delivery_fee` and `design_fee`.

Also use the normal `get_credit_card_accounts_by_user` tool for the required wallet-security check. Use `get_current_time` and `log_verification` for successful identity verification.

## Verification and authorization

1. Locate the customer and confirm the target `user_id`.
2. Verify identity using two of date of birth, email, phone number, and address. Do not treat a name alone as verification. Obtain the current time and call `log_verification` with the complete retrieved customer record and the current timestamp after two fields are confirmed.
3. Establish that the customer wants permanent closure and the applicable reason (`lost` or `stolen`). Explain that closure is permanent. If they only want a temporary lock or have not confirmed loss/theft, use the freeze process instead of this Skill.
4. Confirm a replacement mailing address and obtain delivery/design preferences. Do not assume that an earlier card's preference applies to a different card unless the customer explicitly made it apply to all of them.

## Identify exactly which cards are in scope

1. Retrieve all accounts for the verified user. Retain only checking accounts that can have debit cards.
2. For every potentially requested checking account, retrieve its debit cards. Confirm every target card has a matching `user_id`; never act on another owner's card.
3. Use last four digits or linked-account identification if available. If the customer cannot identify cards, only infer the targets when the request and lookup unambiguously identify them (for example, precisely the stated number of eligible active cards). Otherwise present only safe, non-sensitive distinctions (such as linked account or final four) and obtain clarification before closing any ambiguous card.
4. A card must be `ACTIVE` or `PENDING` to be closed. Do not try to close a `CLOSED` or `FROZEN` card; explain its current state and determine whether another requested card remains.

## Closure eligibility and execution

For each selected card, check the following before closing:

- The linked account's transaction history has no `pending` transaction. Pending or processing transactions must settle first. A lost/stolen report does **not** waive this condition; explain that already-authorized transactions can still post.
- There are no pending refunds. If a relevant pending refund is found, do not close until it processes (normally 3–5 business days) unless the customer gives the required written acknowledgement that it will be credited to the linked checking account.
- Normal cards must have been active for at least 14 days from `date_issued`. For `lost`, `stolen`, and `fraud_suspected`, this card-age rule is bypassed.

If an unmet condition blocks one card, do not call its closure tool. Continue separately with other independently eligible requested cards only where that is consistent with the customer's request; clearly report each blocked card and what must happen next.

For each eligible confirmed lost/stolen card, call `close_debit_card_4721` with its `card_id` and the matching reason. Never repeat a close call after an unknown or failed result. Record each confirmed result before proceeding.

Immediately after handling the lost/stolen report, check the customer's Rho-Bank credit-card accounts. If one or more exist, ask whether they were also in the lost wallet and offer a replacement credit card as a security precaution. If none exist, say no additional Rho-Bank credit-card protection is needed. For fraud concerns, also recommend review of recent transactions, disputes for unauthorized charges, and a password change.

## Replacement eligibility

Treat each replacement as a separate order connected to its just-closed card and linked checking account. Before ordering, confirm all of these:

- The customer remains verified and the linked account is a checking account, `OPEN`, open at least three business days, and has a balance of at least $25.
- There is no active debit card and no `PENDING` debit-card order/card conflict for that account after closure.
- The domestic mailing address is confirmed.
- The replacement history is within tier limits. Count cards issued in the rolling 12 months whose `issue_reason` is `lost`, `stolen`, `fraud`, or `damaged`; do not count `new_account`, `first_card`, `expired`, `upgrade`, or `bank_reissue`.
- The tier's waiting period after closure has elapsed. Entry tier has a 48-hour wait; Mid, Premium, and Elite have no wait.

If a limit or waiting period prevents an order, do not place it. Tell the customer the applicable wait/alternative. For Entry and Mid, an excess-replacement fee may be an alternative after the normal limit is exceeded ($25 Entry, $15 Mid); Premium must wait after its limit. Obtain explicit agreement before any excess fee, and use the ordering tool only if it supports the policy-required charge. Never invent an unsupported tool argument.

## Delivery, design, and exact charges

All applicable delivery, design, and excess fees are automatically deducted from the linked checking account at order time. Before calling the order tool, state the exact charge for each account/card and obtain confirmation if the customer has not already explicitly approved that charge.

Apply the tier policy exactly:

| Tier | Delivery choices and fee | Design fees |
|---|---|---|
| Entry | STANDARD only, $0 | CLASSIC $0; PREMIUM $10; CUSTOM $25 |
| Mid | STANDARD $0; EXPEDITED $15 | CLASSIC $0; PREMIUM $10; CUSTOM $25 |
| Premium | STANDARD $0; EXPEDITED $0; RUSH $35 | CLASSIC $0; PREMIUM $0; CUSTOM $15 |
| Elite | STANDARD/EXPEDITED/RUSH $0 | CLASSIC/PREMIUM/CUSTOM all $0 |

If the customer asks for an unavailable shipping method, explain the permitted method and obtain a replacement selection. If they request the best no-cost design, do not silently choose an extra-fee design: select PREMIUM only where it is complimentary and the customer has authorized that interpretation; otherwise use or confirm CLASSIC. CUSTOM requires an uploaded image and any applicable approval; do not select it merely because it is free.

When all checks and informed consent are complete, call `order_debit_card_5739` with the selected delivery/design, confirmed address, and exact `delivery_fee` and `design_fee` required by the linked account tier. Do not place an order based on a fee estimate or before a required wait expires.

## Customer-facing completion

Give a per-card result, separating successfully closed, successfully ordered, and blocked/pending items. For every successfully closed card, state:

- it is permanently deactivated and cannot be reactivated;
- pending authorized transactions may still settle;
- refunds to the closed card will credit to the linked checking account;
- recurring merchants must be updated with new payment details.

For each replacement actually ordered, state the selected delivery service, applicable charged fees, expected delivery timeframe when provided by policy/tool, and that it will need activation. A lost/stolen/fraud replacement uses `activate_debit_card_8292` after receipt, subject to normal activation verification and card-detail requirements.

If no action can be safely completed because identity, ownership, requested-card identity, address, payment consent, eligibility, or tool capability is missing, explain the precise missing item and stop rather than guessing or attempting an unsafe action.
