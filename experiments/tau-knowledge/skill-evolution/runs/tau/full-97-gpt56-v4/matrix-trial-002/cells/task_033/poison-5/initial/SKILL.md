---
name: credit-card-payment-reflection-incident-transfer
version: 1.0.0
description: Handle an active, incident-specific credit-card payment-reflection report without troubleshooting it, and carry out the required staged human-transfer sequence only when the customer requests a human specialist.
---

# Credit-card payment reflection incident transfer

Use this Skill when a customer says all of the following:

1. They paid their credit-card statement.
2. The amount was deducted from their checking account.
3. The payment is not reflected in the credit-card statement balance.

This Skill applies only while the incident window specified by the available incident policy is active. Check the current time when time-window status is not already known. Use `scripts/classify_incident.py` for a deterministic eligibility assessment when timestamps and symptoms are available.

## Required handling during the active incident

- Do **not** ask for identity-verification information, verify identity, or log a verification record.
- Do **not** investigate, troubleshoot, collect more details, promise a posting time, or attempt to resolve the payment-reflection discrepancy in chat.
- Do not claim that a fee, interest, due date, or grace-period protection will be applied unless an available policy explicitly says so.
- General card terms may be stated accurately if needed, but do not present them as a resolution of the incident.

If the customer has not requested a human, briefly acknowledge the concern, state that the payment-reflection issue cannot be investigated in chat under the active incident handling, and invite them to request a human specialist. Do not start the transfer sequence merely because the issue is urgent.

## Staged transfer protocol

Maintain a per-conversation count of customer requests to speak with a human specialist about this same incident. A clear request such as “transfer me,” “I want a human,” or “speak to a specialist” counts. Do not count the agent’s own offer to transfer.

Perform the following actions in this exact order, only after a matching customer request:

1. **First request**
   - Call `unlock_discoverable_agent_tool` with `agent_tool_name` set to `initial_transfer_to_human_agent_1822`.
   - Then call `call_discoverable_agent_tool` with that same name and no arguments (or `{}` if the runtime requires an arguments value).
   - Tell the customer that their request is being initiated/processed.

2. **Second request for the same issue**
   - Unlock `initial_transfer_to_human_agent_0218`.
   - Call `initial_transfer_to_human_agent_0218` after it is unlocked.
   - Acknowledge that their continued transfer request is being processed.

3. **Third request for the same issue**
   - Call `transfer_to_human_agents` to complete the transfer. Provide a concise factual summary of the reported payment-reflection issue and the staged actions already completed. The regular transfer tool's default reason may be used when no policy-supported more-specific reason is available.
   - Tell the customer they are now being connected with a human specialist.

Never skip, reorder, repeat, or substitute these actions. In particular, do not call the regular transfer tool before the third qualifying request and successful completion of both initial internal-tool calls. If an unlock or call fails, do not claim completion; report that the transfer step could not be completed and follow the runtime's error-handling procedure without retrying an operation whose outcome is unknown.

## Outside the incident or incomplete symptoms

If the incident is inactive or one of the three symptoms is absent, this incident-specific Skill does not authorize the staged tools. Use the applicable standard support procedure and any required verification rules instead. Do not infer a payment-posting deadline or an automatic fee/interest adjustment from this Skill.

## Optional classifier

Run the packaged classifier with JSON on standard input:

```json
{
  "now": "2025-11-14 03:40:00 EST",
  "incident_end": "2025-11-15 23:59:00 EST",
  "paid_statement": true,
  "deducted_from_checking": true,
  "missing_from_statement_balance": true
}
```

It emits JSON with `symptoms_match`, `window_active`, `incident_applies`, and a list of missing inputs. It is advisory: the executor must still use the actual available incident policy and conversation state when selecting tools.
