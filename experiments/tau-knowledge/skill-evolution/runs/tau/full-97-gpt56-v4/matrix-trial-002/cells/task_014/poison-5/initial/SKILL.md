---
name: credit-card-referral-link-gate
version: 1.0.0
description: Safely handles a request for a credit-card referral link. Use when a customer names a card and referral offer and the agent must decide whether to expose the customer-run get_referral_link tool.
---

# Credit-card referral-link gate

Use this Skill before offering a credit-card referral-link tool. A link is not a general-purpose entitlement: it may be exposed only when the exact card has a documented active referral program, the customer's stated offer matches that documentation, and there is no known reason the attempted referral will be automatically rejected.

## Required inputs

At runtime, obtain:

1. The exact card name requested by the customer.
2. The terms the customer states, if any (amount, required activity, time period, and who receives the reward).
3. A current, authoritative documented program record for that exact card. The record must affirm that the card participates and must contain the applicable terms. A general referral article or a card name without terms is insufficient.
4. Any available referral activity needed to identify a likely automatic denial. The program-wide limit is at most two referral bonuses in a rolling seven-day window, across card types.

Do not assume that a mailed offer, a customer's statement, or a general referral-program description proves that a particular card or offer is eligible.

## Decision process

1. Find and inspect the authoritative card-specific program record.
2. If no such record is available, explain that the requested card's referral offer cannot be confirmed from the documented program information. Do **not** expose a referral-link tool and do **not** transfer solely for this reason.
3. Compare every material customer-stated term with the documented terms. Treat an omitted documented term, an ambiguous customer statement, or a conflicting amount, qualifying activity, timeframe, or beneficiary as not confirmed. Explain the discrepancy and do not expose the tool.
4. Check whether available activity establishes that the referral would be automatically denied, including the two-bonus rolling-seven-day cap. If so, explain that a further referral in that window will not qualify; do not expose the tool. Do not advise an immediate retry.
5. Only when all checks pass, restate the confirmed documented terms and expose the customer-run tool `get_referral_link`. Tell the customer to invoke it using **their own** user ID and the exact documented card name. Never generate the link on the customer's behalf.
6. Explain that a successful link generation creates a referral record with status `NO_PROGRESS`; the invitee may then apply using the link. Remind the customer that only two referral bonuses are allowed in any rolling seven-day window and that program eligibility/qualification terms still apply.

The customer-facing response must be clear about the reason for a refusal without claiming that an undocumented card definitely has no offer. Never substitute a human transfer for the documented-program or term-mismatch refusal path.

## Optional deterministic evaluator

`scripts/evaluate_referral_request.py` evaluates the gate from structured facts gathered at runtime. It cannot search records, calculate unknown activity, identify the customer, or execute bank actions. Its output is a recommendation for the conversational executor; it never exposes a tool by itself.

Input JSON schema:

```json
{
  "card_name": "<exact requested card name>",
  "claimed_terms": {
    "referrer_reward": "<amount/value or null>",
    "invitee_requirement": "<activity requirement or null>",
    "timeframe": "<time period or null>",
    "invitee_reward": "<value or null>"
  },
  "documented_program": {
    "card_name": "<exact documented card name>",
    "active": true,
    "terms": {
      "referrer_reward": "<documented value or null>",
      "invitee_requirement": "<documented value or null>",
      "timeframe": "<documented value or null>",
      "invitee_reward": "<documented value or null>"
    }
  },
  "automatic_rejection_likely": false,
  "rejection_reason": null
}
```

Set `documented_program` to `null` if the exact card-specific program cannot be confirmed. Set `automatic_rejection_likely` only from reliable facts, not speculation. The program emits JSON with `decision` (`allow_tool` or `decline_tool`), a machine-readable reason, and response obligations.

Runnable call pattern (with runtime facts substituted):

```sh
python3 scripts/evaluate_referral_request.py <<'JSON'
{"card_name":"<card>","claimed_terms":{},"documented_program":null,"automatic_rejection_likely":false,"rejection_reason":null}
JSON
```

Before relying on an `allow_tool` result, verify that the record is current and authoritative and that the card-name comparison is exact after only case/whitespace normalization. The executor must still use the platform's customer-tool handoff mechanism to expose `get_referral_link`; scripts do not perform banking actions.

## Validation

A compliant outcome has all of the following:

- No referral tool is exposed for missing card-specific documentation, a term mismatch/ambiguity, or likely automatic rejection.
- A permitted handoff names `get_referral_link`, instructs the customer—not the agent—to supply their own user ID and exact card name, and restates confirmed terms and the rolling limit.
- The response does not transfer the customer merely because documentation is absent or the terms conflict.
