---
name: human-agent-transfer-triage
version: 1.0.0
description: Selects the highest-priority supported reason code and prepares a concise transfer summary when a banking customer requests transfer to a human agent.
---

# Human-agent transfer triage

Use this Skill when a conversation must be transferred through `transfer_to_human_agents`. Its purpose is to choose the most specific applicable reason at the highest documented priority tier and to preserve the relevant case history in the transfer summary.

## Inputs and assumptions

Read the live conversation, public task inputs, tool observations, and the supplied transfer-reason knowledge. Do not treat a customer's request for a human as proof of any operational issue that was not actually observed.

Before transferring:

1. Confirm that the customer has requested or requires transfer.
2. Identify facts that are explicitly stated by the customer or established by tool results.
3. Check Tier 1 reasons first, then Tier 2, then Tier 3, and use `other` only if none apply.
4. If the request involves an unavailable offer or a claimed external communication, apply the extra prerequisites exactly; do not infer them merely from an unsuccessful account lookup.
5. Do not perform account changes, disclose sensitive data, or repeat a failed/unknown action solely to prepare a transfer.

Use `scripts/select_reason.py` for a reproducible recommendation when the applicable facts can be represented by its JSON input. The script only recommends a reason; the executor must make the actual banking-tool call.

## Reason selection procedure

Evaluate the documented conditions in priority order:

### Tier 1: specific functional or operational issue

Choose the applicable Tier 1 code for fraud/security, explicit closure, deceased holder/estate, legal/regulatory issue, ownership dispute or specialist identity-verification failure, complex billing dispute, abusive behavior, third-party inquiry, a technical system error/outage preventing completion, or a customer who persists and demands a human after being told a requested unavailable offer does not exist.

The unavailable-offer escalation requires all of these: the request is about an offer/promotion absent from the system, the customer was informed it is unavailable, the customer persisted multiple times, and then demanded a human. An ordinary account/product search failure does not satisfy this rule.

### Tier 2: knowledge or capability gap

Use `unconfirmed_external_communication` only when the customer says they have a specific letter, email, or flyer for an offer/program and it cannot be verified after searching the knowledge base.

Use `kb_search_unsuccessful_customer_requests_transfer` only when the customer asked for information/instructions, the agent searched the knowledge base and could not find it, the customer was informed of that, and then requested transfer.

Use `specialized_department_required` for an out-of-scope specialist department request, and `accessibility_or_special_needs` when human intervention is needed for an accessibility/special-needs accommodation.

### Tier 3: customer disposition

If no higher tier applies, distinguish:

- `customer_frustrated_demands_human`: general frustration plus demand for a human.
- `supervisor_request_service_complaint`: request for a supervisor due to service quality.
- `customer_requests_human_no_specific_reason`: preference/request for a human without a more specific applicable cause and without general frustration.
- `request_completed_customer_wants_human_followup`: the original request was completed successfully and the customer wants human follow-up or confirmation.

### Tier 4

Use `other` only when no documented reason applies. Its summary must explain why no listed code fits.

If multiple conditions apply, always retain the reason from the highest numbered-priority tier. If more than one reason in the same tier plausibly applies, use the one that most specifically describes the immediate transfer need and record the supporting facts in the summary.

## Create the transfer summary

Write a factual, concise summary that includes:

- the customer’s requested outcome;
- relevant lookup/search or troubleshooting steps and their outcomes;
- any confirmed issue that supports the selected reason;
- the customer’s transfer request; and
- unresolved next step for the human agent.

Do not include unverified claims as facts. Do not expose unnecessary full identity attributes, account numbers, or other sensitive data. If a lookup is negative, state the category searched and the negative result without inventing a record identifier.

A suitable general structure is: `Customer requested [outcome]. [Relevant actions] showed [result]. Customer requested transfer. Human agent should [next step].`

## Execute the transfer

After choosing the reason and writing the summary, call:

`transfer_to_human_agents(reason=<recommended reason>, summary=<factual summary>)`

The transfer tool's `reason` must be one of its declared enum values. Use the exact documented spelling. Report the transfer result to the customer. If the tool fails, do not claim that transfer occurred; preserve the error for appropriate follow-up.

## Script interface

Run the packaged selector as follows through the Skill runtime:

`python scripts/select_reason.py <<'JSON'`
`{"facts":{"customer_requested_human":true,"general_frustration":false}}`
`JSON`

The program reads one JSON object from standard input and emits one JSON object to standard output:

- Input: `{"facts": {<boolean fact names>}}`. Omitted facts are `false`.
- Output: `{"reason": <reason enum or null>, "tier": <1-4 or null>, "matched": [<fact names>], "needs_manual_review": <boolean>}`.

A `null` reason means no transfer request was represented. `needs_manual_review` is true for contradictory or underspecified same-tier facts; inspect the conversation and select the more specific documented condition before calling the banking tool.

## Validation

Before using the result, verify that a reason is present, it is in the transfer tool enum, and its tier is not lower than any supported fact. Verify that every assertion in the summary is supported by the live transcript or observation. The script is a deterministic aid, not a substitute for this review.
