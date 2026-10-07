---
name: secure-stolen-wallet-cards
version: 1.0.0
description: Secure a verified customer's debit cards after a wallet loss or theft, locate related credit-card accounts, and offer the documented credit-card replacement protection workflow. Use when a customer reports a lost/stolen wallet or asks to urgently secure multiple debit and credit cards.
---

# Secure Stolen-Wallet Cards

## Scope and safety boundary

Use this Skill for a customer who reports a wallet or debit card as lost or stolen and wants cards secured. A debit-card **freeze** is a temporary, reversible lock. A debit-card **closure** is permanent and cannot be reversed. For confirmed loss or theft, recommend closure rather than a temporary freeze, but only perform the action the verified owner authorizes and only when its documented prerequisites are met.

No documented agent workflow in this Skill freezes or locks a credit card. Do not represent a credit-card replacement order as a reversible freeze. For a lost/stolen wallet, check the customer's credit-card accounts and proactively offer the documented replacement process.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Inputs and prerequisites

Obtain or establish:

- The customer's identity information and a candidate `user_id`.
- The customer's request, including whether the card or wallet is confirmed lost/stolen and whether the customer authorizes a temporary debit freeze or permanent debit closure.
- The debit-card accounts/cards to secure. Do not infer that an old, closed, or unrelated card is a target.
- For any credit-card replacement order: the selected credit-card account/card identifier, exact reason, confirmed shipping address, shipping speed, applicable fee acknowledgement, and order confirmation.

### Identity and authority

1. Locate the customer using a customer-supplied identifier, such as name, email, or phone number.
2. Confirm **two of the four** profile fields—date of birth, email, phone number, and address—using standard verification procedures. A lookup result alone is not customer confirmation.
3. Retrieve the profile by `user_id` as needed and call `log_verification` only after two fields are confirmed. Supply the required complete profile fields and a timestamp from `get_current_time`.
4. Confirm the requester is the owner: every selected debit card's `user_id` must equal the verified `user_id`; every selected credit-card account must belong to that user.

If identity, authority, ownership, or the requested card selection cannot be established, do not take a banking action. Explain what information is needed or transfer/escalate according to the available support process.

## Locate the customer’s products

1. Call `get_all_user_accounts_by_user_id_3847(user_id)`.
2. From returned checking accounts, call `get_debit_cards_by_account_id_7823(account_id)`. The debit-card lookup returns the card identifier, linked account, cardholder user ID, last four digits, and status. Match requested account/card descriptions with the customer; ask a clarifying question if more than one possible card exists.
3. Call `get_credit_card_accounts_by_user(user_id)`, including when the customer initially asks only about debit cards, because a reported stolen wallet triggers the cross-product security check.
4. Review account/card status, ownership, and any required eligibility data before proposing or taking an action. Use `scripts/plan_card_security.py` only to validate a supplied inventory and prepare a review checklist; it does not verify identity or execute banking actions.

## Debit-card temporary freeze workflow

Use this only if the verified card owner chooses a temporary freeze rather than closure.

### Eligibility

For each card, verify all of the following:

- Customer identity is verified and logged.
- Card `user_id` matches the verified customer.
- The card is currently `ACTIVE`.
- The target card and requested action have been confirmed.

Do not freeze `PENDING`, `CLOSED`, or already `FROZEN` cards. Explain the status and next step instead.

### Required disclosure

Before freezing, inform the customer:

- All new transactions will be declined while the card is frozen.
- Recurring payments and subscriptions will also be declined.
- Pending transactions already authorized may still process.
- The customer can unfreeze at any time through customer service or the mobile app.
- Freezing does not affect ATM access when the customer has the PIN; an ATM block must be enabled separately in the mobile app.
- If the card is not unfrozen within 90 days, a reminder notification is sent.

### Action and confirmation

For each eligible, confirmed debit card, use the normal banking tool `freeze_debit_card_3892` with its `card_id`. Do not issue a blanket action without enumerating the eligible target cards. Confirm each successful freeze. If an action fails or produces an ambiguous result, do not claim the card is protected; report the result and escalate or use the available support process.

## Debit-card closure alternative for confirmed theft

For a card confirmed lost, stolen, or subject to suspected fraud, recommend permanent closure rather than a temporary freeze. Closure is irreversible. The documented closure reason must be exactly one of `lost`, `stolen`, `fraud_suspected`, `damaged`, `no_longer_needed`, or `account_closing`.

Before calling `close_debit_card_4721(card_id, reason)`, verify the owner, card status (`ACTIVE` or `PENDING`), no pending/processing transactions, and no pending refunds unless the customer provides the documented written acknowledgement that refunds will credit the linked checking account. Check card age from `date_issued`; the 14-day minimum is bypassed for `lost`, `stolen`, and `fraud_suspected`, but other stated requirements still apply. For loss/theft/fraud, explain that pending authorized transactions may still process, offer debit-card replacement through the applicable standard process, and advise fraud victims to review transactions and file disputes. After a successful closure, explain that the card cannot be reactivated and recurring merchants need new payment details.

## Credit-card protection and replacement workflow

A reported lost or stolen debit card/wallet requires a credit-card check. If the verified customer has credit cards, tell them that a stolen wallet can expose multiple cards, ask whether each active credit card was also in the wallet, and offer a replacement with a new card number. Record a decline according to the customer-record process when applicable.

Do not place a replacement order merely because it was offered. Obtain the owner's explicit order authorization and complete these checks for the selected credit-card account:

1. Confirm identity, ownership, the correct active credit-card account/card, current product eligibility, and required account/card details.
2. Confirm the shipping address, including apartment or suite information.
3. Record exactly one reason: `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`.
4. Ask whether standard or expedited shipping is desired. Standard delivery is 7–10 business days with no fee. Expedited delivery is 2–3 business days; entry-tier fee is $15.00, mid-tier fee is $10.00, and premium-tier-and-above is complimentary. Strongly recommend expedited shipping for `fraud_suspected` or `stolen`.
5. Obtain acknowledgement of any applicable expedited fee.
6. Confirm no pending replacement order blocks a new request. Use `get_pending_replacement_orders_5765` with the credit-card account ID when available. A pending or shipped order blocks another replacement; delivered and cancelled orders are final. Also enforce applicable replacement-limit and other eligibility rules before ordering.

When eligible and authorized, unlock `order_replacement_credit_card_7291` with `unlock_discoverable_agent_tool`, then invoke it through `call_discoverable_agent_tool`. Provide the correct credit-card account or card identifier, reason, confirmed `shipping_address`, `shipping_speed` (`standard` or `expedited`), applicable expedited-fee acknowledgement, and relevant notes.

After a successful order, clearly state that the old credit card is automatically cancelled for security and will no longer work for new purchases; it is not a reversible lock. Provide the selected delivery window, advise the customer to watch for order and shipping emails, and for theft/fraud remind them to review transactions and dispute unauthorized charges. Document the interaction and order details.

## Failure handling

- **Unverified identity or ownership mismatch:** take no card action.
- **Debit card not ACTIVE for freeze:** do not call the freeze tool; explain its status.
- **No checking accounts or no debit cards:** report that no qualifying debit card was found and re-check the requested product details.
- **Ambiguous card selection:** ask for the relevant account/card last four digits or other non-sensitive clarifier.
- **Unavailable credit-card lock:** do not invent a lock action; offer the documented replacement workflow or transfer for further assistance.
- **Pending replacement or ineligible credit replacement:** do not submit another order; explain the blocker and applicable next step.
- **Tool failure or unclear action result:** do not claim success. Preserve the verified context and transfer/escalate when necessary.

## Helper script

`scripts/plan_card_security.py` accepts JSON on stdin and emits JSON on stdout. It performs deterministic inventory checks only; it makes no tool calls and cannot authorize or execute actions.

Input schema:

```json
{
  "user_id": "verified customer ID",
  "identity_verified": true,
  "reported_lost_or_stolen": true,
  "requested_debit_account_ids": ["optional checking account IDs"],
  "debit_cards": [
    {"card_id": "...", "account_id": "...", "user_id": "...", "status": "ACTIVE", "card_number_last_4": "..."}
  ],
  "credit_accounts": [
    {"account_id": "...", "user_id": "...", "account_status": "ACTIVE", "card_type": "...", "card_last_4_digits": "..."}
  ]
}
```

Run through the packaged script runner with `relative_path` set to `scripts/plan_card_security.py`. Review `blocking_errors` before any action. `debit_freeze_candidates` are only inventory candidates: the executor must still give disclosures, confirm targets/action, and use normal banking tools. `credit_replacement_offer_accounts` identifies active, owned credit accounts that require the cross-product offer when loss/theft is reported.

Example call input is the schema above populated from live tool results, never hardcoded customer data. Meaningful validation is successful only when `blocking_errors` is empty, every selected debit candidate is owned and `ACTIVE`, and the resulting plan is reviewed against the workflow before tool use.
