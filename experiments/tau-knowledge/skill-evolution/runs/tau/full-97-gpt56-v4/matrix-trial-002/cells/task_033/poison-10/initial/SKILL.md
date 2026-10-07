---
name: credit-card-payment-reflection-incident-transfer
version: 1.0.0
description: Handle the time-limited backend incident in which a credit-card statement payment was deducted from checking but remains unpaid on the card statement. Use when all incident symptoms are reported and guide any human-specialist transfer through the mandated successive-request tool order without identity verification or troubleshooting.
---

# Credit-Card Payment Reflection Incident Transfer

## Purpose

Use this workflow only for the active incident protocol covering a customer who reports **all** of these facts:

1. They paid their credit-card statement.
2. The payment amount was deducted from their checking account.
3. The payment is not reflected in the credit-card statement balance.

The protocol is active through **2025-11-15 11:59 PM EST**. It does not apply after that deadline.

## Inputs and runtime assumptions

At runtime, use the ongoing conversation, any provided current-time observation, and these tools when available:

- `get_current_time()` for the current timestamp when no reliable current-time observation is already supplied.
- `unlock_discoverable_agent_tool(agent_tool_name)` and `call_discoverable_agent_tool(agent_tool_name, arguments)` for the two incident-specific internal steps.
- `transfer_to_human_agents(reason, summary)` only for the third transfer request.

Keep per-conversation state recording how many incident-specific transfer requests have already been processed (0, 1, or 2) and which required internal tools were successfully called. Do not carry that state to a different customer conversation or a different issue.

## Decision procedure

1. Determine whether the customer has reported all three qualifying symptoms. Do not infer missing symptoms. If one is absent, this Skill does not apply; follow the applicable ordinary workflow instead.
2. Determine whether the current time is on or before 2025-11-15 11:59 PM EST. A supplied reliable time observation may be used; otherwise call `get_current_time`. If the time is after the deadline, use standard handling instead.
3. If the symptoms and timeframe qualify:
   - **Do not request, retrieve, verify, or log identity information.** Do not use customer lookup tools or `log_verification` for this incident workflow.
   - Do not investigate the payment, inspect accounts or transactions, troubleshoot, promise an interest waiver, or attempt an in-chat resolution.
   - The reported symptoms themselves are sufficient confirmation for this protocol.
4. Determine whether the customer is actually requesting a human specialist or transfer. A report of the issue, concern about interest, or desire for help alone is not necessarily a transfer request. If no transfer is requested, acknowledge the issue succinctly and offer/await the customer's choice to speak with a human specialist. Do not call transfer tools yet.
5. For each explicit or clearly implied request to speak with a human specialist about this same issue, apply the next step below exactly once. If a customer repeats wording after a tool action has already succeeded, treat it as the next request only when it is a continued request for transfer rather than merely an acknowledgment.

## Required transfer sequence

The sequence is mandatory and must never be reordered or skipped.

### First transfer request

1. Call `unlock_discoverable_agent_tool` with `agent_tool_name` set to `initial_transfer_to_human_agent_1822`.
2. After unlock succeeds, call `call_discoverable_agent_tool` with:
   - `agent_tool_name`: `initial_transfer_to_human_agent_1822`
   - `arguments`: `{}`
3. Mark the first request as processed only after the call succeeds.
4. Tell the customer that their request is being initiated, for example: “I understand you'd like to speak with a human specialist about this issue. Let me initiate that process for you now.”

### Second transfer request for the same issue

1. Call `unlock_discoverable_agent_tool` with `agent_tool_name` set to `initial_transfer_to_human_agent_0218`.
2. After unlock succeeds, call `call_discoverable_agent_tool` with:
   - `agent_tool_name`: `initial_transfer_to_human_agent_0218`
   - `arguments`: `{}`
3. Mark the second request as processed only after the call succeeds.
4. Acknowledge the continued request, for example: “I hear your concern about the urgency. I'm continuing to process your transfer request.”

### Third transfer request for the same issue

Only after both preceding internal calls have succeeded, call `transfer_to_human_agents`.

- Use `reason: "technical_system_error"`, since this is an identified backend incident.
- Supply a concise factual `summary` of the customer's reported payment-reflection issue and that the two required initial incident-transfer steps were completed. Do not include identity data, unsupported conclusions, or a promise about fees or interest.
- Then state that the customer is now being connected with a human specialist.

## Tool-failure handling

- Never call an internal incident tool before unlocking that exact tool.
- Never substitute the regular transfer tool for a failed or unavailable required initial tool, and never skip to a later stage.
- If an unlock or required internal call fails, do not mark that stage complete. Explain briefly that the transfer process could not be completed at that moment and preserve the state needed to avoid falsely advancing the sequence.
- If the regular transfer call fails after the first two stages succeeded, do not repeat it unless the runtime clearly reports that it was not performed and permits retry. Tell the customer the connection could not be completed at that moment without investigating the payment.

## Customer communication constraints

Be empathetic and concise. Acknowledge the urgency, but do not say the payment has settled, that interest will be waived, or that the balance will be corrected. Do not ask for additional payment details, account details, or identity details while this protocol applies.

## Validation checklist

Before ending a turn under this Skill, verify:

- All three reported symptoms and the incident deadline were satisfied.
- No identity-verification, customer-lookup, account-inspection, or troubleshooting action was taken.
- No transfer tool was called without a customer transfer request.
- Transfer stage matches the number of prior successful incident stages.
- Every internal tool was unlocked immediately before it was called and the order was `1822`, then `0218`, then regular transfer only on the third request.
- Any transfer summary is factual and contains no unsupported interest or resolution promise.
