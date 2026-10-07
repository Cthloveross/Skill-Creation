---
name: highest-flat-cash-back-card
version: 1.2.0
description: Recommend exactly one personal Rho-Bank card for a customer seeking the highest cash back on everyday purchases by extracting and comparing supplied product terms for flat all-eligible-purchases cash-back rates.
---

# Highest Flat Cash-Back Card Recommendation

## When to use
Use this Skill when a customer asks for exactly one Rho-Bank personal credit-card recommendation based on the highest cash back for everyday, ordinary, or general purchases.

Interpret this request as seeking the highest documented **flat cash-back rate on all eligible purchases**. A rate restricted to a category (for example, travel, software, or groceries) is not a flat everyday-purchase rate.

This Skill provides product information only. Do not access customer records, submit an application, make approval claims, or infer eligibility from a customer's employer, title, or finances.

## Evidence and decision rules
1. Treat product documents and evidence supplied in the current task as available evidence. Do **not** claim that product terms are unavailable merely because no external search was performed.
2. Consider only personal cards with an explicit flat rate applying to all purchases or all eligible purchases. Exclude business cards and category-only reward rates.
3. An invitation-only card is not ordinarily available for an application recommendation. A documented minimum credit score, subscription requirement, or similar stated prerequisite is a condition to disclose, not a reason to silently discard an otherwise ordinarily available card.
4. Select the unique highest documented qualifying rate. Never use a title, popularity, or unsupported assumption as a tie-breaker.
5. If the supplied terms establish a unique result, make the recommendation immediately. Do not ask the customer to provide terms already present in the task context.
6. If the evidence is genuinely missing, internally inconsistent, or tied, explain that specific limitation and request only the missing comparison information. Do not invent a recommendation.

## Required workflow
1. Read the supplied product documents relevant to personal credit-card rewards, including related fee and eligibility documents.
2. To make extraction repeatable, pass all available product documents to `scripts/extract_candidates.py`.
3. If extraction returns `status: "ok"`, send its `cards` array unchanged to `scripts/recommend.py`.
4. If recommendation returns `status: "ok"`, use `customer_message` as the customer-facing answer. It is deliberately decisive and presents only one recommendation.
5. If either script returns `status: "needs_review"`, use its reason to describe the evidence gap or conflict. Do not replace a supported recommendation with a generic refusal.

## Customer-response requirements
For a successful selection, begin exactly in this form, with the selected values:

> I recommend the [card name]. It earns [rate]% cash back on all eligible purchases—the highest documented flat rate for everyday spending.

Then, if documented, concisely state material tradeoffs or conditions such as an annual fee, minimum credit score, subscription prerequisite, eligible-purchase exclusions, or return adjustments. Phrase prerequisites as requirements, not as a claim that the customer qualifies.

Give exactly one recommendation. Do not offer a second card as an alternative or say that the product terms are unavailable when the supplied evidence supports the selection.

## Script interfaces

### 1. Extract candidates
Run:

```text
python scripts/extract_candidates.py < product_documents.json
```

Input is one JSON object:

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

The extractor emits either:

```json
{
  "status": "ok",
  "cards": [
    {
      "name": "string",
      "personal": true,
      "cash_back_rate_percent": "decimal string",
      "applies_to_all_eligible_purchases": true,
      "ordinary_application_available": true,
      "annual_fee": "decimal string or null",
      "eligibility_constraints": ["documented requirement"],
      "conditions": [],
      "evidence": ["document identifier"]
    }
  ]
}
```

It returns `needs_review` if no qualifying flat rate can be extracted or if a single card has conflicting flat rates. Review the cited documents in that case rather than guessing.

### 2. Select and phrase the recommendation
Run:

```text
python scripts/recommend.py < candidates.json
```

`candidates.json` must contain the `cards` array described above. Required fields for each card are `name`, `personal`, `cash_back_rate_percent`, `applies_to_all_eligible_purchases`, and nonempty `evidence`. `ordinary_application_available` defaults to `true` only when no invitation-only restriction is documented. `annual_fee` may be null.

The selector returns `status: "ok"` with a `customer_message` for a unique maximum. It returns `needs_review` when there is no qualifying candidate, a tie, or invalid input.

## Final validation
Before sending a successful answer, confirm:
- The rate is explicitly flat across all eligible purchases or all purchases.
- The selected card has the unique highest documented qualifying personal-card rate.
- The answer includes “I recommend the [card name]” and the percentage.
- The answer ties the rate to all eligible or everyday purchases.
- Exactly one card is recommended.
- Every fee, access requirement, and reward condition mentioned is supported by supplied product terms.
