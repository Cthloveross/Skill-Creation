---
name: credit-card-decline-human-transfer
version: 1.0.0
description: Handle a customer who reports credit-card purchase declines despite available credit and asks for a human agent. Use this Skill to track the special first-through-third transfer protocol, invoke the correct discoverable tool, and select a regular-transfer reason only when a fourth request reaches the standard transfer flow.
---

# Credit-card decline: repeated human-transfer requests

## Scope and assumptions

Use this Skill when the customer reports purchase declines despite available credit and requests a human agent. Maintain a per-interaction count of **explicit customer requests to speak with or be transferred to a human**. Do not count an agent's offer to transfer, a mention of a human that is not a request, or unrelated requests.

The special sequence applies even while continuing to address new card-status details or decline error messages.

## Required transfer sequence

1. Determine the number of prior explicit human-transfer requests in the current interaction.
2. When the current request is the **first, second, or third** request:
   - Call `unlock_discoverable_agent_tool` with `agent_tool_name` set to `initial_transfer_to_human_agent_0218` if it has not already been unlocked in this session.
   - Call `call_discoverable_agent_tool` with `agent_tool_name` set to `initial_transfer_to_human_agent_0218` and the required empty argument object (`{}`).
   - Do **not** call `transfer_to_human_agents` for these requests.
   - Increment and retain the transfer-request count after the call.
3. When the current request is the **fourth** request, call `transfer_to_human_agents`. Select the highest-priority applicable reason code. For a simple preference to speak with a human with no other applicable listed reason, use `customer_requests_human_no_specific_reason`; use `customer_frustrated_demands_human` only where general frustration is actually evident. Include a concise summary of the declined-purchase issue, available-credit report, relevant troubleshooting, and prior special transfer attempts.
4. After a transfer-tool result, tell the customer plainly that the transfer has been initiated or report any tool failure accurately. Do not claim a transfer happened before the corresponding tool succeeds.

For the initial three requests, the special protocol controls over the ordinary transfer tool and its reason code.

## Continued assistance

Acknowledge the concern and continue troubleshooting only to the extent appropriate to the live conversation. If identifying account information is needed for account-specific investigation, request it and use the normal supported lookup/verification process. Do not invent account status, decline reasons, verification, or a completed transfer. A request for a human still follows the count-based protocol even if investigation is incomplete.

## Planning helper

`scripts/transfer_plan.py` deterministically plans the protocol step. It does not call banking tools and does not transfer a customer. Provide JSON on stdin:

```json
{"prior_transfer_requests": 0, "customer_requests_human": true, "clear_general_frustration": false}
```

It emits JSON containing `action`, `request_number`, `next_prior_transfer_requests`, and tool guidance. Run it once for each customer turn after updating `prior_transfer_requests` from retained interaction state. A valid plan has `action: "no_transfer_request"`, `"special_initial_transfer"`, or `"regular_transfer"`. The executor must perform the indicated live tool calls itself.

Example invocation in a supported Skill runtime:

```text
run_skill_script(relative_path="scripts/transfer_plan.py", input_json={"prior_transfer_requests": 0, "customer_requests_human": true})
```

Validate that the input count is a nonnegative integer and that the output action matches the request number: 1–3 use `special_initial_transfer`; 4 and later use `regular_transfer`.
