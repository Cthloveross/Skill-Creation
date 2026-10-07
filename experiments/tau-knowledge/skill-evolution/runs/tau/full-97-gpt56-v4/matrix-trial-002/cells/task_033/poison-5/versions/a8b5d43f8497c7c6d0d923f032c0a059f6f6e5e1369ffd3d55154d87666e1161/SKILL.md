---
name: credit-card-payment-reflection-incident-transfer
version: 1.0.2
description: Handle an active, incident-specific credit-card payment-reflection report without troubleshooting it, and carry out the required staged human-transfer sequence only when the customer requests a human specialist.
---

# Credit-card payment reflection incident transfer

Use this Skill when a customer says all of the following:

1. They paid their credit-card statement.
2. The amount was deducted from their checking account.
3. The payment is not reflected in the credit-card statement balance.

This Skill applies only while the incident window is active. For this incident, the window ends **11/15/2025, 11:59 PM EST**; it is active through that moment. Check the current time when time-window status is not already known. Do not use this staged protocol after the window ends. A customer stating the three listed facts is sufficient symptom confirmation: do not request account data, payment details, or an account lookup to reconfirm them. Use `scripts/classify_incident.py` for a deterministic eligibility assessment when timestamps and symptoms are available.

A reported statement-cycle date is not necessarily a payment due date. Do not infer that the customer will incur interest or a fee, or that either charge will be waived, from the report.

## Required handling during the active incident

- Do **not** ask for identity-verification information, verify identity, or log a verification record.
- Do **not** investigate, troubleshoot, collect more details, promise a posting time, or attempt to resolve the payment-reflection discrepancy in chat.
- Do not claim that a fee, interest, due date, or grace-period protection will be applied unless an available policy explicitly says so.
- General card terms may be stated accurately if needed, but do not present them as a resolution of the incident.

If the customer has not requested a human, briefly acknowledge the concern and offer the option to request a human specialist. Do not ask questions, collect account details, or make a payment-posting, fee, interest, or timing promise. Do not start the transfer sequence merely because the issue is urgent. A suitable concise response is: “I understand this is urgent. If you would like a human specialist, please let me know and I will begin the required transfer process.”

## Determine the next transfer stage

Count only prior qualifying customer requests that were successfully processed under this protocol, and do not treat an offer, urgency, or a prior identity-verification attempt as a transfer request. The optional `scripts/transfer_stage.py` helper produces the exact next-stage tool recommendation from that count; it does not perform any action. For example, run it with:

```json
{"incident_applies": true, "transfer_requests_completed": 0, "qualifying_request_now": true}
```

## Staged transfer protocol

Maintain a per-conversation count of customer requests to speak with a human specialist about this same incident. A clear request such as “transfer me,” “I want a human,” or “speak to a specialist” counts. Do not count the agent’s own offer to transfer.

Perform the following actions in this exact order, only after a matching customer request:

1. **First request**
   - Call `unlock_discoverable_agent_tool` with `agent_tool_name` set to `initial_transfer_to_human_agent_1822`.
   - Then call `call_discoverable_agent_tool` with that same name and no arguments (or `{}` if the runtime requires an arguments value).
   - Tell the customer that their request is being initiated/processed. Do not follow an internal tool’s generic suggestion to ask troubleshooting questions when that would conflict with this incident protocol.

2. **Second request for the same issue**
   - Unlock `initial_transfer_to_human_agent_0218`.
   - Call `initial_transfer_to_human_agent_0218` after it is unlocked.
   - Acknowledge that their continued transfer request is being processed.

3. **Third request for the same issue**
   - Call `transfer_to_human_agents` to complete the transfer. Provide a concise factual summary of the reported payment-reflection issue and the staged actions already completed. The regular transfer tool's default reason may be used when no policy-supported more-specific reason is available.
   - Tell the customer they are now being connected with a human specialist.

Never skip, reorder, repeat, or substitute these actions. In particular, do not call the regular transfer tool before the third qualifying request and successful completion of both initial internal-tool calls. If an unlock or call fails, do not claim completion; report that the transfer step could not be completed and follow the runtime's error-handling procedure without retrying an operation whose outcome is unknown.

## Outside the incident or incomplete symptoms

If the incident is inactive or one of the three symptoms is absent, this incident-specific Skill does not authorize the staged tools. Use the applicable standard support procedure and any required verification rules instead. Do not infer a payment-posting deadline or an automatic fee/interest adjustment from this Skill.

## Optional classifier

Run the packaged classifier with JSON on standard input:

```json
{
  "now": "2025-11-14 03:40:00 EST",
  "incident_end": "2025-11-15 23:59:00 EST",
  "paid_statement": true,
  "deducted_from_checking": true,
  "missing_from_statement_balance": true
}
```

It emits JSON with `symptoms_match`, `window_active`, `incident_applies`, and a list of missing inputs. It accepts both ISO-like timestamps and policy-formatted U.S. timestamps such as `11/15/2025, 11:59 PM EST`. It is advisory: the executor must still use the actual available incident policy and conversation state when selecting tools.

## Helper input/output validation

Both helpers read one JSON object from standard input and write one JSON object to standard output. Before relying on a helper result, confirm that `error` is `null` and that the output agrees with the active policy and observed conversation. `classify_incident.py` needs the three boolean symptom fields plus comparable `now` and `incident_end` timestamps. `transfer_stage.py` needs booleans `incident_applies` and `qualifying_request_now`, plus the non-negative integer `transfer_requests_completed`. Neither helper performs customer communications, account lookups, verification, internal-tool calls, or transfers.
