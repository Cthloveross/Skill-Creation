---
name: credit-card-decline-human-transfer
version: 1.1.0
description: Triage credit-card purchase declines despite available credit and apply the required first-three/ fourth-request human-transfer sequence when the customer explicitly requests a person.
---

# Credit-card decline and human-transfer protocol

Use this Skill for a customer who says credit-card purchases are declined despite available credit. It covers the special sequence only when that customer **clearly asks** to speak with, be transferred to, or be connected to a human agent.

## Track the request count precisely

Maintain `human_request_count` for the current interaction. Initially it is `0`. Do not increment it for a decline report alone, for general frustration, or for an agent's offer to investigate. Increment it once only when the current customer message contains a clear human-transfer request. This distinction is essential: do not initiate any transfer before the customer actually asks for one.

If the customer reports the decline but has not requested a human, offer to investigate and request the email address on the account. Do not claim to have reviewed an account, verified identity, or found a cause at this point. For example: “I can look into this. Please provide the email address on your account so I can review your credit-card account and recent transactions.” If the customer instead asks for a human, stop the ordinary investigation path and follow the sequence below.

## Deterministic planning helper

Run `scripts/conversation_plan.py` with JSON on stdin. It emits JSON on stdout and never performs banking actions. Input schema:

- `purchase_declines_despite_available_credit` (boolean, required): must be `true` for this Skill.
- `clear_human_request` (boolean, required): whether the **current** message is a clear transfer request.
- `human_request_count_before` (non-negative integer, default `0`): number of earlier clear requests, before the current message.
- `frustrated` (boolean, optional): use `true` for a frustrated/demanding request when no higher-priority reason applies.
- `specific_reason` (optional permitted transfer reason code): provide only when a higher-priority applicable reason has been identified.
- `summary` (nonempty string, required only for the fourth request): factual issue and actions already taken.

Example—initial decline report without a human request:

```bash
printf '%s' '{"purchase_declines_despite_available_credit":true,"clear_human_request":false,"human_request_count_before":0}' | python3 scripts/conversation_plan.py
```

Validate the returned `status` is `ok`, retain its `human_request_count`, and execute only the returned banking-tool calls. An `error` or `unsupported` output means do not infer a tool call from the helper.

## Required execution sequence

1. For `clear_human_request: false`, send the returned request-for-email message. There is no transfer and the count does not change.
2. For the first, second, and third clear request (returned count `1`, `2`, or `3`), call `unlock_discoverable_agent_tool` with `initial_transfer_to_human_agent_0218`, then call `call_discoverable_agent_tool` with that name and `arguments` set to `{}`. Do **not** call `transfer_to_human_agents` for any of these three requests.
3. If the initial tool reports that a transfer is initiated and lines are busy, accurately tell the customer that the lines are busy and the transfer request was initiated. Continue to count later clear requests.
4. On the fourth clear request (returned count `4`), call `transfer_to_human_agents` with the planned reason and factual summary. Select the highest-priority applicable reason. When no higher-priority operational reason applies and the customer is frustrated/demanding, use `customer_frustrated_demands_human`; for a calm request with no specific reason, use `customer_requests_human_no_specific_reason`.
5. Only after a successful tool result, tell the customer the transfer succeeded and a human agent will assist shortly.

## Boundaries and failures

- Do not replace the initial specialized tool with the standard transfer tool on requests 1–3, even if unlocking/calling it fails. Report that result accurately.
- Do not invent account details, transaction results, identity verification, or diagnoses.
- A request for the email address is not identity verification. Before revealing account information or taking identity-sensitive action, follow any applicable verification requirements.
- If the count exceeds four or the facts do not match this Skill, the documented special protocol no longer determines a next action; follow current applicable operational guidance rather than guessing.
