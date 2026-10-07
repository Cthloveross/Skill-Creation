---
name: rho-bank-erroneous-credit-bureau-reporting-incident
version: 1.0.0
description: Handle the time-limited Rho-Bank credit-card incident in which a backend error reported delinquency to credit bureaus for accounts that may be current. Use when a customer reports an unexpected delinquency report or sudden credit-score decline and the active incident window may apply.
---

# Erroneous Credit Bureau Reporting Incident

## Scope and prerequisites

Apply this Skill only when all of the following are true:

1. The current time is from **2025-11-14 00:00 EST** through **2025-11-18 23:59:59 EST** (inclusive).
2. The customer reports a credit-card delinquency they say is erroneous, an unexpected credit-bureau report, or a sudden credit-score drop; the report is consistent with an account in good standing/current payments.

Obtain the current time with `get_current_time` if it is not already available in the interaction. Use `scripts/assess_incident.py` to record a deterministic eligibility assessment when desired. The script is an aid only; the executor remains responsible for recognizing the customer's report and performing the required escalation.

Do **not** request, collect, look up, or log identity-verification information for this incident. Do not investigate transactions or account details before the emergency escalation.

## Required procedure

For an applicable report, act immediately, in this order:

1. Tell the customer, using empathetic and urgent language, that their report is serious and is being urgently escalated. Acknowledge the potential impact without promising a particular credit outcome or correction timeline.
2. Unlock the incident tool by calling `unlock_discoverable_agent_tool` with `agent_tool_name` set to `emergency_credit_bureau_incident_transfer_1114`.
3. Call `call_discoverable_agent_tool` with `agent_tool_name` set to `emergency_credit_bureau_incident_transfer_1114` and `arguments` set to `{}`.
4. Immediately call `transfer_to_human_agents`. Use reason `technical_system_error`, because this is a backend reporting error. Its summary should state that the customer reports an erroneous credit-card delinquency/score decrease during the active credit-bureau-reporting incident and that the emergency incident transfer was invoked. Include only the issue details volunteered by the customer; do not add personal data or request verification.

The emergency tool and the human transfer are both required. Do not substitute a normal account review, generic dispute workflow, or customer self-service instruction.

If unlocking or calling the emergency tool returns an error, do not retry with invented arguments or a different incident tool. Transfer to a human agent immediately with reason `technical_system_error`, summarize the reported active incident and the failed emergency-escalation step, and state in the customer-facing message that urgent escalation is being arranged. If the human-transfer tool itself fails, clearly report the inability to complete the transfer in the response and preserve the exact tool failure for follow-up; do not claim that a transfer occurred.

## Customer-facing communication

Use concise wording such as: acknowledge that an unexpected delinquency report and resulting score drop are serious, recognize the urgency (for example, an imminent mortgage application if volunteered), and say that it is being urgently escalated to the appropriate team. Never state that the customer's report has been verified, that a credit bureau has corrected the record, or that a particular score change will be reversed.

## Non-applicable or ambiguous cases

If the date window is not active, or the report does not concern this specific pattern, do not use the emergency incident tool based on this Skill. Follow the applicable normal policy instead. If the date or report facts are unavailable, obtain only the current time needed to assess the incident; do not seek identity verification merely to decide applicability.

## Helper script

`scripts/assess_incident.py` reads one JSON object from stdin and emits one JSON object to stdout.

Input schema:

```json
{
  "current_time": "YYYY-MM-DD HH:MM:SS EST",
  "customer_report": "customer's message"
}
```

Output fields:

- `window_active`: whether `current_time` is inside the inclusive EST incident window;
- `report_matches`: whether the text contains indicators of unexpected credit-card delinquency/credit-bureau reporting plus a score decline or current/good-standing payment assertion;
- `applicable`: `window_active && report_matches`;
- `missing_fields`: required missing or invalid inputs;
- `reason`: concise machine-readable assessment explanation.

Example runtime invocation (with actual interaction values):

```text
run_skill_script(relative_path="scripts/assess_incident.py", input_json={"current_time":"<time from get_current_time>","customer_report":"<customer message>"})
```

Validate that `applicable` is true before using this Skill's emergency workflow. The script rejects malformed timestamps rather than assuming the window is active. A false assessment does not authorize the emergency tool.
