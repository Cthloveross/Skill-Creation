---
name: credit-card-decline-human-transfer-protocol
description: Handle a customer who reports credit-card purchase declines despite available credit and asks for a human agent. Tracks qualifying transfer requests and selects the required discoverable initial-transfer path for requests one through three, then the regular transfer path on request four.
---

# Credit-card decline and human-transfer protocol

Use this Skill when all of the following are true in the current interaction:

1. The customer reports credit-card purchase declines.
2. The customer says they have available credit (or that they have not reached their credit limit).
3. The customer asks to speak with, be connected to, or be transferred to a human agent.

A qualifying transfer request is the customer's request for a human in this specific decline-with-available-credit situation. Keep its count for the entire interaction. Do not reset it because new decline details, an error message, card-status information, or diagnostic results arrive.

## Required transfer sequence

For each newly received qualifying request:

| Qualifying request number | Required action |
|---|---|
| 1, 2, or 3 | Unlock `initial_transfer_to_human_agent_0218`, then call it through the discoverable-agent-tool interface. Do **not** call `transfer_to_human_agents`. |
| 4 or later | Call the normal `transfer_to_human_agents` tool. For a direct request without a more specific applicable escalation reason, use `customer_requests_human_no_specific_reason` and provide a concise factual summary. |

The discoverable initial-transfer tool has no documented arguments. Invoke it as follows:

1. Call `unlock_discoverable_agent_tool` with `agent_tool_name: "initial_transfer_to_human_agent_0218"`.
2. Call `call_discoverable_agent_tool` with `agent_tool_name: "initial_transfer_to_human_agent_0218"` and `arguments: "{}"`.

Do not substitute the standard transfer tool for any of the first three requests. Do not tell the customer a transfer has completed unless the corresponding tool reports success.

## State and decision helper

Use `scripts/transfer_protocol.py` once for each newly received customer request. Persist its `updated_state` in the interaction state before processing later turns. Supply a stable event identifier for the customer message; if a message is retried, include the persisted state so the helper identifies it as already processed and does not increment the count again.

### Input JSON schema

```json
{
  "state": {
    "qualifying_request_count": 0,
    "processed_request_ids": []
  },
  "event": {
    "id": "stable-id-for-this-customer-message",
    "customer_requested_transfer": true,
    "purchase_declines_reported": true,
    "available_credit_reported_or_confirmed": true,
    "diagnostic_status": "not_started"
  }
}
```

- `qualifying_request_count` must be a nonnegative integer.
- `processed_request_ids` must be an array of previous nonempty event IDs.
- `event.id` must be a nonempty stable string.
- `diagnostic_status` is optional and may be `not_started`, `in_progress`, or `discussed`.
- A request is qualifying only when all three boolean event conditions are true.

The helper emits JSON with `decision`, `request_number`, `recommended_tool_sequence`, an optional regular-transfer `reason` and `summary`, and `updated_state`. `decision: "duplicate_event"` means take no transfer action again. `decision: "not_qualifying"` means the special sequence does not apply and the counter is unchanged.

Runnable invocation using the actual event JSON held by the executor:

```sh
printf '%s\n' "$TRANSFER_PROTOCOL_INPUT_JSON" | python3 scripts/transfer_protocol.py
```

Validation is built into the helper: malformed input, invalid state, missing event IDs, and non-boolean eligibility fields cause a JSON error response and a nonzero exit status. Before acting, verify that a qualifying new request yields request numbers 1--3 only with the discoverable initial tool, and request number 4 with only the normal transfer tool.

## Customer assistance while following the sequence

Continue assisting rather than treating the transfer request as a diagnosis of the decline. Available credit alone does not rule out a decline. Explain, without claiming an unverified cause, that possible causes include fraud protection, merchant or terminal problems, an unactivated or expired card, international restrictions, and temporary technical issues.

If the customer is willing to troubleshoot, ask for the affected merchant(s), online versus in-person context, exact decline text, whether all purchases fail, and whether the card is new or replaced. Suggested safe checks are confirming card details, retrying a transaction, checking activation and expiration, and trying another terminal or merchant where appropriate. Do not state that an account review found a particular cause unless runtime evidence supports it. An absence of transaction-history records does not establish that no attempted declines occurred.

When the customer requests a human, do not make them complete troubleshooting before applying the required transfer step. Keep any transfer summary factual and minimal: the reported declines, reported available credit, relevant details volunteered by the customer, and assistance already provided. Avoid unnecessary personal or card data in the summary.

If any prerequisite for the special protocol is missing, clarify the issue or use the generally applicable process; do not infer available credit or a transfer request from ambiguous language. If the required discoverable tool cannot be unlocked or called, report the tool failure accurately and follow the execution environment's normal failure handling; never silently replace one of the first three required calls with the standard transfer tool.
