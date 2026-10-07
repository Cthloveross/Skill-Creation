---
name: erroneous-credit-bureau-reporting-incident
version: 1.0.0
description: Handle the time-limited Rho-Bank emergency incident in which a backend error falsely reported credit-card delinquencies for accounts in good standing. Use when a customer reports an unexpected bureau delinquency or abrupt score drop despite current payments during the active incident window.
---

# Erroneous Credit Bureau Reporting Incident

## Applicability

Use this emergency workflow only when all of the following are true:

1. The current time is from **2025-11-14** through **2025-11-18, 11:59 PM EST**, inclusive.
2. The customer reports a Rho-Bank credit-card delinquency that they say is false, or a related sudden credit-score decline.
3. Their report is consistent with an account being in good standing (for example, payments are current or autopay is active).

Do not assume the incident applies outside that window or when the report does not concern a Rho-Bank credit-card delinquency. Follow the applicable normal support workflow in those cases.

## Mandatory emergency workflow

For an applicable report, treat it as urgent. **Do not request, retrieve, or verify identity**, do not call `log_verification`, and do not investigate account details before escalation.

Perform these actions in this order:

1. Unlock the specialized tool by calling `unlock_discoverable_agent_tool` with:
   ```json
   {"agent_tool_name":"emergency_credit_bureau_incident_transfer_1114"}
   ```
2. Immediately call it through `call_discoverable_agent_tool` with:
   ```json
   {
     "agent_tool_name":"emergency_credit_bureau_incident_transfer_1114",
     "arguments":"{}"
   }
   ```
3. Then call `transfer_to_human_agents`. Use `technical_system_error` as the reason. In the summary, state that the customer reported a potentially erroneous Rho-Bank credit-card delinquency/score drop during the emergency credit-bureau-reporting incident and that the emergency incident escalation was initiated. Include only details the customer volunteered; do not add or seek personal data.

The emergency specialized-tool call must precede the human transfer. Do not retry an emergency action if its result is unknown; report the status and proceed only as permitted by the available tool result.

## Customer communication

Acknowledge the seriousness and urgency with empathy. Explain only that Rho-Bank is addressing a credit-bureau reporting issue affecting some credit-card customers and that the case is being escalated immediately to the team that can assist. Avoid guarantees about score restoration, bureau correction timing, mortgage outcomes, or account-specific findings. Do not imply that the customer caused the issue.

A suitable response is concise, empathetic, and urgent, for example: acknowledge how concerning the report is—particularly given a pending mortgage application—and confirm that an immediate escalation has been started. Do not expose internal tool names, incident identifiers, or unverified account information.

## Validation checklist

Before completing the interaction, confirm:

- The report matched the incident and fell within the active EST time window.
- No identity-verification or account-lookup action was taken for this workflow.
- `emergency_credit_bureau_incident_transfer_1114` was unlocked and called successfully before the human transfer.
- The human transfer used `technical_system_error` and an accurate, privacy-minimized summary.
- The customer received an empathetic acknowledgement without unsupported promises.
