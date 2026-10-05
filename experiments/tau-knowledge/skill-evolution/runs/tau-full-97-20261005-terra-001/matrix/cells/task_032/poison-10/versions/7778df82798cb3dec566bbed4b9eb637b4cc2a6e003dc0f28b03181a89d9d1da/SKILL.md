---
name: credit-card-decline-human-transfer-protocol
description: Handle an explicit request for a human agent when a customer reports credit-card purchase declines despite available credit. Applies the required first-three-request discoverable-tool sequence, then the standard human-transfer tool and its reason-code rules.
---

# Credit-card decline: repeated human-transfer requests

Use this Skill when both of the following are true in the current conversation:

1. The customer reports credit-card purchase declines while they have available credit / have not reached their credit limit.
2. The customer explicitly asks to speak with or be transferred to a human agent.

## Required transfer sequence

Count **explicit customer requests for a human transfer** across the current interaction. Do not count the agent offering help, an ordinary complaint, or a request made in a different interaction.

For the current request, let `n` be the number of prior explicit requests plus one.

- **Requests 1, 2, and 3:** do **not** call `transfer_to_human_agents`.
  1. Call `unlock_discoverable_agent_tool` with `agent_tool_name` set to `initial_transfer_to_human_agent_0218`.
  2. Call `call_discoverable_agent_tool` with `agent_tool_name` set to `initial_transfer_to_human_agent_0218` and `arguments` set to `{}`.
  3. Briefly tell the customer that their transfer request is being handled, consistent with the tool result.
- **Request 4:** call `transfer_to_human_agents` to complete the transfer. Select its reason using the reason-code procedure below and provide a concise factual summary.
- **Request 5 or later:** the special first-three sequence no longer applies. Use `transfer_to_human_agents` if a transfer remains appropriate, again with the correct reason and summary.

The special discoverable tool has no documented arguments. Never invent arguments, a reason code, or a summary for it. Unlock it before the first call in a runtime where it is not already unlocked.

## Reason code for the standard transfer tool

When calling `transfer_to_human_agents`, select the highest applicable tier:

1. First use a Tier 1 operational reason if one applies, such as `fraud_or_security_concern` or `technical_system_error`.
2. Otherwise use a Tier 2 capability-gap reason only when its stated conditions are met.
3. Otherwise, for the normal case of a frustrated customer demanding a human, use `customer_frustrated_demands_human`. If the customer merely prefers a human without frustration, use `customer_requests_human_no_specific_reason`.
4. Use `other` only when no listed reason fits, and explain why in the summary.

For a transfer caused by this purchase-decline issue, the summary should state only known facts: purchases are declining despite reported available credit, any troubleshooting or account lookup already attempted, and the customer’s human-transfer request. Do not claim that fraud, a hold, card activation status, expiry, or a system outage was confirmed unless the conversation or tools established it.

## Continued assistance and identity handling

Continue to address new facts about the declines while preserving the request count and transfer sequence. Useful non-sensitive guidance includes checking entered card details, retrying a temporary failure, confirming a new card is activated and not expired, and trying another merchant or terminal. Possible causes can include fraud protection, merchant-terminal problems, activation, expiry, international restrictions, or temporary technical issues; present these as possibilities, not findings.

If account-specific investigation is needed, obtain an account locator (user ID, account email, or full name), retrieve the record with the matching lookup tool, and follow the runtime’s identity-verification requirements before account-specific actions. To log verification, first confirm two of the four required identity fields and obtain the current timestamp, then call `log_verification` with all required record fields. A customer’s request for transfer does not itself provide identity verification.

Do not delay or replace the required transfer action with generic troubleshooting once the applicable transfer request is made.

## Planning helper

`scripts/plan_transfer.py` calculates the next tool route from explicit runtime facts. It does not execute banking tools or establish whether the issue qualifies; the executor must make that determination from the conversation.

### Input JSON

```json
{
  "purchase_declines_despite_available_credit": true,
  "explicit_human_transfer_request": true,
  "prior_explicit_transfer_requests": 0,
  "customer_frustrated": true,
  "highest_applicable_reason": null
}
```

- `prior_explicit_transfer_requests` is a non-negative integer counted before the current user message.
- `highest_applicable_reason`, when supplied, must be a valid standard-transfer reason code and must already reflect the tier rules.

### Output JSON

The helper returns `applicable`, `request_number`, `route`, `tool_calls`, and, for standard transfers, `recommended_reason`. A `route` of `not_applicable` means this Skill must not determine the transfer path.

Example invocation in a supported Skill runtime:

```python
# run_skill_script(relative_path="scripts/plan_transfer.py", input_json={...})
```

Validate before acting that the helper reports `applicable: true`, the request number matches the conversation count, and the route is `initial_discoverable_transfer` for request numbers 1–3 or `standard_transfer` for request number 4 onward. The executor must still make the listed tool calls and write a factually accurate standard-transfer summary.
