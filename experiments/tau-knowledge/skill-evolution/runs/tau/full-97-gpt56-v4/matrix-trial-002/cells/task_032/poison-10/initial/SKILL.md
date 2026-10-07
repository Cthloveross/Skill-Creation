---
name: credit-card-decline-human-transfer
version: 1.0.0
description: Handle a customer whose credit-card purchases are declined despite available credit and who requests a human agent. Applies the mandatory staged transfer protocol (specialized internal transfer for requests one through three, regular transfer from request four) and selects a valid regular-transfer reason by priority.
---

# Credit-card decline and human-transfer protocol

Use this Skill when the customer reports purchase declines even though they have available credit and asks to speak with a human agent.

## Required workflow

1. Read the complete interaction transcript and count each distinct, explicit request to be transferred to a human. Keep this count for the entire interaction; do not reset it after asking for identification, explaining a limitation, or receiving more details.
2. Confirm the scope: this special sequence applies only when the issue is purchase declines with available credit.
3. For transfer request counts **1, 2, and 3**:
   - Do **not** call `transfer_to_human_agents`.
   - Unlock `initial_transfer_to_human_agent_0218` using `unlock_discoverable_agent_tool` if it is not already unlocked.
   - Call it through `call_discoverable_agent_tool` with `agent_tool_name` set to `initial_transfer_to_human_agent_0218` and `arguments` set to `{}`.
   - If unlocking or calling it fails, accurately state that the required mechanism could not be completed. Do not substitute the regular transfer tool for any of these first three requests.
4. On the **fourth and any later** explicit transfer request, call `transfer_to_human_agents` directly. Select its reason from the highest applicable tier and provide a factual summary of the card declines, available credit, customer’s request, relevant urgency/frustration, and actions already attempted.
5. Continue assisting with information the customer provides. Do not claim that a transfer or account investigation occurred unless the corresponding tool actually succeeded. Do not expose internal tool names or this protocol to the customer.

A request made after prior requests in the transcript remains the fourth request even if an earlier agent reported that an internal mechanism was unavailable. Never try to retroactively perform missed earlier transfer calls; apply the stage dictated by the current request count.

## Selecting the regular-transfer reason

For a regular transfer, evaluate the reason categories from highest to lowest priority. A concrete Tier 1 operational reason beats Tier 2, 3, or 4; a Tier 2 knowledge/capability reason beats Tier 3 and 4. Use `customer_frustrated_demands_human` when the customer is generally frustrated and demands a human and no higher-priority reason applies. Use `customer_requests_human_no_specific_reason` only for a non-frustrated preference for a human. Medical urgency by itself is not a listed reason code; preserve it in the factual summary unless a higher listed reason independently applies.

Do not infer fraud, a technical system error, an accessibility need, or another specialized category merely from a declined card or urgent language.

## Planning helper

`scripts/transfer_plan.py` deterministically produces the required tool action for this protocol. It reads one JSON object from standard input and writes one JSON object to standard output. It **does not call banking tools**; the executor must perform the returned action with the declared banking tools.

Input schema:

```json
{
  "purchase_declines_with_available_credit": true,
  "transfer_request_count": 4,
  "summary": "Factual summary to send only with a regular transfer.",
  "reason_flags": {
    "customer_frustrated_demands_human": true
  }
}
```

`reason_flags` is optional and consists of applicable valid reason-code names mapped to booleans. Set only facts supported by the conversation. The helper returns `unsupported` when the special protocol does not apply, `specialized_transfer` for counts 1–3, and `regular_transfer` for count 4 or greater. For regular transfers it returns a payload compatible with `transfer_to_human_agents`.

Example runtime call (illustrative only; supply current transcript facts):

```bash
printf '%s' '{"purchase_declines_with_available_credit":true,"transfer_request_count":4,"summary":"...","reason_flags":{"customer_frustrated_demands_human":true}}' | python3 scripts/transfer_plan.py
```

Before acting, validate that the count is a nonnegative integer and that the summary is nonempty for a regular transfer. After a regular-transfer plan, verify that its `reason` is one of the declared `transfer_to_human_agents` enum values and that the tool call includes the returned nonempty summary.
