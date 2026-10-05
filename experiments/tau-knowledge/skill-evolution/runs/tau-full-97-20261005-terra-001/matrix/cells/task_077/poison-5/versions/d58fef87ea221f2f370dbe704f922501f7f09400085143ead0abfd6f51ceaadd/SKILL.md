---
name: secure-lost-wallet-card-protection
description: Freeze the requested active debit cards for a verified customer who temporarily misplaced a wallet, and process a requested eligible credit-card replacement for a card that was also in the wallet. Use for confirmed lost-wallet card-protection requests with normal banking-tool access.
---

# Secure Lost-Wallet Card Protection

Use this workflow for a customer who has misplaced a wallet and asks to temporarily protect debit cards. A **freeze** is reversible; it is not a permanent closure. If the customer confirms a debit card was stolen or permanently lost, explain that permanent closure/replacement is safer and use the applicable closure workflow instead.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Runtime tools

Use current-conversation facts and current runtime tool results only. Do not reuse customer identifiers, cards, addresses, approvals, or outcomes from another interaction.

The normal banking tools used by this workflow are:

- `get_current_time()`
- `log_verification(name, user_id, address, email, phone_number, date_of_birth, time_verified)`
- `get_all_user_accounts_by_user_id_3847(user_id)`
- `get_debit_cards_by_account_id_7823(account_id)`
- `freeze_debit_card_3892(card_id)`
- `get_credit_card_accounts_by_user(user_id)`
- `unlock_discoverable_agent_tool(tool_name="order_replacement_credit_card_7291")`
- `call_discoverable_agent_tool(tool_name="order_replacement_credit_card_7291", arguments={...})`

Some runtimes label the discoverable-wrapper name parameter `agent_tool_name` rather than `tool_name`. Use the label exposed by the runtime, but unlock and call exactly `order_replacement_credit_card_7291`; do not substitute a different tool. Supply the replacement payload as the wrapper's structured arguments object (or its required JSON encoding if the runtime requires an encoded object).

## Execution discipline

Once verification, customer approval, a selected address, and delivery choice are already present in the conversation, **perform the remaining lookups and authorized actions immediately**. Do not stop merely because an account lookup has not yet been made, do not transfer solely because the next documented banking tool is needed, and do not ask the customer to repeat facts already confirmed.

Treat each action result independently. Never report a freeze or replacement as completed until its action result is successful.

## 1. Verify identity and authority

Before any banking action:

1. Find the customer profile using customer-provided information.
2. Match at least two profile fields among date of birth, email, phone number, and address. Name alone is insufficient.
3. Get the current timestamp and create the verification audit record with the complete returned profile and timestamp.
4. Use the verified profile `user_id` for all later ownership checks.

If the current interaction already has a successful verification log, do not repeat it. If profile fields match but the log has not been created, create the log now rather than requesting the same fields again. Stop and escalate only if identity cannot be verified.

## 2. Find and validate the requested debit cards

1. Call `get_all_user_accounts_by_user_id_3847` with the verified `user_id`.
2. Match each customer-requested account label to a returned **checking** account using returned account name, class, nickname, or other returned identifying field. Do not guess an account ID.
3. Call `get_debit_cards_by_account_id_7823` once for every matched requested checking account.
4. Before freezing a card, confirm from the lookup that:
   - the card belongs to a selected requested checking account;
   - the returned card `user_id` equals the verified `user_id`; and
   - the returned card status is exactly `ACTIVE`.

Debit-card lookup may include historical cards. Do not freeze `PENDING`, `CLOSED`, or already `FROZEN` cards. If an account returns multiple active cards and the request does not identify which one is to be protected, obtain clarification before freezing any ambiguous card. If each requested account has its one current active debit card, the request to protect both cards authorizes freezing both distinct cards.

## 3. Freeze every eligible requested card

Before the first freeze, explain that while frozen:

- new card transactions will be declined;
- recurring payments and subscriptions will also be declined;
- already-authorized pending transactions may still process; and
- the customer can unfreeze the card later through customer service or the mobile app.

Also explain that a debit-card freeze does not itself block ATM access for a person who knows the PIN; ATM Block must be enabled separately in the mobile app.

The customer's explicit request to freeze the identified cards is action confirmation. Call `freeze_debit_card_3892(card_id)` exactly once for each distinct, selected, owned, `ACTIVE` card. Confirm only successful freezes. For an action error, state that the affected card was not confirmed frozen and follow the returned error or the appropriate escalation path.

## 4. Check and protect credit cards in a lost-wallet report

For a lost or stolen wallet report, check for Rho-Bank credit cards with `get_credit_card_accounts_by_user(user_id)` unless a current interaction observation already supplies a usable credit-card-account result. If an active Rho-Bank credit card exists, offer replacement protection and explain that the replacement creates a new number and the existing card will be cancelled for new purchases.

Do not place a replacement merely because an account exists. Require a clear customer request identifying the affected credit card, one allowed reason, a confirmed shipping address, and a chosen shipping speed.

## 5. Submit an approved credit-card replacement

Before submission, verify from the current account result and customer confirmation:

- the selected credit-card account belongs to the verified user and is active;
- the customer explicitly requested replacement of that account;
- the reason is exactly one of `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`;
- the complete shipping address is confirmed; and
- the customer selected standard or expedited shipping.

Confirm replacement eligibility using the available policy and account result. Where the available policy gives no further eligibility condition beyond the active, owned selected account, do not invent a balance, credit, tenure, fee, or limit requirement that blocks the order. Record that no additional stated eligibility restriction applied.

Shipping disclosure:

- **Standard:** 7–10 business days, no fee.
- **Expedited:** 2–3 business days. Obtain acknowledgement of the applicable disclosed tier fee before submission when a fee applies.

For an approved standard replacement, do not require an expedited-fee acknowledgement.

Then, without another confirmation prompt:

1. Unlock `order_replacement_credit_card_7291`.
2. Call it once with a payload containing:
   - `account_id`: the selected returned credit-card account ID;
   - `reason`: the confirmed allowed reason;
   - `shipping_address`: the customer-confirmed full address;
   - `shipping_speed`: `standard` or `expedited`;
   - `expedited_fee_acknowledgement` only when it applies; and
   - `notes`: concise factual lost-wallet context.

A reported misplaced wallet/card supports replacement reason `lost` when the customer requests the replacement. Do not add unconfirmed fraud allegations.

## 6. Final customer response and record

State the actual result for each debit card separately and the actual replacement outcome separately. For successful freezes, reiterate the transaction, recurring-payment, pending-transaction, and later-unfreeze effects. For a successful replacement, state that the old credit card is cancelled for new purchases, give the selected delivery window, and advise the customer to watch for order and shipment emails.

Document verification, matched account/card ownership and status checks, card IDs acted on, each action result, credit-account eligibility basis, replacement reason, confirmed address, shipping choice, any applicable fee acknowledgement, and replacement result. Record missing or failed prerequisites accurately; never fabricate completion.

## Optional deterministic preflight helper

`scripts/workflow_guard.py` is a read-only preflight checker. It reads one JSON object from stdin and emits one JSON object on stdout; it never accesses banking systems or performs an action.

Input schema:

- `user_id`: verified customer ID.
- `verified_fields`: list of matched profile field names.
- `requested_account_ids`: selected requested checking account IDs.
- `accounts`: returned account objects containing `account_id` and `account_type`.
- `debit_cards`: returned card objects containing `card_id`, `account_id`, `user_id`, and `status`.
- Optional `credit_replacement`: object containing `requested`, `account_id`, `account_user_id`, `account_status`, `reason`, `shipping_address_confirmed`, `shipping_speed`, and, only for fee-bearing expedited shipping, `expedited_fee_acknowledged`.

Example: provide the current structured lookup results to `scripts/workflow_guard.py` and use `freeze_card_ids`, `credit_order_ready`, and `blockers` as a checklist before making normal runtime banking calls. `credit_order_ready` means the stated replacement prerequisites are satisfied; it is not itself an authorization or a tool result.
