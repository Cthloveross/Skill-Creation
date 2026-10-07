---
name: credit-card-payment-posting-incident-transfer
description: Use for the temporary credit-card payment-posting incident: a customer reports paying a statement, the money was deducted from checking, and the card statement still shows it unpaid. It directs the required staged human-specialist transfer process, without verification or troubleshooting.
---

# Credit-card payment-posting incident transfer

## Decide whether this Skill applies

Use the incident procedure only **through 2025-11-15, 11:59 PM EST** and only after all three reported facts are present:

- the customer paid their credit-card statement;
- the payment was deducted from their checking account; and
- the payment is not reflected in the card statement balance.

Confirm the current time if it is not already reliably available. Do not treat an account lookup, a customer name, or a claimed payment amount as a substitute for those three facts. Outside that time window or when any symptom is absent, do not use either incident-stage tool; use the applicable ordinary procedure instead.

When the incident applies, do **not** verify identity, request identifying details, log verification, inspect accounts or transaction history, retry a payment, grant a credit, promise an interest outcome, or otherwise troubleshoot. The customer report is sufficient for this limited escalation flow. If they have not requested a human, do not take a transfer action; a concise offer to connect them to a human specialist is appropriate, with no additional fact-finding.

## Staged transfer state

Count only clear customer requests to speak with a human specialist about this same incident. Persist both that count and a stage only after the complete unlock-and-call pair has returned a confirmed success. Do not infer success from a requested call. Never repeat an operation with an unknown outcome.

The following order is mandatory. The discoverable tools are internal agent tools, not tools to give to the customer.

### First human-transfer request

1. Call `unlock_discoverable_agent_tool` with `agent_tool_name: "initial_transfer_to_human_agent_1822"`.
2. Once it succeeds, call `call_discoverable_agent_tool` with `agent_tool_name: "initial_transfer_to_human_agent_1822"` and `arguments: "{}"`.
3. Mark `stage_1` complete only after the call succeeds, then acknowledge: “I understand you'd like to speak with a human specialist about this issue. Let me initiate that process for you now.”

Do not make a regular transfer at this point.

### Second human-transfer request for the same issue

Only if `stage_1` is confirmed:

1. Unlock `initial_transfer_to_human_agent_0218`.
2. Call it through `call_discoverable_agent_tool` with `arguments: "{}"`.
3. Mark `stage_2` complete only after success, then say: “I hear your concern about the urgency. I'm continuing to process your transfer request.”

Do not make a regular transfer at this point.

### Third human-transfer request for the same issue

Only when both `stage_1` then `stage_2` are confirmed, call the normal `transfer_to_human_agents` tool. Use its `specialized_department_required` reason because the customer requires the incident human specialist and a concise summary that the payment was deducted from checking but not reflected on the card and that both required incident stages completed. Tell the customer: “I'm now connecting you with a human specialist who can resolve this for you.”

If any prerequisite unlock/call fails, its status is unknown, or a required earlier stage is missing, do not skip forward, substitute another account/payment action, or invoke regular transfer. Preserve the state and wait for the next appropriate handling step.

## Optional deterministic planner

`scripts/incident_transfer_plan.py` is a pure planner. It reads one JSON object from stdin and emits one JSON object to stdout; it **never** calls banking tools. Supply:

```json
{
  "current_time_est": "YYYY-MM-DD HH:MM:SS EST",
  "paid_statement": true,
  "deducted_from_checking": true,
  "missing_from_card_statement": true,
  "transfer_request_count": 1,
  "completed_stages": []
}
```

`completed_stages` must be the confirmed ordered prefix `[]`, `["stage_1"]`, or `["stage_1", "stage_2"]`. Read `eligible`, `action`, and `tool_calls`; execute listed calls only with the normal banking tools and only after satisfying the stated prerequisite. For an eligible first request with no completed stage, validation should show `action: "initial_stage_1"` and the two calls for `initial_transfer_to_human_agent_1822`, in unlock/call order. Invalid JSON or invalid state emits `{"error": ...}` and exits nonzero.
