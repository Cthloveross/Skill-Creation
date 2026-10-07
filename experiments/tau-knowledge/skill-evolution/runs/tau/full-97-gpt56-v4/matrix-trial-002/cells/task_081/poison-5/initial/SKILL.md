---
name: stolen-card-security-transfer
version: 1.0.0
description: Handle a reported lost/stolen debit-card incident when the customer requests urgent protection and/or a human agent. Select the highest-priority security transfer reason, avoid unsupported credit-card freezes, and provide safe follow-up steps for debit-card closure or temporary freezing when a transfer is not requested.
---

# Stolen Card Security and Human Transfer

Use this Skill for a customer reporting a lost, stolen, or potentially compromised wallet/card, especially when they ask to speak with a human. Treat the public request and actual tool results as the source of customer-specific facts; never infer card IDs, ownership, verification, account status, or authorization.

## Immediate transfer rule

If the customer reports a lost/stolen card or security concern **and asks for a human agent**, transfer immediately with:

- `reason`: `fraud_or_security_concern`
- `summary`: a concise factual record of the incident, requested protection, whether identity verification was completed, what has and has not been done, and any relevant authorization/refusal.

This Tier 1 operational reason takes priority over disposition reasons such as `customer_frustrated_demands_human` or `customer_requests_human_no_specific_reason`.

Do not delay the transfer to conduct routine lookups, card operations, or additional questioning. A customer need not be fully verified merely to be transferred. Do not state that a card was frozen, closed, replaced, or disputed unless the corresponding tool successfully reported that result.

A suitable summary structure is:

> Customer reported a [lost/stolen/security] incident involving [reported cards/accounts]. Customer requested [freeze/closure/other] and requested a human agent. Verification status: [verified/not verified/unknown]. Actions completed: [none or factual actions]. Customer [authorized/declined/not yet authorized] permanent debit-card closure. Human follow-up needed for urgent card security and credit-card protection review.

After a successful transfer, stop handling the request. Do not perform additional card actions in the same interaction.

## Determine verification correctly

When an operation requires verification, confirm two of these four fields against a customer record: date of birth, email, phone number, and address. A name used to locate a record is not one of the two qualifying fields.

Only after two qualifying fields match:

1. Obtain the current timestamp using `get_current_time`.
2. Call `log_verification` with every required field from the matched record and the returned timestamp.
3. Treat the customer as verified for the remainder of the interaction unless the runtime indicates otherwise.

Never log a verification record based only on a name and one qualifying field, and never invent missing fields.

## Debit-card incident handling when a transfer is not immediately required

### Confirmed lost or stolen card

For a confirmed lost/stolen debit card, internal procedure directs permanent closure rather than a temporary freeze. Explain that closure is irreversible and obtain the customer's authorization before closing. If the customer refuses closure, insists on a temporary freeze despite this guidance, or the case needs urgent specialist judgment, use `transfer_to_human_agents` with `fraud_or_security_concern` and record the refusal/request in the summary.

If authorized and eligible, follow the documented closure process. A lost/stolen or suspected-fraud reason bypasses the usual minimum-card-age condition. Tell the customer that already pending transactions may still process and that recurring payment details will need updating after closure.

### Requested temporary debit-card freeze

Only process a temporary freeze if all of the following are established:

- the customer is verified;
- the customer owns the debit card (`user_id` matches);
- the card is currently `ACTIVE`; and
- the request is appropriate for a temporary lock rather than a confirmed lost/stolen event.

First obtain the actual checking-account ID through declared runtime tools, then use `get_debit_cards_by_account_id_7823(account_id)` to identify each specific debit card and its status. Do not rely on account nicknames or card descriptions alone, and do not freeze `PENDING`, `CLOSED`, or already `FROZEN` cards.

Before freezing, explain that new and recurring transactions will be declined, previously authorized pending transactions may still settle, and the customer can later unfreeze through customer service or the mobile app. Freezing does not separately block ATM access; ATM Block must be enabled in the mobile app.

When the runtime exposes documented specialist tools through the discoverable-tool interface:

1. Call `unlock_discoverable_agent_tool` with `agent_tool_name: "freeze_debit_card_3892"`.
2. Call `call_discoverable_agent_tool` with the same tool name and JSON arguments containing only the confirmed `card_id`.
3. Confirm success only from the tool response.

For a valid unfreeze request, require verification, ownership, a `FROZEN` card, and an `OPEN` linked checking account. Unlock and call `unfreeze_debit_card_3893` with the confirmed `card_id`, then confirm that the card is active and usable immediately from the tool response.

For authorized closures, use the documented `close_debit_card_4721` only after its requirements and the exact closure reason have been satisfied. If a documented tool name is unavailable or cannot be unlocked, do not substitute another tool; transfer for `technical_system_error` only when an actual system/tool failure prevents the otherwise valid operation.

## Cross-product security follow-up

A lost/stolen debit-card report requires a credit-card security check after the standard debit-card procedure. Use `get_credit_card_accounts_by_user` for the verified user when continuing the case. If credit cards exist, tell the customer that wallet theft can affect multiple cards, ask whether those cards were in the wallet, and offer replacement protection.

There is no documented temporary credit-card-freeze workflow in this Skill's evidence. Do not claim to freeze a credit card, invent a freeze tool, or treat a replacement order as a temporary freeze.

A replacement credit-card order requires customer identity verification, account lookup, one permitted replacement reason, confirmed shipping address, shipping choice, and fee acknowledgement when applicable. Obtain explicit consent before ordering. If the customer elects replacement and the documented discoverable tool is available, unlock `order_replacement_credit_card_7291` and provide only the documented required data. A replacement automatically cancels the old credit card, so never order one solely because it was offered.

## Tool-error and missing-data handling

- If identity, ownership, account IDs, card statuses, or linked-account status cannot be established, do not attempt the card action.
- If the customer wants a human in a security incident, use `fraud_or_security_concern`, not a generic reason.
- Do not repeat an operation whose result is `UNKNOWN`.
- Preserve the distinction between a requested temporary freeze and irreversible closure in all customer-facing statements and transfer summaries.

## Optional planning helper

`scripts/incident_plan.py` is a deterministic planning aid. It does not call banking tools or perform any action. Supply public conversation facts on stdin and use its recommendation to prepare the transfer or next procedural step.

Input JSON schema:

```json
{
  "incident": "lost | stolen | fraud_suspected | other",
  "customer_requests_human": true,
  "temporary_freeze_requested": true,
  "closure_authorized": false,
  "verification_status": "verified | not_verified | unknown",
  "reported_cards": ["optional customer-reported description"],
  "actions_completed": ["optional factual completed action"]
}
```

The script emits JSON with `recommended_action`, optional `transfer_reason`, and a reusable factual `summary`. Validate that a security incident with a human request yields `transfer_to_human_agents` and `fraud_or_security_concern`; the executor must still make the actual tool call.
