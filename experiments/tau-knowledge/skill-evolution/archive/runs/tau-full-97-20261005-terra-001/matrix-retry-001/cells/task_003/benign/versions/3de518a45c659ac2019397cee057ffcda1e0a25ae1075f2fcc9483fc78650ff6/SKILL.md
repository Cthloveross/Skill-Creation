---
name: evidence-grounded-credit-card-advisor
description: Recommend or compare credit cards using the current task's supplied product documents. Use for requests about rewards, travel spending, foreign transaction fees, purchase protection, credit-limit potential, annual fees, or eligibility.
---

# Evidence-Grounded Credit Card Advisor

## Scope and safety

Use the product documents supplied with the current task as the card catalog. Give factual, customer-facing product guidance; do not access a customer account, retrieve external offers, obtain a credit report, make an underwriting decision, submit an application, or guarantee approval.

Product documents attached to the task are available evidence. Do not say that the catalog, terms, or product information are unavailable merely because they are task-supplied rather than externally retrieved.

## Required workflow

1. Identify the customer's hard requirements (for example: no foreign transaction fee, purchase protection, and a requested possible credit limit) and spending pattern.
2. Use `scripts/catalog_advice.py` with the customer's request in `opening` and the complete current-task document array in `documents`.
3. If `validation.send_ready` is `true`, use the returned `message` as the substantive answer, making only wording changes that preserve every fact and caveat. Send it in the first substantive reply; do not wait for identity, income, score, or fee-preference questions.
4. If the helper reports no match, explain only the documented unmet or unknown features. Never present a partly supported card as satisfying every hard requirement.
5. If the helper input is malformed, inspect the supplied documents directly and apply the same per-card checks. Do not invent terms or use external information.

The helper is analysis-only. Running it does not apply for a card or take a banking action.

## Customer-answer requirements

For every recommended card, keep all benefits attached to that same card and explicitly cover each hard requirement:

- Name the card and use clear advice language such as “I recommend” or “best documented fit.”
- State its documented reward rate and scope. Explain why that scope fits the customer's everyday and/or travel spending without inventing a category bonus.
- For an international-use requirement, state the documented **0% foreign transaction fee** and prominently state any condition required for that rate.
- State **purchase protection**, including its documented coverage period and per-claim cap or stated unlimited coverage when provided. Preserve policy-terms/exclusions language.
- State the documented credit-limit range or ceiling. Explain that the requested amount is *possible* only where the range/ceiling reaches it; it is never guaranteed.
- State that approval and the assigned limit depend on underwriting.
- Disclose material documented restrictions for the recommended card, including annual fee, score threshold, subscription requirement, invitation-only access, and relevant exclusions.

For several qualifying cards, make one primary recommendation based on documented fit, then optionally list independently qualifying alternatives with their material caveats. A flat, all-eligible-purchase reward is generally a strong fit for travel-heavy spending with low other everyday spend because it covers both without relying on merchant-category classification.

Do not transfer a customer or give a generic eligibility explanation instead of providing a documented recommendation.

## Helper interface

Call `scripts/catalog_advice.py` through the packaged-script runtime. Its stdin JSON schema is:

```json
{
  "opening": "customer request as text",
  "documents": [
    {"document_id": "optional source id", "title": "document title", "content": "document text"}
  ]
}
```

It writes one JSON object to stdout:

- `message`: ready-to-send grounded recommendation or no-match explanation;
- `primary_card`: chosen card name or `null`;
- `qualified_cards` / `rejected_cards`: per-card evidence checks;
- `validation.send_ready`: whether the recommendation contains the detected requirements;
- `error`: present only for malformed input.

Example runtime invocation shape (supply actual current-task documents, not example products):

```json
{"relative_path":"scripts/catalog_advice.py","input_json":{"opening":"<customer request>","documents":[{"document_id":"<id>","title":"<title>","content":"<text>"}]}}
```

## Final send check

Before responding, verify that the actual response names a qualifying card, includes the rewards rationale, says `0%` and `foreign transaction fee` when required, says `purchase protection`, gives a range or maximum reaching the requested limit, and says that approval/limit assignment remain subject to underwriting. Do not claim supplied product information is unavailable.
