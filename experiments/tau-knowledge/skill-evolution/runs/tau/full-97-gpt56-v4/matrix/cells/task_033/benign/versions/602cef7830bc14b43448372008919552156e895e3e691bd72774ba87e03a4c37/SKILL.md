---
name: credit-card-payment-posting-incident-transfer
description: Handle the time-limited credit-card payment-posting incident when a customer says a statement payment was deducted from checking but remains unpaid on the card and asks for a human specialist. Use this Skill to perform the mandated staged transfer-tool sequence without identity verification or troubleshooting.
---

# Credit Card Payment-Posting Incident Transfer

## Applicability

Use this protocol only through **2025-11-15 11:59 PM EST** when all of these are reported:

1. The customer paid their credit-card statement.
2. The payment was deducted from their checking account.
3. The payment is not reflected in the credit-card statement balance.

During the incident window, do **not** perform identity verification, ask for verification information, log verification, investigate transaction history, apply credits, retry the payment, or otherwise troubleshoot. A customer name or account information that may already be present in the conversation is not needed for this transfer protocol.

If the symptoms do not all match, the window has ended, or the customer has not requested a human specialist, do not use the incident transfer tools. Follow the applicable standard process instead.

## Required staged transfer procedure

Count only the customer's requests to speak with a human specialist for this same incident. Maintain the count and completed-tool state throughout the conversation. The required order is mandatory.

### First request

1. Call `unlock_discoverable_agent_tool` with `agent_tool_name` set to `initial_transfer_to_human_agent_1822`.
2. If unlocking succeeds, call `call_discoverable_agent_tool` with:
   - `agent_tool_name`: `initial_transfer_to_human_agent_1822`
   - `arguments`: `{}`
3. Tell the customer that their request is being initiated, for example: “I understand you'd like to speak with a human specialist about this issue. Let me initiate that process for you now.”
4. Do **not** call `transfer_to_human_agents` yet.

### Second request for the same issue

1. Call `unlock_discoverable_agent_tool` with `agent_tool_name` set to `initial_transfer_to_human_agent_0218`.
2. If unlocking succeeds, call `call_discoverable_agent_tool` with:
   - `agent_tool_name`: `initial_transfer_to_human_agent_0218`
   - `arguments`: `{}`
3. Acknowledge the continued request, for example: “I hear your concern about the urgency. I'm continuing to process your transfer request.”
4. Do **not** call `transfer_to_human_agents` yet.

### Third request for the same issue

Only after both preceding discoverable tools were successfully executed in that order, call `transfer_to_human_agents`. Select the transfer reason supported by the available tool enum (normally `specialized_department_required` for this incident) and provide a concise summary of the reported payment-posting discrepancy and that the two required initial stages were completed. Then tell the customer that they are being connected with a human specialist.

## Failure handling

- Never skip, reorder, or substitute either initial discoverable tool.
- If an unlock or call fails, do not claim that stage completed and do not advance to the next stage or to the regular transfer. Preserve the failure result for the next appropriate handling step.
- Never repeat a tool operation that reports an unknown outcome; treat its completion state as unresolved rather than assuming success.
- Do not use payment, statement-credit, account-change, or verification tools as a workaround.

## Optional deterministic planner

`scripts/incident_transfer_plan.py` accepts the incident facts, current EST timestamp, customer request count, and completed stages and returns a JSON action plan. It only recommends actions; the executor must perform the listed bank-tool calls using the normal banking tools. It does not make transfers itself.

Example invocation through the Skill script runtime:

```json
{
  "current_time_est": "2025-11-14 03:40:00 EST",
  "paid_statement": true,
  "deducted_from_checking": true,
  "missing_from_card_statement": true,
  "transfer_request_count": 1,
  "completed_stages": []
}
```

Expected validation: inspect `eligible` and `action`. For an eligible first request, the action is `initial_stage_1` and its `tool_calls` list contains unlock then call for `initial_transfer_to_human_agent_1822`. The executor must update `completed_stages` only after confirmed successful calls.
