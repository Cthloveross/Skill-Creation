---
name: credit-card-decline-human-transfer
version: 1.0.0
description: Handle a customer with purchase declines despite available credit who requests a human agent, including the required staged transfer protocol and fourth-request reason-code selection.
---

# Credit-card decline human-transfer protocol

Use this Skill when a customer reports credit-card purchase declines while they still have available credit and asks to speak with a human agent.

## Required inputs and assumptions

Track `human_request_count` across the current interaction. Count only clear requests to speak with, be transferred to, or be connected to a human/agent. A request made after the customer has been asked for identifying information still counts; do not require identity verification merely to follow this transfer protocol.

Use `scripts/transfer_plan.py` to produce a deterministic tool plan. Its JSON input is:

```json
{
  "purchase_declines_despite_available_credit": true,
  "human_request_count": 1,
  "frustrated": false,
  "specific_reason": null,
  "summary": "Customer reports purchase declines despite available credit and requests a human agent."
}
```

The script emits JSON with either a discoverable-tool plan for requests 1–3, a standard-transfer plan for request 4, or `unsupported` when this special protocol does not apply.

## Execution procedure

1. Confirm the special protocol applies: purchase declines are reported despite available credit, and the customer has requested a human.
2. Increment the transfer-request count before selecting a tool.
3. For request counts **1, 2, and 3**, do all of the following:
   - Call `unlock_discoverable_agent_tool` with `agent_tool_name` set to `initial_transfer_to_human_agent_0218`.
   - Call `call_discoverable_agent_tool` with `agent_tool_name` set to `initial_transfer_to_human_agent_0218` and `arguments` set to `{}`.
   - Do **not** call `transfer_to_human_agents` on these requests.
4. On request count **4**, call `transfer_to_human_agents`. Select the highest-priority applicable reason code. For a customer who is frustrated and demands a human without a higher-priority operational reason, use `customer_frustrated_demands_human`. For a calm request with no specific reason, use `customer_requests_human_no_specific_reason`. Supply a concise factual summary of the declined-purchase issue and any troubleshooting/verification attempted.
5. Tell the customer that the transfer is being handled only after the required tool call succeeds. Continue to address new issue details if the transfer has not completed, while preserving the request count.

## Handling failures and boundaries

- If the special discoverable tool cannot be unlocked or called, report the failure accurately and do not substitute the standard transfer tool during requests 1–3.
- Do not invent account data, account status, verification, or diagnostics.
- If the customer has not supplied enough information to investigate, request the needed information only if they have not requested transfer; a clear transfer request takes the staged transfer path above.
- This Skill recommends and sequences tool calls; the executor must perform the actual banking tool calls.

## Validation

For a qualifying request, validate that the request count is a positive integer. Validate that counts 1–3 produce only the initial discoverable transfer path, and count 4 produces the standard transfer path with a permitted reason code. The helper performs these checks and emits an error object instead of a tool plan for invalid input.

Example runnable invocation:

```bash
printf '%s' '{"purchase_declines_despite_available_credit":true,"human_request_count":1,"frustrated":false,"specific_reason":null,"summary":"Customer reports purchase declines despite available credit and requests a human agent."}' | python3 scripts/transfer_plan.py
```
