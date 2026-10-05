---
name: credit-card-payment-posting-incident-transfer
description: Handle the time-limited credit-card payment-posting incident when a customer paid a statement, funds were deducted from checking, the card statement balance still does not show the payment, and the customer requests a human specialist. Applies the required staged internal-transfer sequence without identity verification or troubleshooting.
---

# Credit-card payment-posting incident transfer

## Applicability

Use this Skill only while the incident is active, through **2025-11-15 11:59 PM EST**, and only when the customer's report establishes all three conditions:

1. They paid their credit-card statement.
2. The payment amount was deducted from their checking account.
3. The payment is not reflected in, or the account still shows unpaid on, the credit-card statement balance.

The customer may express these facts in ordinary language. Do not ask follow-up questions merely to investigate, verify, or resolve the posting discrepancy. If the time is after the cutoff or a required symptom is absent, this incident procedure does not apply; use normal applicable handling instead.

**Do not perform identity verification for an applicable incident case.** Do not request identity fields, call user-information tools, or call `log_verification`.

Use the current timestamp supplied by the runtime or conversation. If none is available, obtain the current time before deciding eligibility. Do not treat a customer-supplied time as the authoritative incident-window time.

## Transfer-request counting and continuity

Keep state for this same payment-posting issue containing:

- the count of explicit customer requests for a human transfer;
- whether each internal stage completed successfully; and
- whether the regular transfer completed.

An affirmative answer to an agent's direct question about initiating a human transfer is an explicit transfer request. A later customer message again asking to transfer, demanding a human, or carrying a platform transfer-request marker is another explicit request for the same issue unless the customer clearly changes issues. Treat a platform marker such as `###TRANSFER###`, when exposed in the customer event, as an explicit transfer request.

**Continue processing the conversation after the first-stage acknowledgement.** If a later customer event is a second request, it must immediately trigger the second internal stage. Do not merely acknowledge it, wait for more information, restart the count, or use the regular transfer tool. The count is chronological across the incident conversation, not per assistant turn.

For an eligible case, act immediately on each transfer request. Do not troubleshoot, collect account details, or attempt to correct the payment balance.

## Required transfer sequence

Each named discoverable agent tool must be unlocked successfully before it is called. Record an internal stage as complete only after its corresponding call succeeds.

### First request

Perform these operations in exactly this order:

1. Call `unlock_discoverable_agent_tool` with `agent_tool_name: "initial_transfer_to_human_agent_1822"`.
2. After that unlock succeeds, call `call_discoverable_agent_tool` with `agent_tool_name: "initial_transfer_to_human_agent_1822"` and the default empty argument object.
3. Then tell the customer their requested human-specialist transfer is being initiated or processed.

For example: “I understand you'd like to speak with a human specialist about this issue. Let me initiate that process for you now.”

Do **not** call `transfer_to_human_agents` on the first request.

### Second request

When the next explicit request arrives for the same issue, and the first internal stage succeeded, perform these operations in exactly this order **after that second customer request**:

1. Call `unlock_discoverable_agent_tool` with `agent_tool_name: "initial_transfer_to_human_agent_0218"`.
2. After that unlock succeeds, call `call_discoverable_agent_tool` with `agent_tool_name: "initial_transfer_to_human_agent_0218"` and the default empty argument object.
3. Then acknowledge the continued request.

For example: “I hear your concern about the urgency. I'm continuing to process your transfer request.”

Do **not** use `transfer_to_human_agents` on the second request. Do not repeat the first internal tool for this request and do not defer the second tool until a third request.

### Third request

Only after both internal stages have successfully completed and the customer makes a third transfer request, call `transfer_to_human_agents`.

Supply a concise `summary` based only on the customer's disclosed issue, such as that they paid the card statement, the funds were deducted from checking, the payment is absent from the statement balance, and any stated urgency. The `reason` parameter may be omitted so the runtime default is used.

Then tell the customer they are being connected with a human specialist. Do not duplicate a successfully completed regular transfer for later repetitions.

## Failure and state safeguards

- Never skip, reorder, substitute, or pre-execute either designated internal tool.
- If an unlock or discoverable-tool call fails, do not mark that stage complete and do not advance to a later stage or regular transfer. Follow normal safe runtime failure handling while preserving the required order.
- If state conflicts with the request count, for example a second request exists but the first internal call never succeeded, do not skip to a later tool. Resolve the prior-stage failure through normal runtime controls first.
- A discoverable-tool execution is not the regular human transfer. Only `transfer_to_human_agents` completes the final transfer.
- Never use the regular transfer tool before the third request, even if the customer is urgent or repeats their request after stage one.

## Optional deterministic planner

`scripts/incident_transfer_plan.py` validates incident conditions, cutoff time, and saved sequence state and returns the next permitted operation. It has no side effects and never invokes banking or transfer tools.

Pass one JSON object on standard input, for example:

```json
{
  "current_time": "<runtime current timestamp>",
  "paid_statement": true,
  "deducted_from_checking": true,
  "missing_from_statement_balance": true,
  "transfer_request_number": 2,
  "completed_initial_steps": 1,
  "regular_transfer_completed": false
}
```

The script emits one JSON object on stdout with `status`, `incident_applicable`, and, when action is allowed, `next_operation`. Possible operations include:

- `unlock_and_call_first_internal_tool`
- `unlock_and_call_second_internal_tool`
- `regular_human_transfer`

Before acting on a planner result, confirm it agrees with the successful-call state in the conversation. For either internal operation, perform the exact unlock-then-call pair named above. The planner is a recommendation only; its output does not perform an action.