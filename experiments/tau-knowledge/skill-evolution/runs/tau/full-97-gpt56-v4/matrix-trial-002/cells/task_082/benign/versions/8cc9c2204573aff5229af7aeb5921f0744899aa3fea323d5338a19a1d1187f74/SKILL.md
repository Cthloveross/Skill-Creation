---
name: secure-dispute-human-transfer
description: Handle a customer request for a human agent involving disputed debit-card transactions, especially unauthorized activity or a lost/stolen card. Use this Skill to choose the highest-priority transfer reason and create a concise, actionable human-agent summary from the conversation.
---

# Secure Dispute Human Transfer

## Purpose

Prepare and perform a human-agent transfer when the customer reports several transaction disputes and wants a person. Preserve all transaction details already supplied so the receiving agent can address each issue without asking the customer to repeat it.

## Required reasoning

1. Read the complete conversation and any supplied clarifications before transferring.
2. Identify every disputed transaction and capture, where stated:
   - affected account/card descriptor and last four digits;
   - date;
   - amount;
   - merchant or ATM name and ATM identifier;
   - dispute type and the customer's stated explanation;
   - relevant security context, such as a lost card not yet reported.
3. Select the transfer reason using the tiered reason-code policy, always choosing the highest applicable tier.
   - If any report includes unauthorized transactions, suspected fraud, identity theft, a lost/stolen card with suspicious activity, or another security concern, use `fraud_or_security_concern`.
   - Do not downgrade such a case to a billing-dispute or generic human-request reason merely because other disputes are also present.
   - Use another reason only if no higher-priority security/operational reason applies.
4. Do not attempt to invent missing dates, amounts, card details, merchant names, or account identifiers. If material information is absent, say that it was not provided in the transfer summary.

## Transfer procedure

Call `transfer_to_human_agents` once with:

- `reason`: the selected highest-priority code.
- `summary`: a clear, factual handoff note. State that the customer requested a human; identify the primary security/fraud issue first when applicable; then list each dispute separately. Retain the customer's distinction between unauthorized purchases, a cancelled-subscription/recurring billing issue, and an ATM cash-dispense discrepancy. Include the requested amount and cash actually received for an ATM discrepancy when available.

The summary should be useful to the human agent but should not assert that a dispute, refund, card block, replacement, or investigation has already been completed unless a banking tool explicitly reported that outcome.

## Constraints

- Transfer actions must be performed only through the declared `transfer_to_human_agents` banking tool.
- Do not use customer lookup, identity verification, account-change, or transaction lookup tools unless independently required to answer a separate request; a handoff summary can rely on information the customer has already provided.
- Do not log verification unless the customer has actually completed the required identity verification process.
- Do not expose full card numbers or fabricate personally identifying information.
- After a successful transfer-tool response, give the customer a short confirmation that they are being connected to a human agent. If the tool reports failure, explain only the reported limitation and do not claim the transfer occurred.

## Quality check before calling the tool

Confirm that the handoff summary:

- contains all distinct transactions mentioned in the conversation;
- labels each transaction with its correct dispute rationale;
- includes the lost-card/security context if present;
- uses `fraud_or_security_concern` whenever that security context or unauthorized activity is present; and
- contains no inferred facts or unsupported resolution promises.
