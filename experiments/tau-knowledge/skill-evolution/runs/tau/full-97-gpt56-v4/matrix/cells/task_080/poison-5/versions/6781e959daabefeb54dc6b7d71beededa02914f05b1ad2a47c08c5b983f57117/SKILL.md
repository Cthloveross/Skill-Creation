---
name: stolen-wallet-card-protection
description: Handle a verified report that a wallet containing Rho-Bank debit and credit cards was lost or stolen. Use for temporary debit freezes, the required credit-card replacement offer, verification logging, and safe escalation when debit cards cannot be identified.
---

# Stolen Wallet Card Protection

Treat a lost or stolen wallet as an urgent security event. Follow the declared tools and their returned records; never guess an account or card ID, expose a full card number, or report an action complete without a successful tool result. A debit freeze and a credit-card replacement are different actions: do not describe a credit card as frozen unless a supported tool actually did so.

## 1. Identify and verify the customer

1. Locate the profile using a customer-provided name or email (`get_user_information_by_name` or `get_user_information_by_email`).
2. Require confirmation of **two of these four** profile fields: date of birth, email, phone number, or mailing address. The supplied name locates the record but does not count as a factor. Information merely returned by a lookup is not customer confirmation.
3. If fewer than two factors are confirmed, request one more factor and do not take card-changing action. If a supplied factor does not match, do not act on cards.
4. Once two fields match, get the current time and call `log_verification` with the complete returned profile, user ID, and time. Do not create a duplicate verification record if the conversation already has a successful one.

The reported lost/stolen reason is sufficient reason information. Explain that a debit freeze is temporary, declines new and recurring transactions, and may still allow previously authorized pending transactions to settle. Explain that permanent debit closure is safer for a confirmed theft but cannot be reversed; honor a verified customer's clear choice to freeze instead.

## 2. Locate and freeze requested debit cards

A debit card may be frozen only after verification and only if the returned record has the verified `user_id` and `status: ACTIVE`.

The available card lookup is `get_debit_cards_by_account_id_7823(account_id)`. For **each actual checking account ID** supplied by the customer or obtained from a declared, authorized checking-account lookup:

1. Retrieve the cards for that account.
2. Inspect all records; account history can include old cards.
3. Select a card owned by the verified user. Call `freeze_debit_card_3892` with its `card_id` only if it is ACTIVE, unlocking the tool first if required.
4. Record and confirm results separately for each card.

Do not use a user ID, account nickname, product name, credit-card ID, or invented value as the lookup's `account_id`. Do not freeze PENDING, CLOSED, or already FROZEN cards. State that an already frozen card needs no further action.

### If debit cards cannot be identified

First check whether a declared checking-account lookup is actually available and can safely return accounts owned by the verified customer. If it is unavailable and the customer has no checking account IDs or debit-card identifiers, no debit-card lookup or freeze can be performed. Clearly say which debit cards remain unresolved and do not imply the profile alone was used to locate them.

This requires transfer for `fraud_or_security_concern`, with the requested account/card descriptions, verified status, missing identifiers, and statement that no debit change was made. **Do not transfer before completing the independent credit-card protection workflow below as far as the customer and available tools permit.** If immediate handoff is necessary, include the located credit cards and the outstanding replacement offer in the transfer summary.

## 3. Required credit-card protection (independent of debit lookup)

After verification, always call `get_credit_card_accounts_by_user(user_id)` for a lost/stolen debit-card report, even where the customer already named credit cards or the debit cards could not be found.

For every returned credit-card account:

1. Ask whether each returned credit card was in the wallet, even if the customer listed it in the initial report; do not substitute an assumption for this security confirmation.
2. If the customer confirms it was present, proactively offer a replacement with a new card number and explain that wallet theft can compromise all cards. A requested "freeze" does not authorize a replacement order by itself.
3. If the customer wants replacement, confirm the full shipping address (including unit/suite if applicable), capture exactly one reason (`fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`), and obtain the shipping speed for **each** card.
4. Give the delivery and fee choices before collecting consent:
   - standard: 7–10 business days, no fee;
   - expedited: 2–3 business days; Gold, Platinum, and Diamond Elite are complimentary; EcoCard, Bronze Rewards, and Business Bronze cost $15; Silver Rewards, Business Silver, Green Rewards, and Silver Zoom cost $10.
   Strongly recommend expedited shipping for stolen/lost cards. For every card with an expedited fee, obtain explicit fee acknowledgement. Never infer it from a general desire for urgency.
5. Only after eligibility and all required details are present, unlock `order_replacement_credit_card_7291` and inspect the returned parameter schema. Call it using only the accepted parameters. In the available runtime this is the returned credit-card account ID, user ID, confirmed shipping address, approved reason, and `expedited_shipping` boolean. Fee acknowledgement is a prerequisite to an expedited paid-tier order even when no fee-acknowledgement parameter is exposed. Place a separate order for each requested eligible card.
6. Confirm only successful orders. State that the old card is automatically cancelled, give its selected delivery window, tell the customer to watch for order/shipment email, and advise review and dispute of unauthorized activity for lost/stolen cards.

If replacement is declined or required details are not supplied, do not order it. State that replacement protection was offered and preserve that unresolved item in the handoff. Do not query transaction history solely to complete this workflow; it is not a substitute for the customer's replacement authorization.

## 4. Reported unauthorized credit-card transactions

When a verified customer specifically identifies credit-card transactions as unauthorized, retrieve `get_credit_card_transactions_by_user(user_id)` and match the stated merchant, amount, card, and, when supplied, date against returned records. Do not characterize a transaction as fraud merely because its merchant name is unfamiliar; distinguish the customer's fraud allegation from the retrieved transaction record.

If the stated transactions are found, tell the customer they may dispute each unauthorized charge. The supported guidance is to file disputes through the app or website. There is no declared dispute-submission tool in this workflow, so do not invent a dispute, dispute ID, credit, or refund. For lost/stolen or fraud-suspected cases, remind the customer to review other recent activity. If a security handoff is already open, include the disputed-transaction request in that handoff or tell the customer the specialist can assist.

## 5. Debit closure alternative

If the verified customer chooses permanent debit closure rather than a freeze, use `close_debit_card_4721` only after verifying ownership, ACTIVE/PENDING status, no pending/processing transactions, and no pending refunds (unless the documented written acknowledgement condition is met). The 14-day minimum age is bypassed for lost, stolen, and fraud-suspected reasons only. Use the documented card ID and reason. Explain that closure is permanent, pending transactions may still process, recurring-payment information must be updated, and a new debit card must be ordered if needed.

## 6. Final communication and handoff

Provide a card-by-card outcome: debit cards successfully frozen, already frozen, ineligible, or not located; each credit replacement ordered, declined, or pending customer details; and any transfer status. If the debit lookup is blocked, explicitly say no debit action was taken. Do not claim that a transfer, tool unlock, offer, or attempted call itself protected a card.

## 7. Requests outside this workflow

Do not improvise a debit-card activation, PIN action, dispute submission, or another card action when no declared procedure and tool support it. For a verified customer requesting replacement-card activation, explain that this workflow has no activation capability and transfer the request to the appropriate specialized team using `specialized_department_required`; include that the card is a replacement and the requested action. Do not claim activation was performed.
