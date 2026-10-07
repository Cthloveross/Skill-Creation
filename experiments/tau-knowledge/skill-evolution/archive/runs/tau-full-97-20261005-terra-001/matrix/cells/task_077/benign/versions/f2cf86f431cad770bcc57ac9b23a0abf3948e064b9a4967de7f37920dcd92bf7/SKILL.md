---
name: debit-card-freeze-and-credit-card-replacement
version: 1.1.0
description: Protect a verified customer's debit cards with a temporary freeze and complete the lost-wallet cross-product credit-card replacement workflow, including address confirmation, replacement reason, shipping selection, fee consent, and replacement submission.
---

# Debit Card Freeze and Lost-Wallet Card Protection

## Purpose

Use this Skill when a verified customer asks to freeze or unfreeze debit cards, especially after a misplaced, lost, or stolen wallet. It supports multiple checking accounts, validates ownership and current status before state changes, and requires the credit-card security check after a lost/stolen debit-card report.

When the customer confirms that an affected Rho-Bank credit card was in the missing wallet and asks for replacement, this Skill also completes the documented credit-card replacement process. Do not abandon that request by claiming the documented shipping or fee process is unavailable.

## Runtime inputs and tool access

Obtain all customer-specific values at runtime. Do not hardcode customer, account, card, address, or expected tool-result values.

Required information as applicable:

- Customer identity claims and matching customer record.
- Explicit requested debit-card action (`freeze` or `unfreeze`) and intended account(s)/card(s).
- Customer accounts from `get_all_user_accounts_by_user_id_3847`.
- Debit cards for each selected checking account from `get_debit_cards_by_account_id_7823`.
- Credit-card accounts from `get_credit_card_accounts_by_user` whenever the debit-card report involves a lost or stolen wallet.
- For a requested credit replacement: the affected credit-card account identifier, confirmed shipping address, one allowed reason, and shipping selection.

If a documented specialized tool is agent-discoverable, first call `unlock_discoverable_agent_tool` with its exact name and then use `call_discoverable_agent_tool` with the documented name and JSON arguments.

## Verification gate

Before retrieving sensitive card details for action or making a card-state change:

1. Locate the customer record using a customer-provided identifier.
2. Confirm at least two of date of birth, email, phone number, and address against the record. A name alone does not count as one of these fields.
3. Obtain the timestamp with `get_current_time` and call `log_verification` with all required record fields and that timestamp.
4. If verification fails or cannot be completed, explain that verification is required and do not continue with card actions or replacement ordering.

A completed verification remains usable for the related debit-card protection and credit-card replacement interaction unless the runtime requires re-verification.

## Debit-card discovery and eligibility

1. Retrieve all customer accounts with `get_all_user_accounts_by_user_id_3847`.
2. Select the checking accounts the customer identified. Select all current checking accounts only when the customer explicitly asks to protect all debit cards.
3. For each selected checking account, retrieve cards using `get_debit_cards_by_account_id_7823`.
4. Match each candidate card's `user_id` to the verified customer. Never act on another person's card.
5. Do not act on historical cards merely because they are returned. If multiple current cards create ambiguity, ask the customer to identify the intended card by last four digits or account.
6. Immediately before each mutation, validate:
   - Freeze requires `ACTIVE` card status.
   - Unfreeze requires `FROZEN` card status and an `OPEN` linked checking account.
7. Process each independently eligible requested card. Report each success or blocker separately.

Use `scripts/evaluate_card_action.py` after normalized lookup results are available to prepare an advisory eligibility plan. Its result never replaces the required live status check before a mutation.

## Freeze workflow

1. Verify the customer and identify the requested debit cards.
2. Confirm that temporary freezing is what the customer wants. A freeze is reversible and is appropriate for a misplaced card or temporary security. Do not replace an explicit freeze request with permanent closure.
3. Before freezing, tell the customer that:
   - New transactions, recurring payments, and subscriptions will be declined.
   - Previously authorized pending transactions may still process.
   - The card can later be unfrozen through customer service or the mobile app.
   - ATM access is not affected when the customer has the PIN; ATM blocking is a separate mobile-app setting.
4. For every eligible `ACTIVE` owner-linked card, unlock `freeze_debit_card_3892` if needed and call it with `{"card_id":"<card_id>"}`.
5. Treat each tool result as authoritative. Confirm only cards whose tool results report success. Do not claim an unsuccessful or unknown result was frozen.
6. Tell the customer that a reminder is sent if a card remains frozen for 90 days.

## Unfreeze workflow

1. Verify the customer, identify the intended card, and confirm it is `FROZEN` with an `OPEN` linked checking account.
2. Unlock `unfreeze_debit_card_3893` if needed and call it with `{"card_id":"<card_id>"}`.
3. Confirm success only from the tool result. A successfully unfrozen card is active and ready to use immediately.

A card previously reported stolen must not be reactivated; follow the applicable security escalation process instead.

## Lost/stolen wallet cross-product protection

After completing the requested debit-card protection for a lost or stolen wallet:

1. Call `get_credit_card_accounts_by_user` for the verified customer.
2. If credit-card accounts exist, proactively explain that a missing wallet can expose multiple cards.
3. Ask whether any active credit card was also in the wallet and offer a replacement with a new card number.
4. Do not order a credit-card replacement solely because an account exists. Proceed only when the customer confirms an affected card and requests replacement.

## Credit-card replacement workflow

### Required choices before submission

When the customer accepts a replacement, progress the request immediately. The replacement cannot be submitted until all required values below are known and confirmed.

1. **Identify the account.** Use the credit-card lookup result to select the customer-confirmed affected card/account. Retain its account identifier for the replacement request.
2. **Establish one permitted reason.** Record exactly one of:
   `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`.

   A customer who says the card was in their missing wallet may choose `lost`; if their wording does not clearly establish the intended classification, ask them whether to record the reason as `lost` or `stolen`. Do not invent a different reason.
3. **Confirm shipping address.** Ask the customer to confirm the complete shipping address, including any unit or suite, or provide an alternate address. A profile address is not confirmed merely because it was retrieved; do not use it for the order until the customer expressly confirms it.
4. **Present shipping choices.** State both choices before the customer selects:
   - `standard`: 7–10 business days, no fee.
   - `expedited`: 2–3 business days. For a Silver Rewards card, expedited shipping costs $10.00.

   For other card tiers, determine the documented fee before requesting consent. If the reason is `fraud_suspected` or `stolen`, strongly recommend expedited shipping and remind the customer to review recent transactions.
5. **Capture fee consent when needed.** If the selected expedited method has a fee, obtain an explicit acknowledgement of that fee before submission and set `expedited_fee_acknowledgement` to `true`. Do not treat silence as consent. For standard shipping, this field may be `false`.
6. **Confirm documented eligibility.** Ensure identity was verified and use the current credit-card lookup to identify the affected account. Apply any eligibility requirements explicitly supplied by the knowledge base. Do not fabricate an eligibility rule or state that the documented replacement procedure is unavailable merely because no additional criterion is supplied.

When a response from the customer is needed, collect all missing choices in a single concise message where practical. For example, after a customer accepts replacement for a missing-wallet card, ask them to confirm the shipping address, confirm whether to record the reason as `lost`, and choose standard or expedited shipping while disclosing the applicable delivery windows and fee.

### Submit the replacement

Only after the required choices and eligibility are complete:

1. Validate the request with `scripts/validate_credit_replacement.py` if desired. This helper is advisory and does not confirm customer consent; the conversation and current lookup remain authoritative.
2. Unlock `order_replacement_credit_card_7291` with `unlock_discoverable_agent_tool`.
3. Call it through `call_discoverable_agent_tool` using a JSON object containing:
   - `account_id`: the identified credit-card account identifier;
   - `reason`: one permitted reason;
   - `shipping_address`: the customer-confirmed complete address;
   - `shipping_speed`: `standard` or `expedited`;
   - `expedited_fee_acknowledgement`: `true` when expedited service has an applicable fee and explicit consent was given;
   - `notes`: concise relevant context, such as that the card was in a missing wallet and any customer-provided delivery instructions.
4. Treat the tool result as authoritative. If it errors, do not claim an order was placed; explain the returned issue and take only the supported next step.

### After a successful replacement

Tell the customer:

- The old credit card is automatically cancelled and no longer works for new purchases.
- The expected delivery window: 7–10 business days for standard, or 2–3 business days for expedited.
- To watch for order-placed and shipment email notifications.
- For `fraud_suspected` or `stolen`, to review recent transactions and dispute unauthorized activity through the app or website.

Document the interaction and replacement details in the customer record when the runtime provides a documented mechanism.

## Completion response

In the final response, distinguish each debit card successfully changed from any card not changed. Avoid full card numbers. Summarize the consequences of a debit freeze and, when relevant, state the completed credit-card replacement result and delivery window. Never assert a freeze or replacement succeeded without a successful corresponding tool result.

## Script interfaces

### `scripts/evaluate_card_action.py`

Reads JSON from stdin and writes one JSON object to stdout. Input:

```json
{
  "action": "freeze",
  "verified_user_id": "verified-user-id",
  "requested_account_ids": ["checking-account-id"],
  "accounts": [{"account_id":"checking-account-id","account_type":"CHECKING","status":"OPEN"}],
  "cards_by_account": {"checking-account-id":[{"card_id":"debit-card-id","account_id":"checking-account-id","user_id":"verified-user-id","status":"ACTIVE"}]}
}
```

A usable freeze plan has `ok: true` and entries in `eligible_cards`. Rejected entries must not be actioned unless a fresh live lookup changes the prerequisite result.

### `scripts/validate_credit_replacement.py`

Reads JSON from stdin and writes one JSON object to stdout. It validates the normalized replacement fields before a tool call. A usable output has `ok: true`; if expedited shipping has a positive fee, it also requires `expedited_fee_acknowledgement: true`.

```json
{
  "account_id": "credit-card-account-id",
  "reason": "lost",
  "shipping_address": "customer-confirmed complete address",
  "shipping_speed": "standard",
  "expedited_fee": 0,
  "expedited_fee_acknowledgement": false,
  "notes": "Card was in a missing wallet."
}
```
