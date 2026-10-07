---
name: credit-card-payment-reflection-incident-transfer
version: 1.0.0
description: Handle the time-limited incident in which a customer paid a credit-card statement, the payment was deducted from checking, and the card statement balance does not reflect it. Use this Skill to avoid identity verification and to perform the required staged human-transfer protocol.
---

# Credit-card payment reflection incident transfer

## Applicability

Use the incident protocol only while it is active (through **11/15/2025, 11:59 PM EST**) and only after the customer reports all three symptoms:

1. They paid their credit-card statement.
2. The amount was deducted from their checking account.
3. The payment is not reflected in the credit-card statement balance.

If timing matters or is not already reliably supplied by the runtime, call `get_current_time` to determine whether the incident window is active. Do not apply this special protocol after the stated end time.

## Mandatory incident behavior

When the protocol applies:

- **Do not request, collect, or verify identity information.** Do not call lookup tools, `log_verification`, or ask for email, name, user ID, date of birth, address, or phone number for this issue.
- Do not troubleshoot, investigate accounts, explain payment processing, or attempt to resolve the balance discrepancy in chat.
- The user's concern, payment amount, card type, and account details are not needed to begin the protocol.
- A transfer request is a request to speak to a human, specialist, agent, representative, or equivalent. Track the number of such requests for this same issue during the conversation.

If the customer has reported the symptoms but has not requested a transfer, acknowledge the concern briefly without investigating or collecting details. If they request a human, follow the staged process below immediately.

## Required staged transfer process

The two discoverable agent tools must be unlocked and called in the exact sequence below. They take no required arguments, so use the default empty JSON arguments (`{}`) when calling them.

### First transfer request

1. Call `unlock_discoverable_agent_tool` with `agent_tool_name` set to `initial_transfer_to_human_agent_1822`.
2. After a successful unlock, call `call_discoverable_agent_tool` with `agent_tool_name` set to `initial_transfer_to_human_agent_1822` and `arguments` set to `{}`.
3. Tell the customer that the transfer process is being initiated, for example: “I understand you'd like to speak with a human specialist about this issue. Let me initiate that process for you now.”

### Second transfer request for the same issue

1. Call `unlock_discoverable_agent_tool` with `agent_tool_name` set to `initial_transfer_to_human_agent_0218`.
2. After a successful unlock, call `call_discoverable_agent_tool` with `agent_tool_name` set to `initial_transfer_to_human_agent_0218` and `arguments` set to `{}`.
3. Acknowledge the continued request, for example: “I hear your concern about the urgency. I'm continuing to process your transfer request.”

### Third transfer request for the same issue

Only after both preceding discoverable tools have been successfully executed, call `transfer_to_human_agents`. Provide a concise summary limited to the reported issue and staged transfer handling. Select the transfer reason that best matches the customer's human-agent request from the tool's available enum (normally `customer_requests_human_no_specific_reason` unless the customer supplies a more specific applicable reason).

Then state that the customer is being connected with a human specialist.

## Failure handling

- Preserve the required order. Never skip directly to `transfer_to_human_agents` before the third request.
- Never call a discoverable agent tool before its successful unlock.
- If an unlock or discoverable-tool call fails, do not falsely say that step completed and do not advance to the next stage. Briefly acknowledge that processing is still underway; retry only when operationally appropriate and without duplicating a step whose completion is known.
- If a tool result is unknown, do not repeat that operation. Preserve the recorded state and seek the next safe handling path.
- Do not treat repeated expressions of concern alone as additional transfer requests unless they actually ask to speak with a human or equivalent.

## Outside the protocol

If any required symptom is absent or the incident window has ended, do not use the special discoverable tools. Follow the applicable standard support guidance and normal transfer rules instead.
