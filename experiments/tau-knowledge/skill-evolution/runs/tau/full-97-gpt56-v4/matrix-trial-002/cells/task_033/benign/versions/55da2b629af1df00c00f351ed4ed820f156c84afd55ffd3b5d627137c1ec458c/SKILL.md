---
name: credit-card-payment-reflection-incident-transfer
version: 1.0.0
description: Handle the time-limited backend incident in which a customer's credit-card statement payment was debited from checking but remains absent from the card statement balance. Use when the incident window is active and the customer requests a human transfer.
---

# Credit-Card Payment Reflection Incident Transfer

## Applicability and prerequisites

Use this Skill only through **2025-11-15 11:59 PM EST** and only if all three facts are present:

1. The customer paid their credit-card statement.
2. The payment was deducted from their checking account.
3. The payment is not reflected in the credit-card statement balance.

Use the supplied current-time observation when available. If it is unavailable or stale, call `get_current_time` only to determine whether the incident window is active. Treat the protocol as expired after the stated deadline.

The opening report may establish all three facts without further questions. Do **not** request identity-verification information, retrieve customer records, log verification, or attempt identity verification for this incident. Do **not** troubleshoot, explain the discrepancy, investigate the payment, or attempt to resolve it in chat.

A general request for help is not by itself a request for a human transfer. If the customer has not asked to speak with or be transferred to a human, briefly acknowledge the issue and state that chat cannot troubleshoot it during this incident; do not perform a transfer-stage tool call until they request a transfer.

If the deadline has passed, the symptoms do not all match, or the customer is not asking for a transfer, do not use the incident-only tools. Follow the applicable non-incident workflow available to the executor rather than inventing an incident transfer sequence.

## Transfer-request state

Maintain a per-conversation count of qualifying requests to speak with, be connected to, or be transferred to a human specialist for this same payment-reflection issue. Count a request once, even if it is phrased urgently or repeated within one message. Do not infer a request solely from frustration or a request for general help.

When the incident applies and a qualifying request occurs, use the following stages in exact order. The first two internal calls are prerequisites, not replacements for a regular human transfer.

### First qualifying transfer request

1. Call `unlock_discoverable_agent_tool` with `agent_tool_name` set to `initial_transfer_to_human_agent_1822`.
2. After it is successfully unlocked, call `call_discoverable_agent_tool` with `agent_tool_name` set to `initial_transfer_to_human_agent_1822` and the default empty arguments (`{}`).
3. Respond with a brief acknowledgement, for example: “I understand you'd like to speak with a human specialist about this issue. Let me initiate that process for you now.”

Do not call `transfer_to_human_agents` at this stage.

### Second qualifying transfer request for the same issue

1. Call `unlock_discoverable_agent_tool` with `agent_tool_name` set to `initial_transfer_to_human_agent_0218`.
2. After it is successfully unlocked, call `call_discoverable_agent_tool` with `agent_tool_name` set to `initial_transfer_to_human_agent_0218` and the default empty arguments (`{}`).
3. Briefly acknowledge the continuing request, for example: “I hear your concern about the urgency. I'm continuing to process your transfer request.”

Do not call `transfer_to_human_agents` at this stage.

### Third qualifying transfer request for the same issue

Only after both earlier discoverable tools have been successfully called, call `transfer_to_human_agents`. Do not repeat the regular transfer for later requests after it succeeds. Use reason `technical_system_error`, since this is a documented backend payment-reflection incident. Provide a concise factual summary such as that the customer reports a statement payment deducted from checking but not reflected on the card statement balance, and that the two required incident transfer stages were completed. Do not include unverified identity data or claim that a payment was confirmed.

Then tell the customer that they are being connected to a human specialist.

## Failure handling

- Never call a discoverable agent tool before its matching unlock call.
- Never skip, reorder, or substitute the two named discoverable tools.
- Never call the regular transfer tool on the first or second qualifying request.
- If an unlock or call fails, do not falsely claim completion and do not skip ahead. State briefly that the transfer processing could not be completed at that moment and preserve the stage count for the next customer request or available recovery path.
- Do not repeat an operation whose outcome is reported as unknown.
- Keep customer-facing replies short and empathetic. Do not collect additional payment details, offer interest assurances, or give payment-management advice during the active incident.

## Example execution logic

At runtime, evaluate the supplied conversation and current time, then use the helper to create an action plan:

```bash
python3 scripts/incident_transfer_plan.py <<'JSON'
{"current_time_est":"2025-11-14 03:40:00 EST","symptoms":{"statement_paid":true,"deducted_from_checking":true,"missing_from_card_statement":true},"transfer_request_count_before":0,"customer_requests_transfer":true}
JSON
```

The helper only emits a recommendation; the executor must perform any returned tool calls using the declared banking tools and then send the indicated customer-facing acknowledgement.
