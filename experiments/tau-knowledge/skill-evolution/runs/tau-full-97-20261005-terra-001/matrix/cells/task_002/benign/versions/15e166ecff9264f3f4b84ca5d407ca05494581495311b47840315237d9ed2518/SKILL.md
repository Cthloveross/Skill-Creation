---
name: highest-flat-cash-back-card
version: 2.0.0
description: Recommend exactly one personal credit card when a customer wants the highest cash back for everyday purchases, using the supplied product evidence to compare documented flat all-purchases cash-back rates.
---

# Highest Flat Cash-Back Card Recommendation

## When to use
Use this Skill when a customer requests one personal Rho-Bank credit-card recommendation for the highest cash back on everyday, ordinary, general, or all purchases.

Interpret the request as a comparison of documented **flat cash-back rates applying to all purchases or all eligible purchases**. Do not treat a rate restricted to a spending category, such as travel, software, dining, or groceries, as an everyday flat rate.

## Required behavior
The product documents and evidence supplied in the current task context are available evidence. Read and compare them before answering. Do **not** say that product terms are unavailable, request documents already supplied in context, or refuse to compare merely because no external search was performed.

When the supplied evidence establishes a unique winner, answer immediately and decisively. The customer requested exactly one card, so give exactly one recommendation and do not present an alternate card as another recommended choice.

Do not use the customer's name, employer, job title, public position, finances, or any unsupported assumption to infer approval or eligibility. This is a product recommendation, not an application or an eligibility determination. Do not access customer records, verify identity, submit an application, or take any account action.

## Selection rules
1. Consider personal cards with an explicit cash-back rate that applies to **all purchases** or **all eligible purchases**.
2. Exclude business cards and category-only bonus rates.
3. Treat an invitation-only card as not ordinarily available for an application recommendation. Other documented conditions, such as a minimum credit score or subscription requirement, should be disclosed concisely rather than silently assumed to be satisfied.
4. Select the unique highest documented qualifying rate. Do not use card prestige, a title, popularity, or an invented tie-breaker.
5. Mention a fee, prerequisite, reward exclusion, or condition only when it is supported by supplied terms.
6. If the supplied evidence is genuinely insufficient, has conflicting rates for one card, or leaves the highest rate tied, explain that specific issue. Do not invent a result and do not give a generic lack-of-terms refusal.

## Fast response procedure
1. Locate the current product documents that state cash back on all purchases or all eligible purchases.
2. Compare their numeric rates and identify the unique highest ordinarily available personal-card rate.
3. Reply in this form, substituting only values established by the current evidence:

   > I recommend the [card name]. It earns [rate]% cash back on all eligible purchases—the highest documented flat rate for everyday spending.

4. Optionally add short, relevant documented tradeoffs after that statement, such as an annual fee or a minimum credit-score requirement. State requirements conditionally; never claim the customer meets them.

The first two sentences must remain a direct recommendation, rather than a conditional offer to compare later. Do not output an internal JSON object to the customer.

## Deterministic entrypoint
When supplied documents can be passed as JSON, use the packaged entrypoint to make the extraction, comparison, and wording repeatable:

```text
python scripts/recommend_from_documents.py < product_documents.json
```

Input schema:

```json
{
  "documents": [
    {
      "document_id": "string",
      "title": "Card name: document title",
      "content": "full supplied product-term text"
    }
  ]
}
```

Successful output schema:

```json
{
  "status": "ok",
  "recommendation": {
    "name": "string",
    "cash_back_rate_percent": "decimal string",
    "evidence": ["document id"],
    "annual_fee": "decimal string or null",
    "eligibility_constraints": ["documented requirement"]
  },
  "customer_message": "string"
}
```

A `needs_review` result contains a precise `reason`. Use that reason to identify the actual evidence gap or conflict. If documents are already visible in task context but cannot be mechanically supplied to the script, perform the same documented comparison directly from that context; the lack of JSON transport is not a reason to withhold a supported answer.

## Final validation
Before sending a successful response, verify all of the following:
- It explicitly says `I recommend the [card name]`.
- It states the selected percentage.
- It ties that rate to all eligible purchases, all purchases, or everyday purchases.
- The selected rate is the unique highest documented qualifying flat personal-card rate.
- Exactly one card is recommended.
- Any fee or eligibility qualification mentioned is documented, and no eligibility claim about the customer is made.
