---
name: incident-credit-card-payment-posting-transfer
description: Handle the time-limited credit-card payment-posting incident when a customer reports paying a card statement, a deduction from checking, and an unchanged card statement balance, and requests a human specialist.
---

# Credit-card payment-posting incident transfer

Use this Skill only through **2025-11-15 11:59:00 EST**, when all three reported symptoms are present:

1. The customer paid their credit-card statement.
2. The payment amount was deducted from their checking account.
3. The payment is not reflected in the credit-card statement balance.

A human-transfer request must also be present. Customer statements are sufficient to establish the three symptoms. Do not verify identity, request identifying information, retrieve account information, troubleshoot the payment, or collect additional issue details under this incident protocol.

## Required runtime inputs

Maintain transfer state for this same issue across turns. Obtain the current time using the available current-time tool if it is not already available, then run:

```text
python scripts/incident_transfer_plan.py <<'JSON'
{"current_time":"2025-11-14 12:00:00 EST","symptoms":{"statement_paid":true,"checking_debited":true,"card_balance_unupdated":true},"human_transfer_requested":true,"transfer_request_number":1,"called_agent_tools":[],"issue_summary":"Customer reports a paid card statement was deducted from checking but remains unpaid on the card statement."}
JSON
```

The example illustrates the schema only. At execution, populate values from the live conversation, current-time result, and retained same-issue state; do not reuse its timestamp or summary.

### Script input schema

- `current_time` (string, required): `YYYY-MM-DD HH:MM:SS EST`.
- `symptoms` (object, required): boolean `statement_paid`, `checking_debited`, and `card_balance_unupdated`.
- `human_transfer_requested` (boolean, required): whether the customer currently requested a human specialist.
- `transfer_request_number` (integer, required): the ordinal human-transfer request for this same issue, beginning at 1.
- `called_agent_tools` (array of strings, required): agent-discoverable tools successfully called earlier for this same issue.
- `issue_summary` (string, required for a third-or-later request): concise customer-provided issue summary for the regular human-transfer tool.

The script emits a JSON plan. `status: "ready"` permits the listed actions to be performed in their listed order. Any other status means do not perform an incident transfer from that plan; resolve only the stated prerequisite or use applicable handling outside this Skill.

## Execute a ready plan exactly

The `actions` array is an ordered instruction list. Carry out every action in order using the execution agent's normal tools. Script output is a recommendation only and never executes a banking or transfer action itself.

- **Request 1:**
  1. Call `unlock_discoverable_agent_tool` with `agent_tool_name` `initial_transfer_to_human_agent_1822`.
  2. Call `call_discoverable_agent_tool` with that same name and `arguments` set to the JSON string `{}`.
  3. Tell the customer: “I understand you'd like to speak with a human specialist about this issue. Let me initiate that process for you now.”

- **Request 2 for the same issue:** only after the first specialized tool was successfully called:
  1. Unlock `initial_transfer_to_human_agent_0218`.
  2. Call it with `arguments` set to `{}`.
  3. Tell the customer: “I hear your concern about the urgency. I'm continuing to process your transfer request.”

- **Request 3 for the same issue:** only after both specialized tools were successfully called:
  1. Call `transfer_to_human_agents` with the plan's `regular_transfer` arguments. The plan uses `technical_system_error` because this is a documented backend payment-posting incident.
  2. Tell the customer: “I'm now connecting you with a human specialist who can resolve this for you.”

Do not call the regular `transfer_to_human_agents` tool on the first or second request. Do not skip, reorder, or call an agent-discoverable tool before unlocking it. Record each successful specialized call in `called_agent_tools` before planning a later request.

## Preconditions and boundaries

- The incident ends at the stated EST deadline; the deadline itself is not included. Outside the window, if a symptom is absent, or if the customer did not request a human, this Skill does not prescribe a transfer—use the applicable standard process.
- If a second or third request lacks the required prior successful specialized calls, do not bypass the missing prerequisite or use the regular transfer tool. The plan returns `prerequisite_missing` and identifies what is missing.
- The only permitted symptom questions under this Skill are those needed to establish the three listed symptoms. Never perform identity verification or call identity, account-lookup, transaction-lookup, or verification-log tools for this protocol.
- Do not make interest, payment-posting, balance, or fee determinations in chat.

## Validation

Before executing, verify that the plan has `status` `ready`, `eligible` true, and the exact expected action order. For request 1, there must be exactly an unlock and call for tool `1822`; for request 2, the same pair for `0218`; for request 3, exactly one regular-transfer action and both specialized tool names must be in `called_agent_tools`. Treat malformed input, an unparseable/non-EST time, and unsupported request ordinals as non-ready results.
