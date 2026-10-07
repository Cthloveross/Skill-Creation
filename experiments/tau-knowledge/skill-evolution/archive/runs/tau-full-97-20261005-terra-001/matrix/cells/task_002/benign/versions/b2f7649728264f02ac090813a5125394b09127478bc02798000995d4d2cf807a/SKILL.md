---
name: highest-flat-cash-back-card
version: 3.0.0
description: Give exactly one evidence-based personal credit-card recommendation when a customer asks for the highest flat cash back on everyday purchases.
---

# Highest Flat Cash-Back Card Recommendation

## Use this Skill
Use when a customer asks which personal card has the best, highest, or most cash back for everyday, general, ordinary, or all purchases and asks for one recommendation.

## Non-negotiable response behavior
The supplied product documents and evidence in the task context are product terms. Treat them as available evidence even if they were not provided by the customer in the chat message itself.

When those terms establish a unique highest qualifying rate, answer immediately with exactly one decisive recommendation. Do not:

- claim product terms are unavailable;
- ask the customer to provide documents already present in the task context;
- defer the comparison pending an external search;
- respond only with an offer to compare later; or
- give a generic refusal.

A direct request for the highest everyday cash-back card needs no identity verification, account lookup, application action, eligibility determination, or additional personal information. Do not use a customer's name, employer, public role, finances, or presumed credit profile to decide the recommendation.

## What qualifies as everyday cash back
1. Consider personal cards whose supplied terms explicitly say that cash back applies to **all purchases** or **all eligible purchases**.
2. Compare the stated numeric percentages.
3. Exclude business cards and rates limited to categories such as travel, software, dining, groceries, or other merchant types.
4. Do not recommend an invitation-only card as an ordinarily available application choice.
5. Choose the unique highest remaining documented flat rate. Do not use card prestige, marketing language, or an invented tie-breaker.

A requirement such as a minimum credit score or subscription is not a reason to refuse a supported product comparison. If relevant, disclose it conditionally and concisely; never state or imply that the customer satisfies it.

## Required customer-facing answer
For a supported unique winner, the response must begin with this direct structure, using the selected evidence-derived values:

> I recommend the [card name]. It earns [rate]% cash back on all eligible purchases—the highest documented flat rate for everyday spending.

This is one recommendation, not a list. Do not recommend a second card as an alternative. It is fine to omit other card names entirely.

After the two required sentences, optionally add only concise, documented tradeoffs, for example an annual fee, a redemption condition, or an access requirement. Do not output an internal JSON object to the customer.

## Evidence-resolution procedure
1. Read all current supplied card documents and evidence before responding.
2. Extract every explicitly documented all-purchases or all-eligible-purchases cash-back rate and associate it with its card.
3. Remove category-only, business, and invitation-only options.
4. Select the unique highest remaining percentage.
5. Send the required direct recommendation and rate statement in the same response.
6. Before sending, check that the message explicitly contains: `I recommend the [card name]`, the percentage, and `all eligible purchases`, `all purchases`, or `everyday purchases`.

If and only if the supplied evidence genuinely has no qualifying rate, has unresolved conflicting rates for the same card, or has a tie for the highest rate, explain that precise evidence issue. Never substitute a generic "terms unavailable" refusal when documents are available.

## Deterministic entrypoint
When documents are available as JSON, use the packaged comparison helper:

```text
python scripts/recommend_from_documents.py < product_documents.json
```

Input on stdin:

```json
{
  "documents": [
    {
      "document_id": "string",
      "title": "card product title",
      "content": "full supplied product-term text"
    }
  ]
}
```

Successful stdout result:

```json
{
  "status": "ok",
  "recommendation": {
    "name": "string",
    "cash_back_rate_percent": "decimal string",
    "annual_fee": "decimal string or null",
    "eligibility_constraints": ["string"],
    "evidence": ["document id"]
  },
  "customer_message": "direct customer-facing recommendation"
}
```

If the documents are visible in context but cannot be passed to the script, perform the same comparison manually from the visible terms and still give the supported answer. JSON transport is not an evidence gap.

A `needs_review` output identifies a specific unresolved condition. Do not expose internal script status unless it helps explain a real evidence limitation.
