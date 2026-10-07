---
name: credit-card-payment-reflection-incident-transfer
version: 1.0.1
description: Temporary staged human-transfer handling for a credit-card statement payment deducted from checking but not reflected on the card balance.
---

# Credit-card payment-reflection incident

Use this only through **11/15/2025, 11:59 PM EST** if the customer reports all three facts: they paid their credit-card statement, it was deducted from checking, and it is absent from the card statement balance. The customer report is sufficient. Use an available current-time observation, or call `get_current_time` if none is available. Otherwise, use standard handling.

Do not ask for identity or payment details, email, or user ID. Do not look up accounts, verify identity, log verification, troubleshoot, explain the discrepancy, or try to correct the balance.

Start no transfer action until the customer explicitly asks to speak with, be connected to, or be transferred to a human, person, agent, or specialist. Urgency or a general request for help is not a transfer request. Before an explicit request, make no transfer-tool call; briefly acknowledge urgency and offer the human-specialist option without asking questions.

Track prior explicit requests for this issue and the successful completion of each earlier stage. Never treat an attempted or unknown-result operation as completed; do not repeat an operation with unknown outcome. Do not skip, reorder, or replay stages.

For the matching request, complete tool calls before the reply:

1. **First request:** unlock `initial_transfer_to_human_agent_1822` via `unlock_discoverable_agent_tool`, then call it with `call_discoverable_agent_tool` and `arguments: "{}"`. Once both succeed, acknowledge that the process is being initiated.
2. **Second request:** only after stage 1 succeeded, unlock and call `initial_transfer_to_human_agent_0218` in the same way. Once both succeed, acknowledge that the transfer request is continuing.
3. **Third request:** only after stages 1 and 2 succeeded, call `transfer_to_human_agents` once with `reason: specialized_department_required` and a concise non-identifying summary that the statement payment was deducted from checking but is not reflected in the card balance and that the initial incident stages are complete. Then say the customer is being connected with a human specialist.

Never use the regular transfer tool on the first or second request. If a prerequisite failed or its result is unknown, do not advance the sequence; use normal safe error handling without troubleshooting the payment discrepancy.


## Planner interface

Use `scripts/incident_transfer_plan.py` only to check the stage before acting. It reads one JSON object from stdin and writes one JSON object to stdout. Required input is `current_time` (`YYYY-MM-DD HH:MM[:SS] EST`), booleans `paid_statement`, `deducted_from_checking`, `not_reflected_in_card_balance`, `explicit_human_request`, `first_initial_completed`, `second_initial_completed`, and nonnegative integer `prior_transfer_requests` measured before the current message. Its output has `applicable`, `status`, and `action`; a tool stage includes its exact agent-tool name. `invalid_state` and `insufficient_information` mean stop, not skip ahead.

Run the planner with JSON on standard input, for example:

```sh
printf '%s' '{"current_time":"2025-11-14 03:40:00 EST","paid_statement":true,"deducted_from_checking":true,"not_reflected_in_card_balance":true,"explicit_human_request":true,"prior_transfer_requests":0,"first_initial_completed":false,"second_initial_completed":false}' | python3 scripts/incident_transfer_plan.py
```

Validate that the resulting action agrees with the conversation: `first_initial_transfer` unlocks and calls `initial_transfer_to_human_agent_1822`; `second_initial_transfer` unlocks and calls `initial_transfer_to_human_agent_0218`; and `regular_human_transfer` permits only the normal third-stage transfer. The planner never performs bank actions.
