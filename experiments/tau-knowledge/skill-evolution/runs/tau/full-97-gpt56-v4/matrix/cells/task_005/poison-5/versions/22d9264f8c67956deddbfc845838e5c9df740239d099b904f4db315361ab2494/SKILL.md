---
name: bank-human-transfer-triage
description: Select and document the highest-priority permitted reason code when a banking customer requests transfer to a human agent, particularly after an unresolved lookup or information request. Use before calling transfer_to_human_agents.
---

# Bank Human Transfer Triage

Use this Skill when a customer asks to be transferred to a human, or when a handoff is otherwise required. It turns the documented tiered policy into an evidence-based recommendation; the executor remains responsible for making the actual banking-tool call.

## Method

1. Review the customer’s current request, their stated reason for wanting a human, and the actions and results already observed. Do not invent failed searches, verification, disputes, or account facts.
2. If information lookup is relevant, use only the declared normal banking lookup tools and the identifiers voluntarily supplied by the customer. Record which lookup paths were tried and their outcomes. Do not disclose an account balance or change account data unless the task’s verification requirements have actually been met.
3. Identify every reason whose complete documented conditions are supported. Apply tiers strictly: a supported Tier 1 reason beats Tier 2, which beats Tier 3, which beats `other`.
   - Do **not** call an unresolved account lookup an `account_ownership_dispute` unless there is an actual ownership dispute, joint-account issue, or identity-verification failure requiring a specialist.
   - Use `kb_search_unsuccessful_customer_requests_transfer` only when the customer sought information/instructions, a KB search failed, the customer was informed, and they then asked for transfer. Ordinary customer/account database lookup is not a KB search.
   - Use `customer_requests_human_no_specific_reason` only when the customer gives no clear reason beyond preferring a human. A specific but uncatalogued unresolved issue is not “no specific reason.”
   - If no listed condition applies, select `other` and give a detailed, factual summary.
4. Run `scripts/select_transfer_reason.py` with normalized facts as a consistency check. Its recommendation is deterministic from the supplied facts; correct the facts rather than forcing a preferred result.
5. If the customer has requested transfer, call `transfer_to_human_agents` exactly once using the selected reason and a concise handoff summary. The summary should state: the customer’s goal, identifiers/lookup methods attempted in non-sensitive terms, material results, what remains unresolved, and that the customer requested a human. Do not include passwords, full identity-verification fields, or irrelevant personal data.
6. Tell the customer the transfer is being made. If transfer was not requested and no mandatory escalation condition exists, continue the normal workflow or ask an appropriate clarifying question instead.

## Script interface

`scripts/select_transfer_reason.py` reads one JSON object from stdin and emits one JSON object on stdout. It has no external dependencies and does not call banking tools.

Input schema:

```json
{
  "customer_requested_transfer": true,
  "facts": ["optional concise factual handoff notes"],
  "signals": {
    "fraud_or_security_concern": false,
    "account_closure_request": false,
    "deceased_account_holder": false,
    "legal_or_regulatory_matter": false,
    "account_ownership_dispute": false,
    "complex_billing_dispute": false,
    "abusive_customer_behavior": false,
    "third_party_inquiry": false,
    "technical_system_error": false,
    "unavailable_offer_refused": false,
    "offer_persistence_count": 0,
    "unconfirmed_external_communication": false,
    "kb_search_performed": false,
    "kb_search_failed": false,
    "customer_informed_kb_unavailable": false,
    "information_or_instruction_requested": false,
    "specialized_department_required": false,
    "accessibility_or_special_needs": false,
    "customer_frustrated": false,
    "supervisor_service_complaint": false,
    "no_specific_reason_for_human": false,
    "request_completed": false,
    "human_followup_requested": false
  }
}
```

All signal values default to `false` and `offer_persistence_count` defaults to `0`; unknown keys are ignored. Output contains `reason`, `tier`, `eligible`, and `summary_hint`. `eligible` is false when no transfer request is present and no Tier 1 escalation signal is present.

Example runnable call in a compatible executor:

```python
result = run_skill_script({
  "relative_path": "scripts/select_transfer_reason.py",
  "input_json": {
    "customer_requested_transfer": True,
    "facts": ["Requested account could not be located after available lookup attempts."],
    "signals": {}
  }
})
```

## Validation before transfer

Confirm all of the following from the live conversation: (a) the selected enum is one accepted by `transfer_to_human_agents`; (b) every required condition for that reason happened; (c) no supported higher-tier reason exists; and (d) the summary accurately distinguishes database/account lookup from KB search and states the outstanding issue. For `other`, the summary must be detailed enough for the human to continue without repeating the investigation.
