---
name: evidence-grounded-credit-card-advisor
description: Recommend or compare credit cards using the product documents supplied in the current task. Use for requests involving rewards, travel use, foreign transaction fees, purchase protection, credit-limit potential, annual fees, or eligibility.
---

# Evidence-Grounded Credit Card Advisor

## Scope

Use the current task's supplied product documents as the product catalog. Provide factual, customer-facing guidance from those documents only. Do not retrieve external offers, access an account, obtain a credit report, make an underwriting decision, submit an application, or guarantee approval.

The supplied documents are authoritative task evidence. Do not say that product terms, a catalog, or documented options are unavailable when the task includes product documents.

## Required workflow

1. Identify the customer's hard requirements and spending pattern. Treat phrases such as "no foreign transaction fees," "purchase protection," and "at least $100,000" as hard requirements.
2. Read the supplied documents and run `scripts/catalog_advice.py`, passing the complete current-task document array and the customer's request.
3. Send the returned `message` when `validation.send_ready` is true. It is analysis-only and does not apply for a card or take any banking action.
4. If a script invocation is unavailable or reports no match, inspect the supplied product documents directly before responding. A parser limitation is not evidence that a documented option is unavailable.
5. Give a recommendation in the first substantive response after the customer states enough criteria. Do not wait for identity, income, score, or fee-preference questions merely to identify documented options.

## Customer-answer standard

For a recommended card, attach every benefit to that same card and cover every stated hard requirement:

- Name the card and give clear advice, for example, "I recommend" or "best documented fit."
- State the documented reward rate and its scope, then connect it to the stated everyday and travel spending pattern without inventing category bonuses.
- State the documented **0% foreign transaction fee** where that is required. Prominently disclose any condition needed for that rate.
- State **purchase protection**, including its documented time window and per-claim cap or stated unlimited coverage, and preserve policy-terms/exclusions language.
- State the documented credit-limit range or ceiling. Say the requested amount is possible only if the range reaches it, and that approval and the assigned limit remain subject to underwriting.
- Disclose material documented restrictions relevant to the recommendation, such as annual fee, minimum score, premium-subscription requirement, or invitation-only availability.

When several cards qualify, make a primary recommendation based on the documented spending fit. You may list alternatives, but disclose each alternative's material eligibility caveat. A card earning a flat rate on all eligible purchases is generally a strong documented fit when travel is the main category and lower everyday spending also occurs, because it does not depend on merchant-category coding.

Never replace a grounded recommendation with a generic qualification explanation, a transfer, or an unsupported statement that terms are unavailable.

## Script interface

`scripts/catalog_advice.py` receives JSON on stdin:

```json
{
  "opening": "customer request as text",
  "documents": [
    {"document_id": "optional source id", "title": "document title", "content": "document text"}
  ]
}
```

It emits JSON on stdout with:

- `message`: ready-to-send advice;
- `primary_card`: the selected documented card or `null`;
- `qualified_cards` and `rejected_cards`: per-card hard-requirement checks;
- `validation.send_ready`: whether a fully supported recommendation was produced;
- `error`: present only for malformed input.

Example invocation shape using actual current-task material:

```json
{"relative_path":"scripts/catalog_advice.py","input_json":{"opening":"<customer request>","documents":[{"document_id":"<id>","title":"<title>","content":"<text>"}]}}
```

## Final send check

Before sending, verify that the response names a qualifying card; gives a rewards rationale; says `0%` and `foreign transaction fee` if required; says `purchase protection`; gives a limit range or ceiling reaching the requested amount; and says approval and assigned limit remain subject to underwriting. Do not characterize supplied product information as unavailable.
