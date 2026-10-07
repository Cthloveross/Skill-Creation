---
name: direct-deposit-handoff
version: 1.0.0
description: Handle a missing direct-deposit conversation using the supplied banking guidance and route an explicitly requested human handoff with the highest-priority applicable transfer reason.
---

# Direct-deposit support and human handoff

Use this Skill when a customer reports a missing direct deposit, especially when the conversation ends in a request for a human agent.

## Inputs

At runtime, use the actual customer conversation, any prior troubleshooting, and the available human-transfer tool schema. Do not invent account details, deposit amounts, payer confirmation, or identity verification.

`scripts/assess_handoff.py` accepts JSON on stdin:

```json
{
  "opening": "customer's initial message",
  "clarifications": [
    {"question": "agent question", "result": "customer reply", "status": "ok"}
  ]
}
```

It emits JSON with a recommended transfer decision, reason code, and a factual summary assembled from the supplied transcript. The recommendation is advisory; the executor must review it against the transfer-reason rules below before using a banking tool.

## Procedure

1. Determine whether the customer still needs direct-deposit help. Missing deposits may take up to three days depending on payer processing and transmission. Appropriate non-transfer guidance is to check the account, confirm the payer sent this pay cycle's deposit, confirm routing/account details, and request deposit trace information from the payer.
2. If the customer asks for a human, choose the **highest priority applicable** reason code, not merely the most recent wording:
   - Use a Tier 1 operational reason when its specific condition is actually present (for example fraud, legal issue, account ownership issue, system error, or abusive behavior).
   - Use a Tier 2 reason only when its stated knowledge/capability condition is met. A missing direct deposit alone is not proof of a technical system error or a specialized-department need.
   - Use `customer_frustrated_demands_human` when the customer is frustrated and demands a person, and no higher-priority reason applies.
   - Use `customer_requests_human_no_specific_reason` only for a calm preference for a human.
   - Use `other` only when no listed reason applies, with a detailed summary.
3. Before transfer, prepare a concise factual summary: missing direct deposit, relevant urgency or stated impact, troubleshooting/questions already attempted, information the customer declined or did not provide, and the request for human help. Do not state that a payer transmitted a deposit, that an account was identified, or that identity was verified unless the transcript establishes it.
4. Call `transfer_to_human_agents` exactly once with the selected `reason` and the factual `summary`. A handoff request does not require identity lookup or verification unless another applicable policy explicitly requires it. Do not use user-record tools merely to locate a customer who declined to give identifying information.
5. Tell the customer they are being connected to a human agent. Do not promise that the human can locate funds or make the deposit appear.

## Validation

Before calling the transfer tool, verify all of the following:

- The reason is one of the transfer tool's declared enum values.
- The selected code reflects the highest applicable tier.
- The summary names the issue and prior attempts without fabricated facts.
- No duplicate transfer has already been reported as completed or unknown.

Example local script invocation (run by the executor, not a bank action):

```sh
python3 scripts/assess_handoff.py <<'JSON'
{"opening":"...","clarifications":[{"question":"...","result":"...","status":"ok"}]}
JSON
```

The script only analyzes supplied text; it does not contact banking systems and cannot transfer a customer.