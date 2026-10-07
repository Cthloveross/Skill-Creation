---
name: credit-card-decline-human-transfer-protocol
description: Handle a customer with credit-card purchase declines despite available credit who requests a human agent. Use this Skill to track repeated transfer requests, invoke the required discoverable transfer path for requests one through three, and select a compliant standard-transfer reason on request four.
---

# Credit-card decline: repeated human-transfer protocol

## Applicability
Use this procedure only when all of the following are true:

1. The customer reports credit-card purchase declines;
2. They report available credit / not reaching their credit limit; and
3. They ask to speak with, be transferred to, or otherwise reach a human agent.

Count each distinct customer request for a human during the current interaction. Do not count the agent offering help, an identity-verification question, or a request merely to contact support as a transfer request unless the customer explicitly asks for the transfer.

Continue to acknowledge and, where appropriate, troubleshoot the decline. Possible non-account-specific checks include card details, a retry, activation, expiration, a different terminal/merchant, fraud alerts, international restrictions, and temporary technical issues. Do not claim an account-specific cause without account evidence.

## Required transfer sequence

Maintain `transfer_request_count_before` in conversation state. For every qualifying request, run `scripts/plan_transfer.py` with the current facts before taking transfer action.

### Requests 1–3
For counts 1, 2, and 3, **do not call** `transfer_to_human_agents`.

Instead, execute the returned steps in order:

1. Call `unlock_discoverable_agent_tool` with `agent_tool_name` set to `initial_transfer_to_human_agent_0218` (unless it is already unlocked in this interaction).
2. Call `call_discoverable_agent_tool` with:
   - `agent_tool_name`: `initial_transfer_to_human_agent_0218`
   - `arguments`: `{}` (as the required JSON string for the host tool).

The specialized tool is no-argument. Its call is the required transfer handling path for each of the first three requests. Record the incremented count even if additional assistance continues.

### Request 4 and later
Use `transfer_to_human_agents` rather than the discoverable initial-transfer tool. Supply the returned `reason` and a factual `summary` of the decline, available-credit report, relevant troubleshooting/verification status, and the repeated request. Do not put sensitive data in the summary unnecessarily.

The standard transfer reason must be selected from the highest applicable tier:

- Use an explicit Tier 1 or Tier 2 factual condition when it is present (for example, `fraud_or_security_concern` for an actual fraud/security concern, or `technical_system_error` for an actual system error).
- Otherwise use `customer_frustrated_demands_human` when the customer is frustrated and demands a human.
- Otherwise use `customer_requests_human_no_specific_reason` for a calm/preference-only transfer request.
- Use `other` only when no listed reason applies, and explain why in the summary.

Never label an ordinary decline as fraud or a technical error merely because those are possible explanations.

## Script interface

`scripts/plan_transfer.py` reads one JSON object from stdin and emits one JSON object to stdout. It is a planning/validation helper; the executor must perform the listed banking-tool actions.

Required input fields:

```json
{
  "transfer_request_count_before": 0,
  "current_turn_is_transfer_request": true,
  "qualifying_credit_card_decline": true
}
```

Optional fields:

- `discoverable_tool_already_unlocked` (boolean, default `false`)
- `frustrated_demands_human` (boolean, default `false`)
- `highest_applicable_reason` (one valid standard-transfer reason code when an explicit Tier 1/2 condition is established)
- `issue_summary` (string; a factual, privacy-minimized summary)

Output includes `applicable`, `request_number`, `next_count`, `action`, `actions`, and, for standard transfers, `reason` and `summary`. If it is not applicable or the current turn is not a transfer request, take no transfer action. Invalid counts, unsupported reason codes, or an attempt to assert a standard-only reason without request four produce an error output; resolve the input/state problem before acting.

Example execution by the Skill runtime:

```text
run_skill_script(relative_path="scripts/plan_transfer.py", input_json={...})
```

Validate that a qualifying first-through-third request produces `discoverable_initial_transfer`, with no `transfer_to_human_agents` action. Validate that request four produces `standard_transfer` and a permitted reason code. After a successful action, persist `next_count` in the interaction state.
