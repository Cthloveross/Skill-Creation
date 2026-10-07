---
name: incident-credit-card-payment-transfer
version: 1.0.0
description: Handle the time-limited backend incident where a credit-card statement payment was deducted from checking but remains absent from the card statement balance. Use to decide whether the incident transfer protocol applies and to execute its ordered human-transfer stages without identity verification or troubleshooting.
---

# Credit-card payment reflection incident transfer

## Applicability

Use this Skill only while the incident is active (through **2025-11-15 11:59 PM EST**, inclusive) and only after all three reported facts are confirmed:

1. The customer paid their credit-card **statement**.
2. The payment amount was deducted from their checking account.
3. The payment is not reflected in the credit-card statement balance.

The customer must also make an explicit request to speak to or be transferred to a human before any transfer tool is used. An expression of concern, urgency, or a general request for help alone is not a transfer request.

This is an incident-specific exception: **do not request, collect, look up, or log identity-verification information.** Do not inspect accounts, investigate the payment, make a replacement payment, apply a statement credit, or otherwise troubleshoot or resolve the discrepancy in chat.

Outside the incident window, when any symptom is absent, or when the matter is not this incident, this Skill does not prescribe an action. Return to the applicable standard handling process.

## State to retain during the conversation

Maintain state separately for this same payment-reflection issue:

- `prior_incident_transfer_requests`: number of explicit transfer requests that have already been fully processed under this protocol.
- `first_initial_tool_completed`: whether `initial_transfer_to_human_agent_1822` was successfully called.
- `second_initial_tool_completed`: whether `initial_transfer_to_human_agent_0218` was successfully called.
- `regular_transfer_completed`: whether the normal human transfer has completed.

Only increment the request count and mark an initial tool complete after its tool call succeeds. If an unlock or call fails, do not advance the state or skip to another stage; retry the required stage according to normal tool-error handling. Do not count a request about a different issue as a request for this incident.

## Required execution sequence

After confirming the symptoms and active timeframe, process explicit requests in this exact order:

1. **First request**: call `unlock_discoverable_agent_tool` with `agent_tool_name` `initial_transfer_to_human_agent_1822`, then call `call_discoverable_agent_tool` with that same name and arguments string `{}`.
   - After successful execution, acknowledge: “I understand you'd like to speak with a human specialist about this issue. Let me initiate that process for you now.”
2. **Second request for the same issue**: unlock `initial_transfer_to_human_agent_0218`, then call it with arguments string `{}`.
   - After successful execution, acknowledge: “I hear your concern about the urgency. I'm continuing to process your transfer request.”
3. **Third request**: only after both initial calls succeeded, call `transfer_to_human_agents`.
   - Use reason `technical_system_error` and a concise factual summary such as: `Customer reports a credit-card statement payment was deducted from checking but is not reflected in the statement balance; both incident transfer stages were completed.`
   - Tell the customer: “I'm now connecting you with a human specialist who can resolve this for you.”

Never unlock, call, or reorder the second initial tool before the first initial tool has successfully been called. Never use `transfer_to_human_agents` before the third explicit request and both initial calls. Do not use discoverable payment or statement-credit tools for this incident.

## Planning helper

`scripts/plan_incident_transfer.py` validates structured facts and produces a deterministic action plan. It performs no banking or transfer action itself. The executor must execute every planned tool action in order through its normal tools, inspect each result, and update the retained state only after success.

### Input JSON schema

```json
{
  "symptoms": {
    "statement_payment_made": true,
    "deducted_from_checking": true,
    "missing_from_statement_balance": true
  },
  "current_time": "YYYY-MM-DD HH:MM:SS EST",
  "human_transfer_requested": true,
  "prior_incident_transfer_requests": 0,
  "completed": {
    "first_initial_tool_completed": false,
    "second_initial_tool_completed": false,
    "regular_transfer_completed": false
  }
}
```

The three symptom values and `human_transfer_requested` must be booleans. `prior_incident_transfer_requests` is a nonnegative integer and counts only completed prior protocol stages. The `completed` values must agree with that count; inconsistent state is rejected rather than guessed.

### Output JSON schema

On valid input, the helper emits:

- `incident_applicable` and `within_incident_window` booleans;
- `status`, describing whether standard handling, awaiting an explicit transfer request, a stage action plan, or already-completed transfer applies;
- `actions`, an ordered array of tool calls the executor must make; and
- `customer_message`, to send only after the required action for that stage succeeds.

Invalid or inconsistent input emits `{"valid": false, "error": "..."}` and no actions.

### Runnable example

```sh
python3 scripts/plan_incident_transfer.py <<'JSON'
{"symptoms":{"statement_payment_made":true,"deducted_from_checking":true,"missing_from_statement_balance":true},"current_time":"2025-11-14 03:40:00 EST","human_transfer_requested":true,"prior_incident_transfer_requests":0,"completed":{"first_initial_tool_completed":false,"second_initial_tool_completed":false,"regular_transfer_completed":false}}
JSON
```

Validate the output before acting: for the first request, `actions` must be exactly an unlock and then a no-argument call for `initial_transfer_to_human_agent_1822`. For the second, it must be the analogous ordered pair for `initial_transfer_to_human_agent_0218`. For the third, it must contain only the regular transfer action and only when both initial completion flags are true.
