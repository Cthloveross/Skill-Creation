---
name: evidence-grounded-credit-card-advisor
description: Provide a direct, evidence-grounded credit-card recommendation or comparison from product documents supplied in the current task. Use when a customer asks which card fits spending, rewards, international-use fees, purchase protection, possible credit limits, fees, or eligibility conditions.
---

# Evidence-Grounded Credit Card Advisor

## Purpose

Convert the customer's stated preferences and the current task's product documents into a useful, documented card recommendation. The supplied documents are the product catalog and factual source for the current request. A product comparison is informational: it does not require identity verification, an account lookup, an application, or a banking tool.

## Mandatory response behavior

When the customer has supplied enough criteria to compare cards, provide the completed comparison or recommendation in the **first substantive response**. The opening request is sufficient when it states the spending pattern and required benefits.

Do not give only a greeting. Do not ask the customer to supply product information. Do not say that current terms, product documentation, or a card catalog are unavailable when product documents are supplied in the task. Do not respond with a JSON status, defer the question, or transfer the customer simply because no tool is needed.

If documents establish at least one card satisfying all hard requirements, name it and state the documented terms immediately. A question about a nonessential preference, such as annual-fee tolerance, may be asked only after the initial recommendation is complete.

## Evidence and qualification rules

Use only the customer's request and the product documents supplied in the current task context.

1. Build a separate fact record for each card. Never combine benefits from different cards.
2. Treat missing evidence as unknown, not as a passing term.
3. A requirement for no foreign transaction fee requires a documented `0%` foreign transaction fee for that exact card.
4. A requirement for purchase protection requires documented purchase protection for that exact card. Include its window and claim cap, or its explicitly documented unlimited coverage.
5. A request for the *possibility* of a limit of at least a stated amount is met only when the card's documented approved, typical, standard, or maximum limit reaches that amount. It is not a promise: the exact limit is subject to underwriting and approval.
6. Preserve all material qualifications, including eligibility thresholds, premium-subscription requirements, invitation-only access, annual fees, merchant-category restrictions, policy terms, and exclusions.
7. Do not claim that a score threshold guarantees approval or that a possible credit limit is guaranteed.

## Decision method

1. Identify hard requirements (for example, `0%` foreign fee, purchase protection, and a minimum possible limit).
2. Identify preferences (for example, travel-heavy and otherwise-low everyday spending).
3. Extract each candidate's reward rate and scope, foreign fee, limit range, protection, fees, and access conditions from its own documents.
4. Exclude cards that fail, lack evidence for, or conditionally meet a hard requirement whose condition is not established for the customer.
5. Rank surviving cards by fit. For mixed everyday and travel spend, a documented flat reward on all eligible purchases is generally a strong fit because it rewards both travel and other eligible purchases without inventing travel categories.
6. Give a primary recommendation. Mention alternatives only when they independently meet every hard requirement, and place each alternative's material caveat in the same sentence or bullet.

## Required customer-facing answer

For every direct recommendation, include all of the following in readable prose:

- the exact card name and language such as “I recommend,” “best match,” or “a qualifying option”;
- the documented reward rate and scope, tied to the customer's everyday and/or travel spending;
- `0%` and “foreign transaction fee” (or “foreign fees”) when that is required;
- the exact phrase **purchase protection**, together with its documented number of days and per-claim cap or documented unlimited coverage;
- the documented limit range or ceiling that reaches the requested amount;
- an explicit statement that the requested limit is possible, but the exact approved limit is subject to underwriting and approval.

Use the product's qualifying language, such as “eligible purchases” or “subject to policy terms and exclusions,” where documented. Do not invent airline, lounge, insurance, category, rebate, or approval benefits.

## Recommended response shape

Use this concise structure after checking the documents:

1. **Recommendation:** identify the primary card as the best documented match.
2. **Spending fit:** give its documented rewards rate and scope and explain the relevance to the stated everyday/travel pattern.
3. **Required benefits:** state its `0%` foreign transaction fee and purchase-protection window and cap/coverage.
4. **Limit:** give the documented range or ceiling, explain why the requested limit is possible, and state the underwriting/approval qualification.
5. **Alternatives, if useful:** list only independently qualifying cards, with their access restrictions and any relevant tradeoffs clearly disclosed.

If no supplied card is documented to meet every hard requirement, say which requirement is failed or undocumented for each plausible option. Do not make an unsupported recommendation in that case.

## Runtime helpers

The helpers are optional support for deterministic checking and drafting. They do not retrieve product information, make approval decisions, or cause any banking action. Facts supplied to them must be transcribed from the current task's documents.

### `scripts/recommend_cards.py`

Reads one JSON object from stdin and emits one JSON object on stdout.

```json
{
  "requirements": {
    "max_foreign_transaction_fee_pct": 0,
    "min_possible_credit_limit": 100000,
    "purchase_protection_required": true,
    "primary_category": "travel",
    "everyday_spend_preference": true
  },
  "products": [
    {
      "name": "Exact name from current documents",
      "flat_cashback_pct": null,
      "travel_cashback_pct": null,
      "annual_fee": null,
      "foreign_transaction_fee_pct": null,
      "credit_limit_min": null,
      "credit_limit_max": null,
      "purchase_protection": {
        "available": null,
        "days": null,
        "max_per_claim": null,
        "unlimited": false
      },
      "eligibility_notes": [],
      "source_ids": []
    }
  ]
}
```

It returns per-requirement checks, qualifying candidates, an explainable ranking, and warnings for malformed or unsupported records.

```bash
python3 scripts/recommend_cards.py < candidates.json
```

### `scripts/render_recommendation.py`

Use only after a qualifying primary record has been extracted from the supplied documents. It rejects a primary card without documented `0%` foreign fees, purchase protection, or a sufficient documented credit-limit ceiling.

```json
{
  "primary_name": "Exact name from current documents",
  "customer_priorities": {
    "primary_category": "travel",
    "everyday_spend": true,
    "requested_limit": 100000
  },
  "products": [],
  "alternatives": []
}
```

```bash
python3 scripts/render_recommendation.py < recommendation.json
```

Use the rendered draft only after confirming that every supplied fact is supported by the same card's documents.

## Final send check

- The first substantive response contains a named recommendation or grounded qualifying comparison.
- The primary card itself, not another card, supports every cited hard-requirement fact.
- The response states the rewards rationale, `0%` foreign fee, purchase-protection details, and qualifying limit range/ceiling.
- It says the requested limit is possible rather than guaranteed and is subject to underwriting and approval.
- Every named alternative independently qualifies, and all material eligibility restrictions are disclosed.
- The response contains no unsupported inability claim, product-information refusal, account action, or transfer.
