---
name: incident-payment-reflection-transfer
version: 1.0.0
description: Apply the temporary credit-card payment-reflection incident protocol during its stated EST window when a customer says they paid their statement, the funds left checking, and the statement balance remains unpaid. Use it to gate the mandatory staged human-transfer sequence without identity verification or payment troubleshooting.
---

# Payment Reflection Incident Transfer Protocol

## Applicability

Use this Skill only through **2025-11-15 23:59:00 EST**, inclusive, when all three reported conditions are true:

1. The customer paid their credit-card statement.
2. The payment amount was deducted from their checking account.
3. The payment is not reflected in the credit-card statement balance.

Obtain the current timestamp from the runtime (`get_current_time`) rather than relying on a local clock. The supplied timestamp must explicitly be EST. Outside the window, or when the three conditions do not all apply, stop using this incident Skill and follow the applicable standard procedure.

During the window, do **not** verify identity, request identity information, look up accounts, investigate the payment, explain interest, or attempt to resolve the discrepancy in chat. If a condition is not known, ask only for the missing symptom confirmation. A transfer sequence starts only after the customer requests a human transfer for this issue.

## State to retain per issue

Maintain these facts across turns, only after successful tool calls:

- `prior_transfer_requests`: number of prior customer transfer requests successfully processed under this incident protocol.
- `completed_initial_calls`: ordered names of successfully called initial incident tools.
- `regular_transfer_completed`: whether the normal human transfer has already been completed.

Do not increment the request count merely because a customer asks; increment it after the corresponding required tool action succeeds. Do not infer completion from an unlock alone.

## Deterministic planning helper

Run `scripts/incident_transfer_plan.py` before acting. It reads one JSON object from stdin and writes one JSON object to stdout.

### Input schema

```json
{
  "current_time": "YYYY-MM-DD HH:MM:SS EST",
  "symptoms": {
    "paid_statement": true,
    "deducted_from_checking": true,
    "not_reflected_in_statement_balance": true
  },
  "user_requested_transfer": true,
  "prior_transfer_requests": 0,
  "completed_initial_calls": [],
  "regular_transfer_completed": false,
  "issue_summary": "optional concise non-sensitive summary"
}
```

Symptom values may be `true`, `false`, or `null`/omitted when not yet known. `issue_summary` is optional and must not contain identity-verification data. A runnable executor invocation is `run_skill_script` with `relative_path` set to `scripts/incident_transfer_plan.py` and an `input_json` object conforming to this schema.

### Output interpretation and validation

The helper returns a `status`, `internal_actions`, `assistant_message`, and `next_state`.

- Act only when `status` is `ready`.
- Execute `internal_actions` in the returned order and with the exact arguments shown.
- Before every discoverable-tool call, its matching unlock action must have succeeded in the same handling sequence.
- If an unlock or call fails, do not execute later actions, do not advance state, and do not bypass the required stage with a regular transfer. Handle the runtime error using its normal error process.
- Persist `next_state` only after every planned action succeeds.
- `needs_symptom_confirmation`, `not_applicable`, `invalid_state`, and `invalid_input` are non-actionable planning results. In particular, do not use an incident transfer to compensate for missing facts or invalid state.

The script validates the timestamp format, incident cutoff, all-symptom gate, request-stage state, exact initial-call ordering, and prevention of duplicate normal transfers.

## Required action sequence

For an eligible customer who explicitly requests a transfer:

1. **First request** (`prior_transfer_requests == 0`)
   - Unlock `initial_transfer_to_human_agent_1822` using `unlock_discoverable_agent_tool`.
   - Call `initial_transfer_to_human_agent_1822` using `call_discoverable_agent_tool`.
   - Use the returned acknowledgment message.

2. **Second request** (`prior_transfer_requests == 1`)
   - Unlock `initial_transfer_to_human_agent_0218` using `unlock_discoverable_agent_tool`.
   - Call `initial_transfer_to_human_agent_0218` using `call_discoverable_agent_tool`.
   - Use the returned continued-processing acknowledgment.

3. **Third request** (`prior_transfer_requests == 2`, with both initial calls recorded)
   - Call the normal `transfer_to_human_agents` tool using the returned arguments.
   - The helper selects `technical_system_error`, reflecting the documented backend incident, and produces a non-sensitive summary.
   - Use the returned connection acknowledgment.

Never call `transfer_to_human_agents` before both initial tools have been successfully called and the customer has made the third request. Never skip, reorder, or substitute the two incident tools. Once the normal transfer is complete, do not initiate it again for the same issue.

## Communication

Keep customer-facing communication limited to the helper's concise acknowledgement. Do not promise a payment posting time, interest outcome, adjustment, or account result. If the customer has reported all symptoms but has not requested a transfer, acknowledge the concern without troubleshooting and ask only whether they want a human specialist.
