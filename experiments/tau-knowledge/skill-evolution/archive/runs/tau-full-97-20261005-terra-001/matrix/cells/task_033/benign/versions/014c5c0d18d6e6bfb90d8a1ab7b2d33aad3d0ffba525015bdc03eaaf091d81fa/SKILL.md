---
name: incident-payment-reflection-transfer
version: 1.1.0
description: Handle the temporary credit-card payment-reflection backend incident through its stated EST cutoff. Use when a statement payment left checking but remains unpaid on the card statement, and execute the required staged human-transfer tools for each customer transfer request without identity verification or chat troubleshooting.
---

# Payment Reflection Incident Transfer Protocol

## Applicability gate

Use this Skill only through **2025-11-15 23:59:00 EST**, inclusive, when the customer reports all of these facts:

1. They paid their credit-card statement.
2. The money was deducted from their checking account.
3. The payment is not reflected in the credit-card statement balance.

Obtain the time from `get_current_time`; do not use a local clock. The incident cutoff is defined in EST, so require an explicit EST timestamp. Outside this window, or if any confirmed symptom is false, use the applicable standard procedure instead.

During an applicable incident:

- Do **not** request, collect, or perform identity verification.
- Do **not** look up accounts or payment records.
- Do **not** troubleshoot, investigate, explain interest, or try to resolve the payment-reflection discrepancy in chat.
- If one of the three symptoms is unknown, ask only for confirmation of the missing symptom.
- If all symptoms are known but no transfer has been requested, briefly acknowledge urgency and offer a human specialist. Do not take a transfer-tool action until the customer requests one.

## Persistent state and per-turn handling

Maintain this state for the same incident issue, updating it only after the corresponding tool action succeeds:

```json
{
  "prior_transfer_requests": 0,
  "completed_initial_calls": [],
  "regular_transfer_completed": false
}
```

`prior_transfer_requests` counts successfully processed incident transfer requests, not merely customer messages. `completed_initial_calls` must be exactly one of `[]`, `["initial_transfer_to_human_agent_1822"]`, or `["initial_transfer_to_human_agent_1822", "initial_transfer_to_human_agent_0218"]`.

On **every subsequent customer turn**, continue this same incident state rather than restarting the applicability conversation. Treat a direct request for a person, an affirmative answer to the immediately preceding offer of a human specialist, or an explicit transfer-continuation signal as a transfer request. In environments that send `###TRANSFER###` as a continuation signal, it is the next transfer request for this issue; do not ask the customer to restate the request.

After a successful first-stage action, the next such request is therefore the **second** request. Immediately plan and execute the second-stage action below. Do not wait for a new symptom check, repeat the offer, or perform any account/identity action.

## Planning helper

Before each decision, run `scripts/incident_transfer_plan.py`. It reads one JSON object from stdin and emits one JSON object on stdout.

Example executor call:

```json
{
  "relative_path": "scripts/incident_transfer_plan.py",
  "input_json": {
    "current_time": "YYYY-MM-DD HH:MM:SS EST",
    "symptoms": {
      "paid_statement": true,
      "deducted_from_checking": true,
      "not_reflected_in_statement_balance": true
    },
    "user_requested_transfer": true,
    "prior_transfer_requests": 1,
    "completed_initial_calls": ["initial_transfer_to_human_agent_1822"],
    "regular_transfer_completed": false
  }
}
```

Input fields:

- `current_time`: required `YYYY-MM-DD HH:MM:SS EST` string.
- `symptoms`: object whose three named values are `true`, `false`, or `null`/omitted.
- `user_requested_transfer`: required boolean after symptom facts are available.
- `prior_transfer_requests`, `completed_initial_calls`, and `regular_transfer_completed`: persisted state, with the defaults shown above for a new issue.
- `issue_summary`: optional non-sensitive summary for the third-stage regular transfer only.

The returned object has `status`, `internal_actions`, `assistant_message`, and, when applicable, `next_state`.

Validation and execution rules:

1. Act only when `status` is `ready`.
2. Execute `internal_actions` in exact listed order and exact arguments.
3. A discoverable tool must be successfully unlocked before its call. If an unlock or call fails, stop; do not advance or persist state and do not skip to another stage.
4. Persist `next_state` only after all returned actions succeed.
5. For non-`ready` statuses, do not perform a transfer tool call. Use only the returned message when it is appropriate to the customer.

## Required staged actions

For the first two stages, `unlock_discoverable_agent_tool` and `call_discoverable_agent_tool` are distinct tool calls and must appear in this order.

### First transfer request

With state `prior_transfer_requests == 0`:

1. Call `unlock_discoverable_agent_tool` with `{"agent_tool_name": "initial_transfer_to_human_agent_1822"}`.
2. After it succeeds, call `call_discoverable_agent_tool` with `{"agent_tool_name": "initial_transfer_to_human_agent_1822", "arguments": "{}"}`.
3. After it succeeds, retain the helper's first-stage `next_state` and send its acknowledgement.

### Second transfer request

With state `prior_transfer_requests == 1` and only the first initial call recorded:

1. Call `unlock_discoverable_agent_tool` with `{"agent_tool_name": "initial_transfer_to_human_agent_0218"}`.
2. After it succeeds, call `call_discoverable_agent_tool` with `{"agent_tool_name": "initial_transfer_to_human_agent_0218", "arguments": "{}"}`.
3. After it succeeds, retain the helper's second-stage `next_state` and acknowledge that processing is continuing.

This second sequence is mandatory on the next continuation/transfer request, including `###TRANSFER###` when that marker is supplied by the runtime.

### Third transfer request

Only with state `prior_transfer_requests == 2`, both initial calls successfully recorded in order, and a third request, call `transfer_to_human_agents` using the helper's returned arguments. Then persist its state and send its connection acknowledgement.

Never call `transfer_to_human_agents` before this third request. Never replace, skip, reorder, or duplicate either incident-stage tool. Do not perform a second regular transfer once `regular_transfer_completed` is true.

## Customer communication

Use the helper's concise acknowledgement after successful processing. Do not promise a posting time, reversal, interest outcome, adjustment, or resolution. Keep the response focused on processing the human-specialist request.
