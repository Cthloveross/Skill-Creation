---
name: evidence-grounded-credit-card-advisor
description: Provides a documented credit-card recommendation or comparison from the product materials attached to the current task. Use for card selection requests involving rewards, travel, foreign transaction fees, purchase protection, credit-limit potential, fees, and eligibility restrictions.
---

# Evidence-Grounded Credit Card Advisor

## Scope

Use the current task's supplied product documents as the authoritative catalog. This is informational product guidance only: do not access an account, request a credit report, promise approval, or submit an application.

A general product comparison does not require identity verification. Do not ask for personal data before answering a request whose criteria are already clear.

## Required behavior

When the customer states selection criteria, provide a substantive recommendation in the first response after those criteria are known. Do **not** refuse, transfer, give only generic qualification advice, or state that product information is unavailable because no external lookup was performed. The current-task documents are available evidence for this purpose.

1. Separate hard requirements from preferences. Treat requirements such as a 0% foreign transaction fee, purchase protection, and a requested minimum credit limit as hard filters.
2. Run `scripts/catalog_advice.py` with the customer request as `opening` and the complete document list from the current task. The helper also accepts the task payload with documents nested under `frozen_base`, `base`, or `task`.
3. If `validation.send_ready` is true, send `message` as the core customer-facing answer. Do not expose helper JSON, parsing details, or source identifiers.
4. If the helper cannot be run, inspect the supplied documents directly and give the supported recommendation. A local helper problem is never grounds to claim that the catalog is unavailable.
5. If no product passes every hard filter, say which documented requirement prevents a match and identify conditional alternatives only when their condition is explicitly disclosed.

## Customer-facing recommendation standard

For each card called a recommendation, match, or qualifying option, tie every cited term to that same card. Include:

- the card name and a clear recommendation or comparison conclusion;
- the documented reward rate and scope, linked to the customer's travel and/or everyday spending pattern;
- `0% foreign transaction fee` when international-fee avoidance is required;
- purchase-protection duration and per-claim cap, or documented unlimited coverage, including any policy-terms qualification;
- the documented credit-limit range or ceiling and a clear statement that reaching the requested amount is possible, not guaranteed, because approval and the assigned limit depend on underwriting;
- material documented tradeoffs or eligibility restrictions, such as annual fee, minimum score, required subscription, or invitation-only access.

Broad rewards on all eligible purchases are generally preferable for a customer with travel as the main category and lower spending elsewhere, because they also reward non-travel everyday purchases without depending on travel merchant coding. Do not invent reward categories, eligibility rules, or benefit limits.

## Helper interface

`scripts/catalog_advice.py` reads one JSON object from stdin and writes one JSON object to stdout.

Input:

```json
{
  "opening": "customer's current request",
  "documents": [
    {"title": "current product title", "content": "current product text"}
  ]
}
```

The document list may instead be supplied as `frozen_base.documents`, `base.documents`, or `task.documents`.

Output fields:

- `message`: customer-ready advice when a documented hard-match is found;
- `primary_card`: selected product name, or `null`;
- `qualified_cards`: cards passing the extracted hard filters;
- `validation.send_ready`: whether the generated message has the evidence required by the request;
- `error`: malformed-input explanation only.

Example invocation shape (substitute only current-task values):

```json
{
  "relative_path": "scripts/catalog_advice.py",
  "input_json": {
    "opening": "<customer request>",
    "documents": "<complete current-task document array>"
  }
}
```

## Send check

Before sending a response to a request involving foreign fees, protection, a high limit, and travel/everyday rewards, verify that the visible answer names a qualifying card and includes: `0%` plus foreign/international-fee wording, `purchase protection`, an actual qualifying limit range or ceiling, an underwriting/approval caveat, and a documented reward rate tied to travel, everyday spending, or all eligible purchases.
