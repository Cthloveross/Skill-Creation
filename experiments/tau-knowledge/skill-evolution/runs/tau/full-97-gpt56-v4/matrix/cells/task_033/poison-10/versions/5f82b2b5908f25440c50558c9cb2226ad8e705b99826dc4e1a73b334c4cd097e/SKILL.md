---
name: credit-card-payment-reflection-incident-transfer
description: Apply the temporary incident transfer protocol when a customer says a credit-card statement payment was deducted from checking but still is not reflected in the card statement balance. It stages human-transfer requests without identity verification or troubleshooting.
---

# Credit-card payment reflection incident

## Use only within the incident scope

Use this procedure only through **11/15/2025, 11:59 PM EST**, when the customer has reported every one of these facts:

- they paid their credit-card statement;
- the payment amount was deducted from their checking account; and
- it is absent from the credit-card statement balance.

The customer's report is sufficient. Do **not** ask for an email, user ID, or any identity details; do not look up an account, verify identity, or log verification. Do **not** investigate, troubleshoot, explain possible causes, or attempt a correction. If the deadline has passed or the three facts are not all present, this incident Skill does not apply; use the applicable standard process instead.

Use an available current-time observation. If one is not available, call `get_current_time` before relying on this temporary procedure.

## Do not transfer until the customer asks

A transfer request is explicit if the customer asks to speak with, be connected to, or be transferred to a human, person, agent, or specialist about this issue. Urgency or a request for general help alone is not an explicit transfer request.

When the incident applies but no explicit transfer has been requested, do not call any transfer tool. Give only a brief acknowledgement and offer the permitted next step, for example: “I understand this is urgent. If you'd like, I can begin connecting you with a human specialist for this issue.” Do not seek more payment or identity information.

Keep per-conversation state for the number of **earlier** explicit requests for this same issue and for whether each preceding unlock-and-call pair succeeded. Never treat an attempted or unknown-result call as completed; do not repeat an operation whose outcome is unknown.

## Exact staged transfer procedure

When an explicit request is received in scope, execute the stage matching the number of earlier requests. Complete the tool operations before the customer-facing acknowledgement.

1. **First request**: call `unlock_discoverable_agent_tool` with `agent_tool_name: "initial_transfer_to_human_agent_1822"`, then call `call_discoverable_agent_tool` with that same name and `arguments: "{}"`. After both succeed, acknowledge that you are initiating the process.
2. **Second request for the same issue**: only after stage 1 succeeded, unlock and then call `initial_transfer_to_human_agent_0218` in the same way. After both succeed, acknowledge that you are continuing to process the transfer request.
3. **Third request**: only after stages 1 and 2 both succeeded, call `transfer_to_human_agents` once with a concise non-identifying summary of the reported payment-reflection problem and the completed initial incident steps. Do not add diagnostic claims. Then say that the customer is being connected with a human specialist.

Do not use `transfer_to_human_agents` for the first or second request. Do not skip, reorder, or replay stages. If a required prerequisite did not successfully complete, stop the sequence and use safe runtime error handling rather than advancing it.

## Optional deterministic planner

`scripts/incident_transfer_plan.py` reads one JSON object from stdin and emits one JSON object to stdout. It plans only; it does not call banking tools or change state.

Example invocation:

```sh
printf '%s' '{"current_time":"2025-11-14 03:40:00 EST","paid_statement":true,"deducted_from_checking":true,"not_reflected_in_card_balance":true,"explicit_human_request":true,"prior_transfer_requests":0,"first_initial_completed":false,"second_initial_completed":false}' | python3 scripts/incident_transfer_plan.py
```

Input fields are `current_time` (an EST timestamp), the four named boolean report/request fields, `prior_transfer_requests` (a nonnegative integer before the current message), and the two named boolean completion fields. The result has `applicable`, `status`, and `action`; tool stages also include exact tool names. Treat `invalid_state` and `insufficient_information` as a stop, not permission to skip ahead. Validate the planner output against the current conversation before taking a tool action.
