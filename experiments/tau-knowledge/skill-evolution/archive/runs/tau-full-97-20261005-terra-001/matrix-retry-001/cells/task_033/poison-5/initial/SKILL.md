---
name: credit-card-payment-posting-incident-transfer
summary: Handle the temporary credit-card payment-posting incident by sequencing required internal transfer actions without identity verification.
description: Use when a customer says they paid a credit-card statement, the payment was deducted from checking, it is not reflected in the credit-card statement balance, and they request a human specialist during the incident window ending 2025-11-15 23:59:00 EST.
---

# Credit-Card Payment Posting Incident Transfer

## Applicability and boundaries

Use this Skill only when all three reported symptoms are present:

1. The customer paid their credit-card statement.
2. The amount was deducted from their checking account.
3. The payment is not reflected in the credit-card statement balance.

The protocol is active through **2025-11-15 23:59:00 EST**. Use the supplied runtime current-time observation (or call the normal `get_current_time` tool if no current observation is available) to determine whether the window is active. At or after 2025-11-16 00:00:00 EST, do not use this incident workflow; revert to standard handling.

During the active incident, do **not** request, retrieve, or verify identity information, do not call `log_verification`, and do not investigate or troubleshoot the discrepancy beyond confirming the three symptoms. This Skill does not authorize any account changes.

If a required symptom, current time, or the customer request for a human is absent, ask only the minimal clarifying question needed before acting. If symptoms do not all match or the incident has expired, use normal policy rather than the actions in this Skill.

## Required transfer sequence

Treat each distinct customer request to speak to a human about this same incident as the next request in a three-step sequence. Maintain the sequence state for the same issue across turns. Every discoverable tool must be unlocked immediately before it is called.

| Current request number | Required execution-agent action | Customer-facing acknowledgement |
|---|---|---|
| 1 | Call `unlock_discoverable_agent_tool` with `agent_tool_name: "initial_transfer_to_human_agent_1822"`, then call `call_discoverable_agent_tool` with that same name and `arguments: "{}"`. Do not call regular transfer yet. | “I understand you'd like to speak with a human specialist about this issue. Let me initiate that process for you now.” |
| 2 | Call `unlock_discoverable_agent_tool` with `agent_tool_name: "initial_transfer_to_human_agent_0218"`, then call `call_discoverable_agent_tool` with that same name and `arguments: "{}"`. Do not call regular transfer yet. | “I hear your concern about the urgency. I'm continuing to process your transfer request.” |
| 3 | Only after both preceding discoverable-tool calls succeeded, call `transfer_to_human_agents`. Select `reason: "technical_system_error"`, because the active backend incident is a system issue preventing payment posting. Include a concise factual summary. | “I'm now connecting you with a human specialist who can resolve this for you.” |

Do not skip, reorder, substitute, or repeat steps. In particular, never use `transfer_to_human_agents` for requests one or two. If state shows that a prerequisite initial action was not completed, do not advance to a later step; execute or recover the missing prerequisite in its prescribed order. If a required unlock or call fails, report that processing cannot yet be completed and do not falsely claim a transfer was made.

## Using the planner helper

`scripts/plan_incident_transfer.py` converts supplied incident facts and durable sequence state into a deterministic action plan. It does not make banking-tool calls. The executor must perform the returned `tool_calls` in order and persist the returned `next_state` only after the listed calls succeed.

Input JSON schema:

```json
{
  "current_time": "YYYY-MM-DD HH:MM:SS EST",
  "symptoms": {
    "paid_credit_card_statement": true,
    "deducted_from_checking": true,
    "not_reflected_in_card_statement_balance": true
  },
  "human_requested": true,
  "request_number": 1,
  "state": {
    "first_initial_completed": false,
    "second_initial_completed": false
  },
  "issue_summary": "optional concise customer-provided details"
}
```

`request_number` includes the current request and must be 1, 2, or 3. `state` represents successful actions from prior requests for this same issue. The helper emits JSON with `status` (`plan`, `not_applicable`, or `blocked`), `tool_calls`, `customer_message`, `transfer_summary` where relevant, and `next_state`.

Example invocation by the Skill runtime:

```text
run_skill_script(relative_path="scripts/plan_incident_transfer.py", input_json={...})
```

Validation requirements before execution:

- Confirm the plan status is `plan`.
- Execute exactly the emitted tool calls in array order.
- For a third request, confirm the state proves both initial calls completed before calling regular transfer.
- Ensure the regular-transfer reason is `technical_system_error` and summary describes only the payment-posting incident and prior required steps; do not include unnecessary personal data.
- Send the returned customer message after initiating the corresponding action.

The helper rejects malformed input, inactive times, unmatched symptoms, missing human request, invalid request numbers, and out-of-order state. Its output is a recommendation for the execution agent; only the execution agent's normal tools can perform the transfer.
