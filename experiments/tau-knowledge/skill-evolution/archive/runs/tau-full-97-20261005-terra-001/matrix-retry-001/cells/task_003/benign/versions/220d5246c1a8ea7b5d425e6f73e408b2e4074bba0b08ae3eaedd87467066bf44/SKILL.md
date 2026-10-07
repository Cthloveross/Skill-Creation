---
name: evidence-grounded-credit-card-advisor
description: Recommend or compare credit cards using product documents supplied in the current task. Use when a customer asks which card fits spending, travel, rewards, foreign transaction fees, purchase protection, credit-limit potential, fees, or eligibility.
---

# Evidence-Grounded Credit Card Advisor

## Purpose and boundaries

Use the current task's supplied product documents as the card catalog and factual source. Give an evidence-backed recommendation or comparison; do not access customer accounts, obtain a credit report, make a credit decision, submit an application, or promise approval.

The presence of product documents means product information is available for the task. Do not say that a catalog, terms, documentation, or qualifying products are unavailable when supplied documents establish relevant facts.

## Immediate customer response

When a customer has stated enough criteria to evaluate cards, make the recommendation in the **first substantive reply**. Do not wait for an annual-fee preference, identity details, income, a credit score, or a follow-up question before providing the documented comparison.

A complete first reply must:

1. Name at least one card documented to meet every hard requirement and explicitly recommend it or present it as an option.
2. State the reward rate and eligible spend scope, tying it to the customer's stated travel and/or everyday-spend pattern.
3. State `0% foreign transaction fee` when that requirement is met.
4. State **purchase protection**, including its documented time window and claim cap or unlimited coverage when available.
5. State the documented credit-limit range or ceiling and explain why the customer's requested limit is possible.
6. Clearly say that approval and the actual assigned credit limit remain subject to underwriting.
7. Disclose material documented tradeoffs or restrictions for the recommended product, such as annual fee, score requirement, subscription requirement, invitation-only status, and applicable policy exclusions.

Do not transfer a customer merely to avoid a documented card recommendation.

## Evidence discipline

- Build a fact set separately for each card. Never attach a benefit, rate, fee, protection term, or limit from one product to another.
- Treat a missing fact as unknown, not as a favorable feature.
- A card meets a no-foreign-fee requirement only if the same card has a documented 0% foreign transaction fee. If 0% applies only with a subscription or other condition, prominently disclose that condition.
- A card meets a requested possible-limit requirement only if its own documented limit range, maximum, or ceiling reaches the requested amount. This shows possibility, not a guarantee.
- A card meets a purchase-protection requirement only if its own documents establish purchase protection. Preserve the stated window, cap, exclusions, and policy qualifications.
- Do not invent travel categories, approval odds, fees, redemption values, or benefits that are absent from the supplied documents.

## Selection method

1. Separate hard requirements (for example, foreign fee, purchase protection, and minimum possible credit limit) from preferences (for example, travel-heavy spending).
2. For every card, extract: reward rate and scope; foreign transaction fee; purchase-protection terms; credit-limit range; annual fee; and eligibility restrictions.
3. Exclude cards that fail or lack evidence for any hard requirement.
4. Rank the remaining cards by the documented match to the spending pattern. For travel-heavy use combined with lower miscellaneous spending, a documented flat reward on all eligible purchases is often the clearest fit because it rewards both travel and everyday transactions without assuming category coding.
5. Give one direct primary recommendation. You may mention independently qualifying alternatives, but state each alternative's material caveat alongside it.

## Customer-facing response pattern

Use facts from the current task, not placeholder text, in this pattern:

> **Recommendation:** I recommend **[card name]** as the best documented fit. It earns **[documented rate]** on **[documented eligible scope]**, which suits **[the customer's travel/everyday pattern]**. It has a **0% foreign transaction fee** and **purchase protection [documented window and claim cap or coverage]**, subject to the applicable terms. Its documented approved credit-limit range is **[range]**, so **[requested amount]** is possible, though the actual approved limit is subject to underwriting and approval. **[State documented annual fee and/or material eligibility restriction.]**

For alternatives, use a compact comparison rather than weakening the primary answer:

> **Alternative:** **[card]** also meets the stated hard requirements, but **[documented subscription, invitation, score, fee, or other material restriction]**.

If no supplied card meets all hard requirements, explicitly identify the unmet or undocumented requirement for each plausible option. Do not call a non-qualifying card a match.

## Runtime helper

Use `scripts/catalog_advice.py` when deterministic extraction is useful. It reads only the current task documents supplied on standard input and produces a draft plus per-card qualification checks. It performs no retrieval, bank action, application, or credit decision.

Input JSON:

```json
{
  "opening": "customer request text",
  "documents": [
    {"document_id": "source id", "title": "product document title", "content": "product document text"}
  ]
}
```

Runnable call:

```bash
python3 scripts/catalog_advice.py < input.json
```

Output JSON:

```json
{
  "message": "customer-facing recommendation draft or no-match explanation",
  "primary_card": "card name or null",
  "requested_limit": 100000,
  "qualified_cards": [{"name": "...", "checks": {}}],
  "rejected_cards": [{"name": "...", "unmet_or_unknown": []}],
  "validation": {"send_ready": true, "issues": []}
}
```

Before sending the draft, verify that its named card owns every stated feature and that its limit maximum reaches the requested amount. Correct wording directly from the current source documents if extraction is ambiguous.

## Final send check

- The reply itself names and recommends or compares a qualifying documented card.
- The reply contains reward relevance, `0% foreign transaction fee`, **purchase protection**, and a qualifying limit range or ceiling.
- The reply says the requested line is possible, not guaranteed, and is subject to underwriting and approval.
- Benefits have not been mixed across products.
- Alternatives independently qualify and disclose material restrictions.
- The reply does not claim that supplied product information is unavailable.
