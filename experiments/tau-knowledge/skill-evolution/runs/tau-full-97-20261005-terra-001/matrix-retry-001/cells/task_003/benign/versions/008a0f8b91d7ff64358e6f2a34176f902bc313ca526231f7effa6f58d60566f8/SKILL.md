---
name: evidence-grounded-credit-card-advisor
description: Recommend or compare credit cards from product documents supplied with the current task. Use for requests involving rewards, travel or everyday spending, foreign transaction fees, purchase protection, credit-limit potential, fees, and eligibility conditions.
---

# Evidence-Grounded Credit Card Advisor

## Scope

Use the product documents supplied with the current task as the factual catalog. Provide product information and a recommendation; do not access an account, run a credit check, promise approval, submit an application, or take a banking action.

## Immediate response rule

When the customer states card criteria, give a grounded recommendation or comparison in the first substantive reply. The supplied task documents are evidence for this purpose. Do **not** say that product terms, a catalog, or documentation are unavailable when those documents are present; do not ask the customer to provide the catalog; and do not transfer solely to avoid making a documented recommendation.

Do not require income, identity verification, a credit score, or an annual-fee preference before giving the initial evidence-backed recommendation. Instead, disclose any documented eligibility restriction and explain that approval and the assigned line are underwriting decisions.

## Per-card evidence rules

1. Assemble facts separately for each card. Never combine a reward, fee, limit, protection, or eligibility fact from different products.
2. Treat missing evidence as unknown. A card meets a hard requirement only when the documents establish that requirement for that same card.
3. For a no-foreign-fee requirement, require a documented `0%` foreign transaction fee. If the fee is `0%` only under a condition, disclose the condition prominently.
4. For purchase protection, state that exact phrase and include the documented coverage window and per-claim cap, or documented unlimited coverage, when available.
5. For a requested possible credit line, use a documented limit range, maximum, or ceiling that reaches the requested amount. A range or ceiling establishes possibility, not a promise.
6. Preserve material restrictions such as subscription requirements, invitation-only access, score thresholds, annual fees, transaction eligibility rules, and policy exclusions.
7. Do not infer category rewards, approval likelihood, or benefits that are not documented.

## Selection process

1. Identify hard requirements (for example, fee, protection, and requested minimum limit) separately from spending preferences.
2. Extract each card's reward rate and scope, foreign transaction fee, limit range, purchase-protection terms, and eligibility conditions from the supplied documents.
3. Exclude products that fail a hard requirement or lack evidence for it.
4. Rank the remaining cards by documented fit. For mixed everyday use where travel is the main category, a strong flat all-eligible-purchase reward is generally a clear fit because it rewards travel and lower non-travel spend without assuming an undocumented category bonus.
5. Give one explicit primary recommendation. Mention an alternative only if it independently satisfies every hard requirement, and put its material caveat beside it.

## Required customer-facing content

The first substantive answer must name a qualifying card and explicitly recommend or present it as an option. For the primary card, include all of these facts in connected prose:

- card name and a clear recommendation;
- documented reward rate and eligible scope, tied to the customer's travel and/or everyday pattern;
- `0% foreign transaction fee`;
- **purchase protection**, with the documented window and cap or unlimited coverage;
- documented credit-limit range or ceiling showing why the requested amount is possible; and
- a statement that the actual approved limit is subject to underwriting and approval.

Use this response pattern, filling every bracket from the current task's documents:

> **Recommendation:** I recommend **[card]** as the best documented match. It earns **[rate]** on **[eligible scope]**, which fits **[travel and everyday spending pattern]**. It has a **0% foreign transaction fee** and **purchase protection [window and cap/coverage]**, subject to applicable terms. Its documented credit-limit range or ceiling is **[range/ceiling]**, so a limit of at least **[requested amount]** is possible; the exact approved limit is subject to underwriting and approval.

If no product is documented to meet every hard requirement, say which requirement is absent or unmet for each plausible product. Do not describe a non-qualifying product as a match.

## Runtime helper

`scripts/catalog_advice.py` deterministically groups current-task documents by card, checks the customer's foreign-fee, purchase-protection, and credit-limit requirements, and drafts a recommendation. It only reads JSON supplied on standard input; it does not retrieve documents, make credit decisions, or perform bank actions.

Input schema:

```json
{
  "opening": "customer request",
  "documents": [
    {"document_id": "source id", "title": "document title", "content": "document text"}
  ]
}
```

Run the packaged helper with a JSON file containing the current task's actual opening and documents:

```bash
python3 scripts/catalog_advice.py < input.json
```

Output schema:

```json
{
  "message": "customer-facing draft or no-match explanation",
  "primary_card": "string or null",
  "requested_limit": 0,
  "qualified_cards": [],
  "rejected_cards": [],
  "validation_note": "string"
}
```

Use `message` as a draft only after reviewing its selected card, `qualified_cards`, source IDs, and the underlying supplied documents. If parsing is ambiguous, correct the factual wording from the source rather than guessing.

## Final send check

- The response itself, not merely an internal note or JSON object, recommends or compares a documented card.
- Every stated primary-card benefit is documented for that same card.
- It includes rewards relevance, `0% foreign transaction fee`, **purchase protection**, and a sufficient documented limit range or ceiling.
- It says the requested limit is possible, not guaranteed, and subject to underwriting and approval.
- Any alternative independently qualifies and discloses its material restriction.
- It does not claim that supplied product information is unavailable.
