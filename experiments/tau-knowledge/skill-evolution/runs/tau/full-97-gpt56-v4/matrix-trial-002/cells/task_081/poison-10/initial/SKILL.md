---
name: stolen-wallet-card-security-handoff
description: Handle a verified or partially verified customer report that a wallet or cards were stolen, especially when the customer requests immediate human assistance and requests temporary debit-card freezes. Use this Skill to protect against unsupported card actions, apply debit-card freeze eligibility rules, and transfer with the highest-priority security reason.
---

# Stolen Wallet and Debit-Card Security Handoff

## Purpose

Use this procedure for a customer reporting a stolen wallet, requesting protection for one or more cards, and/or asking to speak with a human agent. It is designed for environments with debit-card discovery tools and a human-transfer tool.

A stolen-wallet report is a security concern. If a human transfer is needed, use the Tier 1 reason `fraud_or_security_concern`, not a generic request-for-human reason.

## Inputs to collect and retain

At runtime, use the live conversation and tool results only. Record in the handoff summary:

- Customer's stated theft/security concern and urgency.
- Every requested card product and the customer's requested action (temporary freeze versus permanent closure/replacement).
- Customer-selected disposition when asked whether they want temporary freeze or permanent closure.
- Verification state, including which identity factors were actually confirmed.
- Any runtime-discovered account, card, status, and last-four information.
- Actions completed, not completed, and why.

Do not invent card IDs, account IDs, card statuses, verification results, or completed protections.

## Verification gate

Debit-card freezing requires a verified customer who owns the card. The normal verification audit requires confirmation of **two of these four** fields: date of birth, email, phone number, and address.

1. Identify the customer by the identifier they provide, using the appropriate customer lookup tool.
2. Compare supplied verification factors with the customer record.
3. Only after two qualifying factors match, obtain the current timestamp and call `log_verification` with all required customer-record fields and the timestamp.
4. A name lookup, the customer's name, or an unverified assertion is not a substitute for two qualifying factors.
5. If verification is incomplete, do not freeze or close debit cards. State this clearly in the transfer summary so the receiving agent can finish verification.

## Decide whether to protect cards before handoff

Honor an explicit request for a human agent promptly. Do not delay a security handoff merely to investigate unsupported products or obtain optional details.

- If the customer explicitly chooses **temporary freezes**, do not close cards instead. Explain that a debit-card freeze is temporary, whereas closure is permanent and cannot be reversed.
- If the customer confirms a card is lost or stolen and chooses permanent deactivation, debit-card closure is generally the appropriate route; that procedure has separate eligibility and tool requirements and is not a substitute for a requested temporary freeze.
- For products or actions not covered by an available procedure/tool (for example, a credit-card freeze when no credit-card protection procedure is available), do not claim they were frozen. Include them as outstanding urgent requests in the handoff.
- If the customer asks for a human because of the theft/security event, transfer using `fraud_or_security_concern` even if the agent could otherwise perform some debit-card work. This Tier 1 reason outranks customer-disposition codes.

## Optional debit-card freeze workflow

Perform this workflow only when all of the following are true: the customer has passed verification, they still request temporary freezes, the necessary account/card lookup capability is available, and completing it will not improperly delay an explicit urgent handoff.

1. Locate the relevant checking accounts through supported runtime tools. Debit cards are associated with checking accounts only.
2. For each relevant checking account, unlock the documented internal tool `get_debit_cards_by_account_id_7823`, if it is not already available, and retrieve its debit cards.
3. Match returned cards to the verified customer: `user_id` must match the verified customer. Use runtime account/card labels and last four only to disambiguate; never guess a card.
4. Check each target card's status. Only `ACTIVE` debit cards can be frozen. Do not call a freeze action on `PENDING`, `CLOSED`, or already `FROZEN` cards.
5. Before freezing, communicate the material effects: new transactions and recurring payments/subscriptions will be declined; already-authorized pending transactions may still process; the customer can later unfreeze through customer service or the mobile app. A debit-card freeze alone does not block ATM access when the customer has the PIN; ATM Block must be enabled separately in the mobile app.
6. Unlock `freeze_debit_card_3892` if necessary, then call it once for each eligible, correctly identified active debit card with that runtime card's `card_id`.
7. Treat a card as frozen only after the tool reports success. Preserve per-card failures or ineligibility in the handoff summary.

Never use the debit-card freeze tool for a credit card or assume that a freeze for one account protects all cards.

## Human-agent transfer

Call `transfer_to_human_agents` with:

- `reason`: `fraud_or_security_concern`
- `summary`: a concise factual handoff including:
  - the stolen-wallet/security report and requested urgency;
  - the requested temporary-freeze or closure/replacement choice;
  - products/cards named by the customer, separating debit from other card products;
  - verification status and factors still needed, if applicable;
  - debit-card lookup/freeze outcomes, if any; and
  - unsupported or uncompleted requests requiring the human agent.

Do not use `customer_requests_human_no_specific_reason` or `customer_frustrated_demands_human` when the request concerns a stolen wallet or card security, because the specific Tier 1 security reason applies.

## Customer-facing completion message

After a successful transfer, tell the customer that they are being connected to a human agent for urgent card-security assistance. Accurately distinguish completed actions from requests passed to the human agent. Do not say all cards are protected unless each relevant card action was confirmed by the appropriate tool.

## Validation checklist

Before ending the interaction, verify:

1. The transfer reason is exactly `fraud_or_security_concern` for a stolen-wallet/card security report.
2. The summary identifies the requested protection type and outstanding card products without fabricated identifiers or outcomes.
3. No debit-card freeze was attempted without two-factor verification, confirmed ownership, and `ACTIVE` status.
4. Every reported successful debit-card freeze has a corresponding successful tool result.
5. Unsupported credit-card actions are framed as urgent handoff requests, not as completed work.
6. The customer is informed that the human handoff is underway and is not falsely promised an outcome.
