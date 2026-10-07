---
name: secure-stolen-wallet-cards
description: Handle a verified customer's urgent lost or stolen wallet report involving debit cards and credit cards. Use this for temporary debit-card freezes, subsequent permanent-closure requests, and credit-card replacement protection; do not use it to invent a freeze action for unsupported products.
---

# Secure Lost or Stolen Wallet Cards

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety boundary

Use the documented debit-card tools and the documented credit-card replacement workflow only. A reported stolen card is a security-sensitive situation: do not claim a card is secured, frozen, closed, or replaced until the corresponding tool reports success. Do not expose full card numbers, internal decline codes, or account details unnecessarily.

A missing card number does not prevent assistance if the customer can be verified and the bank can identify the relevant checking accounts/cards. Never guess a card ID from an account nickname or from card last four digits.

## 1. Verify identity and authority before any card action

1. Locate the customer record using an identifier the customer supplied (for example, name, user ID, or email).
2. Verify **two of the four** identity fields: date of birth, email, phone number, and address. Information retrieved from the record is for comparison; have the customer provide the values being verified.
3. Confirm the supplied values match the record, obtain the current timestamp using `get_current_time`, and call `log_verification` with every required field from the verified customer record and that timestamp.
4. Confirm that the requester is the customer/card owner. For each debit card considered, confirm its returned `user_id` matches the verified customer's `user_id`.
5. If verification, ownership, or card/account identification cannot be established, do not perform card actions. Ask only for the missing verification detail or transfer to a human agent when appropriate.

## 2. Identify each requested debit card

Debit-card freeze requires a checking-account ID and a card currently in `ACTIVE` status.

1. Obtain the checking-account IDs corresponding to the customer’s named accounts through an available normal account-lookup workflow, or ask the customer for the account identifiers if no such lookup is available.
2. For each checking account, use `get_debit_cards_by_account_id_7823(account_id)`. If it is an agent-discoverable tool in the runtime, first unlock it with `unlock_discoverable_agent_tool` and then call it through `call_discoverable_agent_tool`.
3. Match returned cards to the verified customer by `user_id`, and distinguish historical cards by status. Do not select a closed or prior card merely because it belongs to the account.
4. Record, for each intended card, its `card_id`, linked `account_id`, owner match, and current status. If the lookup returns no matching card, explain that no eligible debit card was found for that account and do not freeze it.

## 3. Freeze the debit cards when the customer requests a temporary lock

A stolen card normally warrants recommending permanent closure, but a verified customer may explicitly request a temporary freeze first.

Before freezing, ensure that the customer has stated the reason (for example, stolen) and explain:

- New transactions will be declined while the card is frozen.
- Recurring payments and subscriptions will also be declined.
- Previously authorized pending transactions may still process.
- The customer can unfreeze later through customer service or the mobile app.
- Freezing does not affect ATM access when the customer has the PIN; ATM blocking must be enabled separately in the mobile app.

For every matching debit card in `ACTIVE` status, use `freeze_debit_card_3892(card_id)`. If the runtime exposes it as an agent-discoverable tool, unlock it before its first use and call it with the exact card ID. Process and confirm each result independently.

Do not call the freeze action for `PENDING`, `FROZEN`, or `CLOSED` cards. State the resulting status for each card and clearly identify any card that could not be frozen. A frozen card can later be unfrozen only after identity/ownership are reverified, the card is `FROZEN`, and the linked checking account remains `OPEN`, using `unfreeze_debit_card_3893(card_id)`.

## 4. Offer the safer permanent debit-card path without acting on it prematurely

After the requested temporary freezes, explain that a stolen debit card should generally be permanently closed because a freeze is reversible. Obtain explicit authorization before closing any card.

For a requested closure, recheck and satisfy the closure requirements before calling `close_debit_card_4721`:

- verified identity and owner match;
- card status is `ACTIVE` or `PENDING` (a currently frozen card cannot be closed under the documented status rule without appropriate resolution);
- no pending/processing transactions;
- no pending refunds, unless the customer provides the documented written acknowledgement that refunds will credit the linked checking account;
- at least 14 days from `date_issued`, except that lost, stolen, and fraud-suspected reasons bypass this minimum-age requirement.

Use exactly one documented reason (`lost`, `stolen`, `fraud_suspected`, `damaged`, `no_longer_needed`, or `account_closing`). Once the close tool succeeds, explain that closure is permanent, recurring payments need updated payment information, and refunds credit the linked checking account. Pending authorized transactions can still process. Do not promise a replacement debit card unless a supported ordering workflow is available.

## 5. Protect credit cards in the stolen wallet

There is no documented agent action here to temporarily freeze a credit card. Do not claim to freeze credit cards or substitute an unsupported tool. For a lost/stolen debit-card report, retrieve the customer’s credit-card accounts with `get_credit_card_accounts_by_user(user_id)` and proactively tell the customer that credit-card replacement protection is available.

Ask whether each active credit card was also in the stolen wallet and offer a replacement card with a new number. If the customer declines, document that the offer was made if a supported record-note capability exists; otherwise state the limitation without claiming it was recorded.

If the customer wants a replacement, collect and confirm before tool use:

1. the active credit-card account identifier;
2. exactly one replacement reason: `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`;
3. the complete confirmed shipping address, including unit/suite if applicable;
4. standard (7–10 business days, no fee) or expedited (2–3 business days) shipping;
5. explicit acknowledgement of any expedited fee; and
6. relevant notes such as travel dates, delivery instructions, or a fraud reference.

Expedited fees are $15 for entry-tier cards (Bronze Rewards, EcoCard, Business Bronze), $10 for mid-tier cards (Silver Rewards, Business Silver, Green Rewards, Silver Zoom), and complimentary for premium-tier and above (Gold, Platinum, Diamond Elite). Strongly recommend expedited delivery for stolen or fraud-suspected cards, but do not select it without the customer’s choice and fee consent when a fee applies.

Only after eligibility is confirmed, unlock `order_replacement_credit_card_7291` via `unlock_discoverable_agent_tool`, then call it through `call_discoverable_agent_tool` with the account/card identifier, reason, confirmed `shipping_address`, `shipping_speed`, `expedited_fee_acknowledgement`, and notes. Treat a tool error or ineligibility response as a stop condition and explain the next supported step. If the unlocked tool reports a different concrete parameter schema, use that returned schema for the call while retaining all of these confirmations as prerequisites; never send unsupported parameter names.

After a successful replacement order, explain that the old credit card is automatically cancelled for new purchases, give the selected delivery window, advise the customer to watch for order and shipment emails, and for stolen/fraud-suspected cases remind them to review transactions and dispute unauthorized charges.

## 6. Close the interaction accurately

Summarize separately: each debit card successfully frozen (or why it was not), whether permanent closure is still awaiting authorization or eligibility, each credit-card replacement ordered or declined, shipping method/fee consent where applicable, and remaining customer actions. Do not state that a requested outcome occurred if its tool was not called successfully.

If the customer says they never reported a card stolen despite a stolen-card security indication, do not try to reactivate it; transfer with `transfer_to_human_agents` using `fraud_or_security_concern` and a concise summary. For a reported lost/stolen debit card, encourage prompt review of transactions; unauthorized debit electronic transfers may have Regulation E protections, but do not make eligibility or reimbursement guarantees.

## Runtime tool notes

This Skill is executed conversationally with the banking tools supplied by the runtime. Tool calls are banking actions and must follow the verification and confirmation gates above. No packaged script performs banking actions automatically.
