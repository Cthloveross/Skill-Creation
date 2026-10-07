---
name: lost-stolen-card-security-transfer
version: 1.1.0
description: Safely handle a reported lost, stolen, or compromised wallet/card, with priority handling for an explicit request to speak to a human. Use the security transfer reason, do not claim unsupported credit-card freezes, and follow documented debit-card and credit-card safeguards only when the case continues.
---

# Lost/Stolen Card Security and Human Transfer

Use this Skill when a customer reports a lost/stolen card or wallet, wants a debit-card freeze or closure, or asks for a human in connection with card security. Use actual conversation facts and successful tool results. Do not infer card IDs, ownership, status, completed actions, or customer consent.

## Explicit human request in a security incident

When a customer reports loss, theft, possible compromise, fraud, or another card-security concern **and asks for a human**, promptly call:

- `transfer_to_human_agents`
- `reason`: `fraud_or_security_concern`
- `summary`: a concise factual handoff covering the incident, cards the customer reported, requested protection, verification state, actions actually completed, and authorization or refusal relevant to closure/replacement.

`fraud_or_security_concern` is Tier 1 and outranks generic frustrated/preference transfer reasons. A completed identity check is not required merely to make this transfer. Do not delay an explicit requested security transfer for routine lookups, verification, or card operations unless a separate documented requirement makes an action mandatory before handoff.

A transfer summary should clearly distinguish requests from results. For example, use this structure (replace bracketed facts only with known facts):

> Customer reported [lost/stolen/security] incident involving [reported card descriptions]. Customer requested [temporary freeze/closure/other] and a human agent. Verification: [verified/not verified/unknown]. Actions completed: [only successful actions, or none]. [Closure/replacement authorization or refusal]. Human follow-up needed for urgent card-security review.

After the transfer succeeds, send a brief confirmation such as, “I’m sorry this happened. I’ve connected you with a specialist who can help secure your cards.” Do not say cards were frozen, closed, replaced, or disputed unless a tool reported that success, and do not continue card operations after a successful handoff.

## Verification for card operations

A debit-card freeze, unfreeze, closure, or credit-card replacement requires verification. Match **two of these four** fields to the customer record: date of birth, email, phone number, and address. A name used to locate a record is not a qualifying field.

Once two qualifying fields match:

1. get the timestamp with `get_current_time`;
2. call `log_verification` with the matched record's full required values and that timestamp; and
3. use the verified status only for the current interaction.

If only one or no qualifying fields has been confirmed, do not perform a protected card action. Do not manufacture a second field from record data. A human transfer can still proceed.

## Debit-card security when the case continues

### Customer asks for a temporary freeze

Before each debit-card freeze, establish that the customer is verified, owns the card (`user_id` matches), and the card status is `ACTIVE`. Retrieve actual debit cards for the actual checking-account ID with `get_debit_cards_by_account_id_7823`; account nicknames alone are not card IDs. Never attempt to freeze a `PENDING`, `FROZEN`, or `CLOSED` card.

Explain before proceeding:

- new purchases and recurring payments will be declined;
- an already authorized pending transaction may still settle;
- the customer may unfreeze through customer service or the mobile app; and
- a card freeze alone does not block ATM access; ATM Block must be enabled separately in the mobile app.

For a confirmed lost or stolen debit card, recommend permanent closure because it is the documented more secure option. Do **not** close the card without the customer's authorization. A customer may still request a temporary freeze; if all freeze requirements are met and the case is not being handed off, use the documented temporary-freeze process rather than falsely claiming closure.

Where the documented discoverable tool is available, unlock `freeze_debit_card_3892`, then call it with only the confirmed `card_id`. Confirm a freeze only from a successful result.

### Permanent debit-card closure

For closure, require verification, ownership, an `ACTIVE` or `PENDING` card, no pending/processing transactions, and no pending refund unless the customer provides the documented written acknowledgement. The usual 14-day card-age rule is bypassed for `lost`, `stolen`, and `fraud_suspected`. Obtain the precise permitted reason and closure authorization, use `close_debit_card_4721` only when all applicable requirements are met, and explain that closure is permanent, recurring payment details must be updated, and pending transactions can still process.

### Unfreezing

Require verification, ownership, `FROZEN` status, and an `OPEN` linked checking account. Unlock and call `unfreeze_debit_card_3893` using the confirmed `card_id`, and only then confirm immediate activation.

If a required documented tool cannot be accessed or returns an actual system failure, do not substitute a tool or retry an `UNKNOWN` result. Use `technical_system_error` only when that failure prevents an otherwise valid operation.

## Credit-card cross-product protection

In a continuing lost/stolen debit-card case, after the standard debit-card procedure, check credit cards with `get_credit_card_accounts_by_user` for the verified user. If cards exist, explain that a stolen wallet can expose them too, ask whether they were in the wallet, and offer replacement protection. Do not presume a transaction is unauthorized just from its merchant name or amount.

There is no documented temporary credit-card-freeze process. Never invent a credit-card freeze tool or represent a replacement as a freeze.

A replacement requires verification, a credit-card account lookup, explicit replacement consent, exactly one reason (`fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`), confirmed shipping address, shipping speed, and fee acknowledgement where applicable. If eligible and the customer elects replacement, unlock and call `order_replacement_credit_card_7291` with only the documented data. State that it cancels the old card. Standard delivery is 7–10 business days free; expedited is 2–3 business days, with a $15 EcoCard entry-tier fee and complimentary Gold Rewards premium-tier expedited shipping.

## Planning helper

`scripts/incident_plan.py` only forms a safe next-step recommendation; it does not call bank tools or perform actions. Feed one JSON object on stdin and read one JSON object on stdout.

Input fields: `incident` (`lost`, `stolen`, `fraud_suspected`, or `other`), `customer_requests_human` (boolean), `temporary_freeze_requested` (boolean), `closure_authorized` (boolean or null), `verification_status` (`verified`, `not_verified`, or `unknown`), `reported_cards` (array of strings), and `actions_completed` (array of factual strings).

Validate its output before use: a security incident plus `customer_requests_human: true` must recommend `transfer_to_human_agents` with `fraud_or_security_concern`; its summary must not state a requested action as completed.
