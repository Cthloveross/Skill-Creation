---
name: secure-debit-dispute-human-handoff
description: Handle a customer who requests a human agent while reporting debit-card disputes, especially unauthorized activity, a lost/stolen card, security concerns, ATM cash discrepancies, or recurring charges after cancellation. Use this Skill to select the highest-priority transfer reason and provide a complete, factual handoff without attempting unsupported card or dispute actions.
---

# Secure Debit-Card Dispute Human Handoff

## When to use
Use this Skill when a customer asks to speak with a human and describes debit-card transaction problems. It is particularly applicable if the report includes unauthorized transactions, a lost or stolen card, fraud/security concerns, or multiple disputes requiring review.

## Required outcome
1. Select the highest-priority applicable `transfer_to_human_agents` reason.
2. Transfer the customer promptly with a concise, useful summary.
3. Tell the customer that they are being connected to the appropriate team.

Do not claim that a dispute was filed, a card was frozen, a recurring-payment block was placed, or a replacement was ordered unless the corresponding banking action was actually completed through an available normal banking tool.

## Decision procedure

### 1. Identify whether security/fraud is involved
Treat the case as a security concern when the customer reports one or more of the following:
- A debit-card transaction they did not make or authorize.
- A lost or stolen debit card, particularly alongside an unknown transaction.
- Suspected identity theft, account compromise, card fraud, or other suspicious activity.
- A transaction they do not recognize where the facts indicate potential fraud.

If any of these conditions applies, use:

`reason: fraud_or_security_concern`

This Tier 1 reason takes priority over the customer's general request for a human, frustration, or another dispute type. A customer reporting transactions they did not make warrants security-team escalation.

### 2. If no security concern applies, select the highest matching reason
Use the priority order below only when no Tier 1 security reason applies:
- A complex billing dispute needing specialist review: `complex_billing_dispute`.
- A specialized department outside available scope: `specialized_department_required`.
- General dissatisfaction with service and a supervisor request: `supervisor_request_service_complaint`.
- Frustration and a demand for a human: `customer_frustrated_demands_human`.
- A simple preference for a human with no specific reason: `customer_requests_human_no_specific_reason`.
- If nothing else fits: `other`, with a detailed summary.

Never use a lower-tier customer-disposition reason if a specific operational or security reason applies.

## Information to include in the handoff summary
Use only details the customer supplied or details obtained through permitted tools. Do not invent missing facts. Include:

- Customer identifier available from the conversation or account lookup (for example, name and user ID if known).
- That the customer requested a human transfer.
- The security trigger: unauthorized activity, lost/stolen card, suspected fraud, or other relevant concern.
- Each reported transaction separately, when known:
  - card/account identifier or last four digits (if provided)
  - date
  - amount
  - merchant, ATM, or descriptor
  - reported issue (unauthorized, ATM partial/no cash, post-cancellation recurring charge, etc.)
- For ATM discrepancies, whether it was a bank ATM or third-party ATM, ATM identifier if supplied, requested amount, amount received, and whether the customer reports the receipt shows a different amount.
- For post-cancellation recurring charges, the reported cancellation timing and the charge details.
- Facts that are unknown or still needed, such as missing details for another transaction.
- Actions actually attempted, if any. If no action was taken before immediate escalation, say so plainly.

Keep the summary factual. Do not label a transaction as a particular dispute category unless the customer facts support it. A past charge after cancellation can be noted as a likely `recurring_charge_after_cancellation` issue for the human agent; an ATM that dispensed less cash than requested can be noted as an ATM cash discrepancy. Do not file either dispute before handoff unless all requirements are satisfied and the customer has requested that action rather than an immediate human transfer.

## Handoff execution

1. If the customer has supplied enough to establish a security concern, do not delay the transfer merely to obtain every disputed transaction detail or complete dispute intake.
2. Construct a single narrative `summary` covering the known information and explicitly flag missing information.
3. Call `transfer_to_human_agents` with the chosen reason and summary.
4. After a successful transfer, provide a short confirmation. Avoid revealing internal fraud indicators or codes.

Suggested customer-facing confirmation:

> I’m connecting you with our security team so they can help review the unauthorized activity and the other debit-card issues. Please have any transaction details available for the specialist.

## Important boundaries

- Do not disclose internal security decline codes, fraud-alert classifications, or bank-internal investigative details.
- Do not attempt to clear a security alert or reactivate a card as part of this handoff.
- Do not state that Regulation E liability, provisional credit, or dispute eligibility has been determined unless the required information was gathered and a supported process completed.
- Formal debit-dispute filing normally requires verified identity, an eligible transaction, transaction and discovery dates, card/account identifiers, and category-specific facts. A transfer request caused by security concerns should be escalated rather than blocked on those intake requirements.
- If the customer reports a lost/stolen card and denies having reported it, treat that as a heightened security concern and transfer rather than attempting to resolve it independently.

## Validation checklist
Before calling the transfer tool, confirm:
- The summary says why the transfer is needed.
- `fraud_or_security_concern` is selected whenever unauthorized debit activity, a lost/stolen card, or suspected fraud is present.
- All transaction facts in the summary came from the customer or permitted lookup results.
- Missing fourth or additional transaction details are explicitly marked as unavailable rather than fabricated.
- The summary does not promise completed banking actions that were not performed.
