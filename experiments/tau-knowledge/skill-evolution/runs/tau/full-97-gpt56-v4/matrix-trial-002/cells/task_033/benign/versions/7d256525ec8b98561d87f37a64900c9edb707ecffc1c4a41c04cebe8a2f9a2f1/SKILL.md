---
name: credit-card-payment-reflection-incident-transfer
version: 1.1.0
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

Maintain two per-conversation state values: (1) the count of qualifying requests to speak with, be connected to, or be transferred to a human specialist for this same payment-reflection issue, and (2) the number of successfully completed initial internal stages. Count a request once, even if it is phrased urgently or repeated within one message. Do not infer a request solely from frustration or a request for general help.

Advance the completed-stage value only after the matching discoverable tool call succeeds. A failed or unknown prerequisite must be retried or handled through an available recovery path; it must not be treated as complete or allow the next named tool to be skipped. When the incident applies and a qualifying request occurs, use the following stages in exact order. The first two internal calls are prerequisites, not replacements for a regular human transfer.

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

Only after both earlier discoverable tools have been successfully called, call `transfer_to_human_agents`. Use reason `technical_system_error`, since this is a documented backend payment-reflection incident. Provide a concise factual summary such as that the customer reports a statement payment deducted from checking but not reflected on the card statement balance, and that the two required incident transfer stages were completed. Do not include unverified identity data or claim that a payment was confirmed.

Then tell the customer that they are being connected to a human specialist. Once that regular transfer has been attempted, do not issue it again for a later request; retain its reported outcome and use an available recovery path instead.

## Failure handling

- Never call a discoverable agent tool before its matching unlock call.
- Never skip, reorder, or substitute the two named discoverable tools.
- Never call the regular transfer tool on the first or second qualifying request.
- If an unlock or call fails, do not falsely claim completion and do not advance the completed-stage value. State briefly that the transfer processing could not be completed at that moment; retry the same prerequisite only through an available recovery path, never by skipping to the next named tool.
- Do not repeat an operation whose outcome is reported as unknown.
- Keep customer-facing replies short and empathetic. Do not collect additional payment details, offer interest assurances, or give payment-management advice during the active incident.

## Runtime execution and validation

At runtime, construct a JSON state object from the **current** conversation and a current-time observation. It must include the helper fields documented in `scripts/incident_transfer_plan.py`: the current EST timestamp, the three independently established symptom booleans, whether the current message is a qualifying transfer request, the number of earlier qualifying transfer requests, the number of successfully completed initial stages, and whether the regular transfer must not be repeated. Do not place customer names, account numbers, payment amounts, or precomputed task answers in that state.

Save or pipe that runtime state to the helper, for example:

```bash
python3 scripts/incident_transfer_plan.py < /path/to/current_incident_state.json
```

Validate the JSON result before acting: `applicable` must be true; every recommended discoverable call must be preceded by its matching unlock in the returned order; and a regular `transfer_to_human_agents` recommendation is valid only for the third qualifying request after both successful initial stages. The helper only recommends actions. The executor must perform returned banking-tool calls, record a completed initial stage only after its call succeeds, and then send the indicated customer-facing acknowledgement. If a prerequisite's outcome is failed or unknown, do not advance or infer that stage; follow the failure rules above.
