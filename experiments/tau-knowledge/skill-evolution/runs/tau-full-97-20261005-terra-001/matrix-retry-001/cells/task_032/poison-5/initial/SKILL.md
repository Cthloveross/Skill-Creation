---
name: credit-card-decline-human-transfer-protocol
description: Handle a customer who reports credit-card purchase declines despite available credit and asks to speak with a human. Tracks explicit transfer requests and uses the required discoverable initial-transfer route for requests one through three, then the regular human-transfer tool on request four.
---

# Credit-card decline and human-transfer protocol

## When this Skill applies

Use this Skill when both conditions are true:

1. The customer reports that credit-card purchases are being declined even though they have available credit or have not reached their credit limit.
2. The customer explicitly asks to speak with, be connected to, or be transferred to a human agent.

Count only explicit requests for a human transfer made during the current interaction. Maintain the count in the execution context; do not infer prior requests from customer frustration alone.

## Required routing sequence

For a qualifying explicit request, increment the prior request count by one and route as follows:

| Request number | Required action |
| --- | --- |
| 1, 2, or 3 | Unlock `initial_transfer_to_human_agent_0218` with `unlock_discoverable_agent_tool`, then invoke it through `call_discoverable_agent_tool`. Do **not** call `transfer_to_human_agents` for these requests. |
| 4 | Call the regular `transfer_to_human_agents` tool with a concise factual summary. |

The discoverable initial-transfer tool has no documented arguments. Invoke it with an empty JSON object (`{}`). The unlock must occur before the discoverable-tool call when it is not already unlocked in the active execution context.

The supplied protocol specifies routing through the fourth request only. If an interaction somehow continues after a completed fourth-request transfer, do not invent a fifth-request routing rule; follow the live transfer outcome or escalate according to separately available policy.

## Execution procedure

1. Identify whether the issue and request meet the applicability conditions above.
2. Determine `prior_transfer_requests`, the number of earlier explicit human-transfer requests in this same interaction. Do not reset it after providing troubleshooting.
3. Run `scripts/transfer_protocol.py` with the scenario flag, request flag, and prior count. It produces a deterministic routing plan and validates the count.
4. Execute the returned tool plan exactly:
   - For `specialized_initial_transfer`, unlock and then call the named discoverable tool.
   - For `regular_transfer`, call `transfer_to_human_agents`. Use the returned or independently selected applicable reason enum. For a straightforward request to speak to a person without a more specific supported escalation reason, `customer_requests_human_no_specific_reason` is suitable. Include only relevant, non-sensitive facts in `summary`: repeated purchase declines despite reported available credit, troubleshooting already attempted or requested, and the customer’s request for a human.
5. Tell the customer briefly that the transfer is being initiated. Do not delay the required transfer to demand account-identifying information or additional transaction details.

## Continued assistance

While a transfer is pending or when the customer does not request a human, acknowledge the problem and offer supported basic checks: confirm card details, retry a potentially temporary failure, confirm that a new/replacement card is activated, check expiry, try another terminal or merchant, and consider fraud protection, merchant, international-use, or temporary technical causes. Customer service can review account holds, restrictions, and fraud alerts.

If the customer provides new decline codes, merchant facts, or card-status information, address those facts when possible while retaining the transfer-request count and routing sequence. Do not claim to have reviewed account-specific information unless a permitted runtime tool was actually used.

## Helper input and output

`scripts/transfer_protocol.py` reads one JSON object from stdin and emits one JSON object to stdout.

Input fields:

- `scenario_matches` (boolean, required): whether the card-decline-despite-available-credit scenario applies.
- `customer_requested_human` (boolean, required): whether the current customer message explicitly requests a human/transfer.
- `prior_transfer_requests` (integer, required): number of earlier explicit human-transfer requests in the interaction; must be zero or greater.
- `issue_summary` (string, optional): factual context to place in a fourth-request transfer summary.
- `standard_reason` (string, optional): an applicable `transfer_to_human_agents.reason` enum selected from the live tool schema. If omitted for request four, the helper uses `customer_requests_human_no_specific_reason`.

Output fields include `ok`, `request_number`, `action`, `tool_plan`, and `customer_guidance`. `tool_plan` is a recommendation for the execution agent, not an automatic banking action.

A runtime invocation reads the request JSON from standard input, for example:

```sh
python3 scripts/transfer_protocol.py < runtime-input.json
```

## Validation

Before acting, verify that the helper reports `ok: true`, that a qualifying request has `request_number` equal to `prior_transfer_requests + 1`, and that the route is specialized only for request numbers 1–3 and regular only for request number 4. Reject a negative, non-integer, or boolean count rather than guessing. Also verify that the actual discoverable-tool call follows its unlock and has `{}` as its arguments.
