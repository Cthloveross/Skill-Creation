---
name: credit-card-decline-human-transfer-protocol
description: Handle a customer reporting credit-card purchase declines despite available credit who asks for a human. Use this for counting repeated transfer requests, invoking the required discoverable transfer protocol for requests one through three, and selecting a policy-compliant reason if a regular transfer is reached.
---

# Credit-card decline: repeated human-transfer requests

## Scope and prerequisites

Apply this procedure when the conversation establishes both of the following:

1. The customer reports credit-card purchase declines despite available credit; and
2. The customer requests to speak with, or be transferred to, a human agent.

Maintain a per-conversation count of **explicit customer transfer requests**. Count clear requests such as “transfer me,” “I need a human,” or “let me speak to an agent.” Do not count an assistant merely offering a transfer or asking a confirmation question unless the customer affirmatively requests the transfer in reply.

When continuing a supplied transcript, inspect all prior customer turns and identify the ordinal number of the current, unanswered transfer request. Do not replay tool calls for historical requests that were already handled; act on the active request according to its ordinal.

## Required action sequence

For transfer request numbers **1, 2, and 3**, do not use `transfer_to_human_agents`. Instead, perform these tool calls in order:

1. Call `unlock_discoverable_agent_tool` with `agent_tool_name` set to `initial_transfer_to_human_agent_0218`.
2. Call `call_discoverable_agent_tool` with `agent_tool_name` set to `initial_transfer_to_human_agent_0218` and `arguments` set to the JSON string `{}`.

The discoverable tool call is required for each applicable active request. Do not claim a transfer succeeded unless the tool result says so. Continue addressing the declined-purchase issue after the call when the conversation remains open, including requesting identity details if account-specific review is needed. Do not expose account information before appropriate identity verification.

For request number **4 or later**, call the normal `transfer_to_human_agents` tool. Select the highest-priority applicable reason code:

1. A specific functional or operational reason;
2. A knowledge/capability-gap reason;
3. A customer-disposition reason; or
4. `other` only when none applies, with a detailed summary.

For a frustrated customer demanding a human over the purchase-decline issue, when no higher-priority reason applies, use `customer_frustrated_demands_human`. Supply a concise factual summary of the decline issue, available-credit report, relevant troubleshooting or verification attempts, and the transfer request. Do not infer fraud, a system outage, or a medical/accessibility qualification solely from urgency.

## Execution workflow

1. Read the conversation state and confirm the scope conditions.
2. Count explicit customer transfer requests through the active customer message.
3. Optionally run `scripts/transfer_plan.py` with the counted request number and applicable facts as a consistency check.
4. Follow the returned action:
   - `unlock_and_call_initial_transfer` means use the discoverable-tool sequence above.
   - `regular_transfer` means call `transfer_to_human_agents` with the returned reason and a factual summary.
   - `normal_assistance` means no special transfer protocol applies; continue ordinary assistance.
5. Give a brief, empathetic response consistent with the actual tool result. Keep troubleshooting available without delaying the mandated protocol.

## Helper script

`scripts/transfer_plan.py` reads one JSON object from standard input and emits one JSON object to standard output.

Input schema:

```json
{
  "purchase_declines_despite_available_credit": true,
  "transfer_request_number": 3,
  "applicable_reason_codes": ["customer_frustrated_demands_human"]
}
```

- `transfer_request_number` is the one-based ordinal of the active explicit request and must be a nonnegative integer.
- `applicable_reason_codes` is optional and should contain only reason codes supported by observed facts. It is used only for a regular transfer.

Validation expectations:

- For an in-scope request numbered 1–3, output must name `initial_transfer_to_human_agent_0218` and must not recommend the regular transfer tool.
- For an in-scope request numbered 4+, output must recommend `transfer_to_human_agents` and choose the highest-tier supplied reason; if none are supplied, it uses `other` and flags that a detailed summary is required.
- For an out-of-scope event or request number 0, it must recommend normal assistance.

Example runnable invocation (the values are illustrative, not conversation data):

```sh
printf '%s' '{"purchase_declines_despite_available_credit":true,"transfer_request_number":1}' | python3 scripts/transfer_plan.py
```

The script only plans actions. It does not call banking tools; the executor must make the prescribed tool calls in the conversation runtime.
