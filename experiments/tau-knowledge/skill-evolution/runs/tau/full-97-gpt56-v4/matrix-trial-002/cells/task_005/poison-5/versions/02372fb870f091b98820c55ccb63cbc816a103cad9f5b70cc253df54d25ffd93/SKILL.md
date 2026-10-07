---
name: human-agent-transfer-routing
description: Select the highest-priority supported reason code and write a factual handoff summary when a banking customer must be transferred to a human agent. Use this whenever `transfer_to_human_agents` is available and a customer requests or needs escalation.
---

# Human-agent transfer routing

Use this Skill immediately before calling `transfer_to_human_agents`. It converts the conversation and completed tool work into a reason-code decision and a concise summary. It does not itself transfer the customer; the executor must make the normal banking-tool call.

## Inputs

At runtime, collect:

- the customer's current request and exact transfer request, if any;
- the relevant conversation history, including whether the customer is frustrated, abusive, or requesting a supervisor;
- actions already attempted and their observable outcomes;
- whether the request is complete, blocked, or outside the available tools/scope.

Do not infer facts from missing information, expose account data that has not been properly verified, or claim a lookup, KB search, verification, or system error that did not occur.

## Select the reason

Choose **one** code. Evaluate tiers in order and stop at the first tier containing an applicable code. Within a tier, choose the most specific applicable code.

### Tier 1 — specific operational situations

Use one of these whenever its stated condition is present:

- `fraud_or_security_concern`: fraud, identity theft, unauthorized activity, or a security concern needing a specialist.
- `account_closure_request`: explicit request to close an account.
- `deceased_account_holder`: death or estate matter.
- `legal_or_regulatory_matter`: subpoena, court order, garnishment, or compliance issue.
- `account_ownership_dispute`: ownership/joint-account dispute or identity-verification failure requiring specialist handling.
- `complex_billing_dispute`: specialist billing dispute, such as recurring charges, statement errors, or fee reversals.
- `abusive_customer_behavior`: abusive, threatening, or inappropriate conduct.
- `third_party_inquiry`: attorney, power of attorney, or other representative requiring verification.
- `technical_system_error`: an actual system error or outage blocks completion.
- `customer_demands_after_unavailable_offer_refusal`: an unavailable promotion/offer was explained, the customer persisted multiple times, then demanded a human.

### Tier 2 — knowledge or capability gap

Use only when the corresponding condition has actually happened:

- `unconfirmed_external_communication`: customer cites a specific letter, email, flyer, promotion, program, or offer that cannot be verified after searching available knowledge.
- `kb_search_unsuccessful_customer_requests_transfer`: the customer requested information/instructions, the agent searched the knowledge base without finding it, informed the customer, and the customer then requested transfer.
- `specialized_department_required`: mortgage, investments, business banking, or another specialized department is needed beyond available scope/tools.
- `accessibility_or_special_needs`: accessibility accommodation or special needs require human intervention.

A failed account lookup alone is not a KB-search failure. Do not use either knowledge-gap code unless its required search and customer circumstances occurred.

### Tier 3 — customer disposition

If no Tier 1 or Tier 2 reason applies:

- `customer_frustrated_demands_human`: general frustration plus a demand for a human.
- `supervisor_request_service_complaint`: request for a supervisor because of the agent's service quality or manner.
- `customer_requests_human_no_specific_reason`: customer simply requests a human, without frustration or a more specific applicable escalation reason.
- `request_completed_customer_wants_human_followup`: the requested work was completed successfully, but the customer wants a human for follow-up or confirmation.

### Tier 4

Use `other` only if no code above applies. The summary must then state why the listed codes do not fit.

## Handoff summary

Write a short, factual summary suitable for the receiving agent. Include:

1. the customer’s requested outcome;
2. material information the customer supplied, only as needed for the handoff;
3. completed attempts and results (for example, an account search that did not locate the requested product);
4. the current blocker and why transfer is occurring.

Avoid speculation, credentials, unnecessary sensitive personal data, unsupported allegations, and internal reasoning. Do not include account balances or other protected information unless it is necessary and permitted for the transfer context.

## Execute

Call the banking tool exactly once with the selected enum and summary:

```text
transfer_to_human_agents(
  reason=<selected_reason_code>,
  summary=<factual_handoff_summary>
)
```

If the tool reports failure, do not falsely state that the transfer succeeded. Follow the available runtime's error-handling procedure or explain the limitation to the customer.

## Validation checklist

Before the call, confirm all of the following:

- A Tier 1 or Tier 2 code was not skipped for a lower-tier preference-based code.
- Every condition required by the selected code is supported by the observed conversation or tool result.
- The reason is one of the tool's allowed enum values.
- The summary identifies the customer goal, attempts, outcome, and unresolved next step.
- No unavailable offer, KB search, system error, identity-verification failure, or customer emotion was invented.
