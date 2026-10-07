---
name: lost-or-stolen-wallet-security-transfer
description: Handle a customer who reports a lost or stolen wallet/card and requests a human agent. Use this Skill to prioritize immediate security escalation, select the correct transfer reason, and avoid unsupported card actions.
---

# Lost or Stolen Wallet: Security Transfer

Use this Skill when a customer reports a wallet, debit card, or other payment cards as lost/stolen and asks to speak with a human. A reported wallet theft is a security concern, so it takes priority over general customer-request or frustration transfer reasons.

## Required handling

1. Acknowledge the urgency without disclosing internal security details.
2. If the customer has requested a human agent, transfer them promptly using `transfer_to_human_agents`.
3. Use `fraud_or_security_concern` as the transfer `reason` for a lost/stolen wallet or card security situation. This Tier 1 reason outranks customer disposition reasons such as `customer_frustrated_demands_human` or `customer_requests_human_no_specific_reason`.
4. Provide a concise, factual `summary` for the receiving agent. Include:
   - reported lost/stolen wallet or cards;
   - card products/accounts the customer named, if any;
   - that the customer requests urgent human assistance; and
   - actions actually completed and important blockers (for example, identity not fully verified or debit-card IDs unavailable).
   Do not put unnecessary full card numbers, date of birth, address, or other sensitive details in the summary.
5. Perform the transfer immediately once the request is clear. Do not send a separate pre-transfer message such as “I am connecting you” before calling the tool: in runtimes that recognize transfer language, that message can end the conversation before the transfer operation is recorded. Do not ask additional questions that delay an explicitly requested security transfer. After a successful tool result, give a brief confirmation that the transfer was completed if the conversation remains open. This confirmation must follow, never substitute for, the tool call.

## Card-action boundaries before transfer

- Do **not** claim any card has been frozen, closed, replaced, or secured unless the corresponding banking action completed successfully.
- A debit-card freeze requires verified identity, customer ownership, an ACTIVE card, the actual `card_id`, and the normal `freeze_debit_card_3892` action. Do not freeze based only on a card type, account nickname, or last four digits.
- A lost/stolen card may require permanent close/replacement rather than a temporary freeze. Let the human security agent complete the appropriate card procedure when transferring.
- Do not freeze credit cards using debit-card freeze procedures. If the customer has credit-card accounts, convey that fact to the human agent; the relevant security protocol supports offering a replacement credit card, not freezing it with a debit-card tool.
- If identity verification has not met the available verification requirement, do not log verification and do not take protected account actions. Transfer can still proceed for the security concern.

## Transfer call

Invoke the normal banking tool directly and **before any transfer-announcement message**, with the selected reason and a case-specific summary. The tool call—not language promising a transfer—is the required operational action. After a successful result, if a final user-facing reply is needed, say only that the transfer has been completed; do this after the tool call:

```text
transfer_to_human_agents(
  reason="fraud_or_security_concern",
  summary="Customer reports a stolen wallet containing [named debit/credit cards] and requests urgent human assistance. [State completed actions or blockers truthfully, e.g. no debit card IDs available and no card action completed.]"
)
```

The script below is optional decision support. It accepts only case facts and emits a transfer recommendation; it never performs bank actions. Read its JSON output, tailor the summary to the actual conversation, and call the banking transfer tool yourself.

## Validation

Immediately before calling the transfer tool, confirm all of the following:

- The reported situation involves a lost/stolen wallet/card or another concrete security risk.
- The customer requested a human agent.
- The reason is exactly `fraud_or_security_concern`.
- The summary says only what was reported, observed, or completed; it does not assert an unperformed freeze/closure/replacement.
- No debit-card action is represented as completed without identity, ownership, ACTIVE status, `card_id`, and a successful tool result.
- If a confirmation is sent, it follows a successful human-transfer tool result and does not imply that the cards were frozen or otherwise changed.
