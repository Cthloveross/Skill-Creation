---
name: secure-lost-wallet-card-protection
description: Protect a verified customer's debit and credit cards after a misplaced or lost wallet. Temporarily freeze selected active debit cards while the wallet is missing, replace an eligible affected credit card on request, and permanently close the same debit cards if the customer later confirms loss or theft and asks to cancel them.
---

# Secure Lost-Wallet Card Protection

Use this workflow for a verified customer reporting a wallet with debit cards missing, including a later change from a temporary freeze to confirmed loss/theft and permanent cancellation.

A **freeze** is temporary and reversible. A **closure** permanently deactivates a card and cannot be reversed. Use a freeze while the customer is still looking; when the customer definitively reports loss/theft or requests cancellation, perform the closure workflow for the affected cards.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Runtime invocation rules

Use current-interaction facts and tool results only. Never reuse a user ID, card ID, address, authorization, or action outcome from another interaction.

In runtimes where these are discoverable agent tools, unlock the needed target and invoke it through the documented wrapper:

- `unlock_discoverable_agent_tool(agent_tool_name="...")`
- `call_discoverable_agent_tool(agent_tool_name="...", arguments="{...}")`

The wrapper's `arguments` value is a JSON-object string. Use `agent_tool_name` where exposed by the runtime. Do not use a direct tool call when the runtime exposes only the discoverable wrapper.

Relevant targets are:

- `get_all_user_accounts_by_user_id_3847` with `{"user_id":"..."}`
- `get_debit_cards_by_account_id_7823` with `{"account_id":"..."}`
- `freeze_debit_card_3892` with `{"card_id":"..."}`
- `close_debit_card_4721` with `{"card_id":"...","reason":"lost"}` or another supported security reason
- `order_replacement_credit_card_7291` for credit-card replacements

Unlock a target before its first wrapper invocation. Treat every action result independently: do not state that a card was frozen, closed, or replaced unless the corresponding action result is successful.

## 1. Verify identity and authority

Before any banking action:

1. Locate the profile using customer-provided information.
2. Match at least two profile fields from date of birth, email, phone number, and address. Name alone is insufficient.
3. Obtain the current timestamp and create `log_verification` using the complete returned profile and timestamp.
4. Use the verified profile `user_id` for all ownership checks.

If a successful verification log already exists in the current interaction, do not repeat it. If fields match but logging has not occurred, log verification rather than asking the customer to repeat supplied facts. If identity cannot be verified, do not take card actions.

## 2. Locate and validate the requested debit cards

1. Retrieve all accounts using `get_all_user_accounts_by_user_id_3847` and the verified user ID.
2. Match each requested account label to a returned **checking** account using returned name, nickname, class, or another identifying field. Do not guess account IDs.
3. Retrieve debit cards using `get_debit_cards_by_account_id_7823` for every matched requested checking account.
4. Record each candidate card's card ID, linked account, owner, status, issue date, and relevant transaction/refund eligibility information returned or available through the applicable workflow.

For a temporary freeze, only select a distinct card when it is linked to the selected checking account, its `user_id` equals the verified user ID, and its status is exactly `ACTIVE`. Historical, pending, closed, and already frozen cards must not be frozen. If a requested account has more than one active card and the request does not identify one, obtain clarification.

## 3. Temporarily freeze eligible cards

Before the first freeze, explain:

- new card transactions will be declined while frozen;
- recurring payments and subscriptions will also be declined;
- pending transactions already authorized may still process;
- the card may later be unfrozen through customer service or the mobile app; and
- freezing alone does not block ATM access for someone who knows the PIN; ATM Block must be enabled separately in the mobile app.

The customer's explicit request to freeze identified cards supplies action confirmation. Invoke `freeze_debit_card_3892` exactly once for each distinct selected, owned, ACTIVE card. Confirm only the successful freezes and retain the exact frozen card IDs for any later confirmed-loss request.

If an action fails, accurately state which card was not confirmed frozen and follow the returned error or appropriate escalation path.

## 4. Credit-card protection and replacement

For a lost or stolen wallet report, retrieve credit-card accounts with `get_credit_card_accounts_by_user(user_id)` unless a usable current-interaction result already exists. If an active card exists, explain that a replacement produces a new card number and the old credit card is cancelled for new purchases, then offer replacement protection.

Do not order a credit-card replacement merely because an account exists. Before ordering, verify:

- the selected account belongs to the verified user and is ACTIVE;
- the customer explicitly requested replacement of that affected account;
- the reason is one of `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`;
- the complete shipping address is confirmed; and
- the customer selected standard or expedited delivery.

Confirm eligibility from available policy and the account result. Where no additional eligibility restriction is supplied beyond ownership and active status, do not invent a balance, credit, tenure, fee, or limit blocker.

Disclose shipping before submission:

- **Standard:** 7–10 business days, no fee.
- **Expedited:** 2–3 business days. Obtain acknowledgement of the applicable disclosed tier fee when one applies.

For the runtime replacement tool, unlock `order_replacement_credit_card_7291`, then invoke it once with JSON arguments containing:

- `credit_card_account_id`: selected active account ID;
- `reason`: the confirmed allowed reason;
- `shipping_address`: confirmed full address;
- `expedited_shipping`: `false` for standard or `true` for expedited; and
- any required fee acknowledgement and concise factual notes supported by the runtime.

A reported missing wallet supports `lost` when the customer requests replacement. Do not add unconfirmed fraud allegations. A standard shipment does not require expedited-fee acknowledgement.

## 5. Later confirmed loss/theft: permanently close the previously frozen cards

This branch applies when, after a temporary freeze, the customer definitively says the wallet/cards are gone or stolen and asks to cancel them. The later confirmed request changes the requested protection from temporary to permanent; do not leave the cards merely frozen.

1. Reuse current-interaction verification and the card IDs previously frozen for this report. If those IDs are unavailable, repeat the account/card lookup and establish ownership before proceeding.
2. Tell the customer that permanent closure cannot be undone, pending transactions already authorized may still process, and recurring merchants will need new payment details.
3. Apply closure eligibility requirements: ownership must match the verified user; check for pending/processing transactions and pending refunds through the available closure workflow; and use an allowed reason of `lost`, `stolen`, or `fraud_suspected`. Loss/theft/security reasons bypass the minimum 14-day card-age condition.
4. Unlock `close_debit_card_4721` and invoke it once for **each distinct debit card that was frozen for this wallet report**, using that card ID and the confirmed security reason. A prior temporary freeze must not cause the confirmed-loss cards to be omitted from the permanent-closure workflow.
5. Confirm closure only after a successful result for each card. If a closure result reports a blocking pending transaction, refund, ownership issue, or other error, report that specific unresolved result and follow the returned instruction; never claim closure.

No debit-card replacement-order tool or parameter schema is assumed by this Skill. After successful closure, offer or arrange replacement only through a separately documented and runtime-available debit-card replacement workflow. Do not invent a tool name, arguments, order status, or delivery date.

## 6. Final response and record

State the actual result for each affected debit card and for any credit replacement separately.

For successful temporary freezes, reiterate the effects on new transactions, recurring payments, pending authorized transactions, and later unfreezing. For successful permanent debit closures, state that each old card is permanently deactivated and cannot be reactivated, that recurring payment details need updating, and that pending authorized transactions may still process. For a successful credit replacement, state that the old credit card is cancelled for new purchases, give the selected delivery timeframe, and advise the customer to watch for order and shipment emails.

Document verification, selected accounts, ownership/status checks, card IDs, each action result, closure reason, credit-account eligibility basis, confirmed replacement address, delivery choice, applicable fee acknowledgement, and all failures or missing prerequisites. Never fabricate completion.

## Optional deterministic preflight helper

`scripts/workflow_guard.py` is a read-only checklist helper. It reads one JSON object from stdin and emits one JSON object on stdout. It does not call banking tools or perform actions.

Input fields:

- `user_id`: verified user ID.
- `verified_fields`: list of matched profile field names.
- `requested_account_ids`: selected checking-account IDs.
- `accounts`: account objects with `account_id` and `account_type`.
- `debit_cards`: card objects with `card_id`, `account_id`, `user_id`, and `status`.
- Optional `credit_replacement`: object with `requested`, `account_id`, `account_user_id`, `account_status`, `reason`, `shipping_address_confirmed`, `shipping_speed`, and, for fee-bearing expedited delivery, `expedited_fee_acknowledged`.
- Optional `confirmed_loss_closure`: object with `requested`, `previously_frozen_card_ids`, `reason`, and `ownership_confirmed_card_ids`.

Its output includes `freeze_card_ids`, `credit_order_ready`, `close_card_ids`, and `blockers`. Use it only as a pre-action checklist; successful output is not an authorization or a banking action result.
