---
name: evidence-grounded-credit-card-advisor
description: Give a documented, customer-facing recommendation or comparison of credit cards using the current task's supplied product materials. Use when a customer asks which card fits rewards, travel, foreign transaction fees, purchase protection, credit-limit potential, fees, or eligibility requirements.
---

# Evidence-Grounded Credit Card Advisor

## Core operating rule

Treat the product documents supplied with the current task as the available card catalog. When a customer provides card-selection criteria, answer with a documented recommendation in the **same response**. Do not say that the catalog, terms, product information, or a documented fit is unavailable merely because no external lookup was performed.

This is general product guidance. Do not access an account, request identity information, pull credit, guarantee approval, or submit an application.

## Workflow

1. Identify hard requirements (for example, no foreign transaction fee, purchase protection, and a requested minimum credit limit) and preferences (such as travel-heavy or everyday spending).
2. Use the current task's product documents only. Collect facts by card, including rewards, fee, protection, credit-limit range, annual fee, and access restrictions.
3. Run `scripts/catalog_advice.py` with the customer request and the complete runtime document list. It accepts the task payload directly when documents are nested under `frozen_base`, `base`, or `task`.
4. When `validation.send_ready` is true, use `message` as the customer-facing core response. Do not expose the helper's JSON, implementation, source IDs, or parsing process.
5. If a helper cannot be run, inspect the supplied documents directly and still provide the documented answer. A local scripting issue is never a reason to refuse the comparison.
6. If no card meets all hard requirements, explain the specific documented mismatch. Present a conditional option only with its material condition clearly stated.

## Required content for a qualifying recommendation

For every product described as a recommendation, match, or qualifying option, ensure all stated benefits belong to that same product. Include:

- the full card name and a direct conclusion such as “I recommend” or “best documented fit”;
- its documented rewards rate and scope, tied to the customer's travel and/or everyday pattern;
- `0% foreign transaction fee` when avoiding international fees is required;
- purchase-protection duration plus per-claim maximum, or documented unlimited coverage, with any applicable policy-terms qualification;
- the documented credit-limit range or ceiling and an explicit statement that the requested amount is possible but not guaranteed because approval and the assigned limit depend on underwriting;
- material documented eligibility restrictions and tradeoffs, including annual fee, score threshold, required subscription, or invitation-only access.

Favor a documented reward rate applying broadly to eligible purchases when the customer has travel-heavy spending but also wants an everyday card: this can reward travel and lower non-travel spend without relying on merchant-category coding. Do not invent category bonuses, eligibility, fees, benefit caps, or approval outcomes.

## Immediate-answer standard

Do not ask for personal data or a credit score before providing a general comparison when the stated criteria can be evaluated from the documents. Do not provide only generic qualification guidance. The first substantive answer must name at least one documented qualifying card and address every stated hard requirement.

## Helper interface

`scripts/catalog_advice.py` reads one JSON object from stdin and emits one JSON object to stdout.

Input schema:

```json
{
  "opening": "customer request",
  "documents": [
    {"title": "product-document title", "content": "product-document content"}
  ]
}
```

`documents` may instead appear under `frozen_base.documents`, `base.documents`, or `task.documents`.

Output schema:

- `message` — customer-ready advice for the top documented hard match, or `null` if none was found;
- `primary_card` — selected card name, or `null`;
- `qualified_cards` — cards satisfying extracted hard requirements;
- `rejected_cards` — cards and unmet/unknown hard filters;
- `validation.send_ready` — whether the message has the evidence needed for the request;
- `error` — input error only.

Runnable call shape (substitute current-task data only):

```json
{
  "relative_path": "scripts/catalog_advice.py",
  "input_json": {
    "opening": "<customer request>",
    "documents": "<complete current-task documents array>"
  }
}
```

## Final visible-response check

Before sending advice for a request involving travel/everyday rewards, foreign fees, purchase protection, and a high limit, verify that the visible response contains all of the following:

1. a named documented recommendation;
2. a documented rewards percentage plus `travel`, `everyday`, or `all eligible purchases` rationale;
3. `0%` and foreign/international-fee wording;
4. the words `purchase protection` and its documented terms;
5. a qualifying credit-limit range or ceiling that shows the requested limit can be reached; and
6. an approval/underwriting caveat.
