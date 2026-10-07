---
name: credit-card-decline-human-transfer
version: 1.0.0
description: Handle a customer's request for a human agent when they report credit-card purchase declines despite available credit, including the required staged transfer protocol and reason selection if standard transfer becomes appropriate.
---

# Credit-card decline transfer protocol

Use this Skill when a customer says their credit-card purchases are being declined despite available credit and asks to speak with a human. Track only explicit requests to be transferred to a human during the current interaction.

## Procedure

1. Confirm that both conditions apply: purchase declines despite available credit, and an explicit human-transfer request.
2. Increment the interaction's transfer-request count. Do not restart the count after asking clarifying questions or discussing new card details.
3. Obtain the special internal tool before using it:
   - Call `unlock_discoverable_agent_tool` with `agent_tool_name` set to `initial_transfer_to_human_agent_0218`.
   - For request counts 1, 2, and 3, call `call_discoverable_agent_tool` with that same tool name and arguments `{}`. Do **not** call `transfer_to_human_agents` for these requests.
4. On the fourth such request, use `transfer_to_human_agents` instead. Select the highest-priority applicable reason code. For a calm customer who simply prefers a human and has no more-specific applicable issue, use `customer_requests_human_no_specific_reason`; use `customer_frustrated_demands_human` if general frustration/demand is evident. Summarize the decline issue and prior assistance accurately.
5. Continue addressing relevant new information unless the transfer action completes the interaction. Never claim a transfer occurred unless the required tool call succeeded.

Do not request or expose identity data merely to perform the staged transfer. If the scenario does not match this Skill, follow the applicable normal support and transfer procedures.

## Decision helper

`scripts/transfer_decision.py` is a deterministic planning helper. It does not make banking actions. Provide JSON on stdin:

```json
{"declines_despite_available_credit": true, "explicit_transfer_requests_so_far": 0, "new_request_is_explicit": true, "customer_frustrated": false}
```

It emits JSON containing the updated count, required action, and (when relevant) a recommended standard-transfer reason. A count refers to requests before the current customer message; set `new_request_is_explicit` to `true` only for a new explicit request.

Example runtime invocation:

```sh
printf '%s' '{"declines_despite_available_credit":true,"explicit_transfer_requests_so_far":0,"new_request_is_explicit":true,"customer_frustrated":false}' | python3 scripts/transfer_decision.py
```

Validate that `updated_transfer_request_count` is 1 through 3 before using the special tool, and exactly 4 before using the standard transfer action. Treat negative/non-integer counts or a non-matching scenario as unsupported rather than guessing.
