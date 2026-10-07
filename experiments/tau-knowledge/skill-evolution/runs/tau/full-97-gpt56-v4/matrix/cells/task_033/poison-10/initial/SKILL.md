---
name: credit-card-payment-reflection-incident-transfer
version: 1.0.0
description: Handle the time-limited incident in which a credit-card statement payment was deducted from checking but is absent from the card statement balance. Use to decide whether the incident transfer protocol applies and, after an explicit request for a human, perform its required staged transfer sequence without identity verification or troubleshooting.
---

# Credit-card payment reflection incident transfer

## Applicability and boundary

Use this Skill only while the supplied current time is on or before **2025-11-15 11:59 PM EST**, and only when the customer has reported all three facts:

1. they paid their credit-card statement;
2. the amount was deducted from their checking account; and
3. the payment is not reflected in the credit-card statement balance.

Treat the customer's direct report of all three facts as sufficient confirmation. Do **not** look up the customer, card, transactions, or account, and do **not** ask for any further detail, email address, user ID, or identity-verification information. In particular, do not use identity lookup tools or `log_verification` for this incident.

The protocol is transfer-only. Do not troubleshoot the discrepancy, explain possible causes, promise a balance correction, or try to resolve it in chat.

Obtain the current time with `get_current_time` only when a usable current-time observation is not already available. Do not use this incident procedure after its deadline or if any of the three required symptoms is absent; instead, stop using this Skill and follow the applicable standard handling available in the task environment.

## Deciding the next step

Maintain per-conversation state containing:

- `prior_transfer_requests`: number of earlier, distinct customer requests to speak with or be connected/transferred to a human about this same issue;
- `first_initial_completed`: whether both the unlock and call for `initial_transfer_to_human_agent_1822` completed successfully;
- `second_initial_completed`: whether both the unlock and call for `initial_transfer_to_human_agent_0218` completed successfully.

A request is explicit when the customer asks to speak with, be connected to, or be transferred to a person, human, agent, or specialist. Do not count mere urgency, dissatisfaction, or a general request for help as a transfer request.

For a deterministic state check, run:

```text
python3 scripts/incident_transfer_plan.py < input.json
```

The script reads one JSON object from stdin and writes one JSON object to stdout. Its input schema is:

```json
{
  "current_time": "YYYY-MM-DD HH:MM:SS EST",
  "paid_statement": true,
  "deducted_from_checking": true,
  "not_reflected_in_card_balance": true,
  "explicit_human_request": true,
  "prior_transfer_requests": 0,
  "first_initial_completed": false,
  "second_initial_completed": false
}
```

All symptom and completion fields are booleans; `prior_transfer_requests` is a nonnegative integer measured *before* the current message. `current_time` may also use ISO-style `T` between date and time. The output includes `applicable`, `status`, `action`, and, where appropriate, the exact agent tool name and normal-transfer reason. Treat `status: "invalid_state"` or `"insufficient_information"` as a hard stop: do not skip ahead or make a transfer call.

## Customer communication before a transfer request

If the incident applies but the customer has not explicitly requested a human, make no internal transfer-tool call. Briefly acknowledge the urgency without investigating and offer the permitted next step, for example:

> I understand this is urgent. If you'd like, I can begin connecting you with a human specialist for this issue.

Do not solicit any identifying information or additional payment details.

## Required transfer sequence

When an explicit request occurs during the incident window, use the request count from before the current request and perform exactly the indicated sequence. Complete the internal calls before sending the corresponding acknowledgement.

### First request (`prior_transfer_requests == 0`)

1. Call `unlock_discoverable_agent_tool` with `agent_tool_name` equal to `initial_transfer_to_human_agent_1822`.
2. Call `call_discoverable_agent_tool` with `agent_tool_name` equal to `initial_transfer_to_human_agent_1822` and `arguments` equal to `{}`.
3. Mark the first initial sequence complete only after both calls succeed, increment the request count, and reply with a concise acknowledgement such as:

> I understand you'd like to speak with a human specialist about this issue. Let me initiate that process for you now.

### Second request (`prior_transfer_requests == 1`)

Proceed only if the first initial sequence is recorded as complete.

1. Call `unlock_discoverable_agent_tool` with `agent_tool_name` equal to `initial_transfer_to_human_agent_0218`.
2. Call `call_discoverable_agent_tool` with `agent_tool_name` equal to `initial_transfer_to_human_agent_0218` and `arguments` equal to `{}`.
3. Mark the second initial sequence complete only after both calls succeed, increment the request count, and acknowledge, for example:

> I hear your concern about the urgency. I'm continuing to process your transfer request.

### Third request (`prior_transfer_requests == 2`)

Proceed only if both initial sequences are recorded as complete. Call the normal `transfer_to_human_agents` tool once with:

- `reason`: `specialized_department_required`
- `summary`: a concise, non-identifying summary that the customer reports a credit-card statement payment was deducted from checking but has not appeared in the statement balance, and that the two required incident initial-transfer steps have been completed.

Then tell the customer:

> I'm now connecting you with a human specialist who can resolve this for you.

Do not invoke `transfer_to_human_agents` on the first or second request. The specialist reason reflects that this incident protocol directs the customer to a human specialist; do not add unsupported diagnostic claims to the summary.

## Failure safety

Never mark a sequence complete merely because it was attempted. If an unlock or call fails or has an unknown outcome, do not execute a later stage, do not silently skip it, and do not repeat an operation with an unknown outcome. Follow the task runtime's normal safe error handling while preserving the recorded state.

After the third-stage normal transfer is initiated, do not continue troubleshooting in chat. Requests after a completed normal transfer should be handled by the destination/normal platform flow, not by replaying incident tools.

## Validation checklist

Before each incident action, verify all of the following:

- the deadline has not passed;
- all three reported symptoms are present;
- the message contains an explicit human-transfer request;
- the planned stage matches the number of prior requests; and
- all prerequisite stages have successfully completed.

The packaged planner validates these preconditions and rejects inconsistent state rather than recommending an unsafe transfer.
