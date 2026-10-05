---
name: evidence-grounded-credit-card-advisor
description: Give a direct, documented recommendation or comparison of credit cards from the product materials supplied in the current task. Use when a customer asks which card fits spending patterns, rewards, foreign transaction fees, purchase protection, possible credit limits, fees, or eligibility requirements.
---

# Evidence-Grounded Credit Card Advisor

## Purpose

Turn the current task's supplied product documents and the customer's stated needs into useful card-selection advice. The product documents in the runtime context are the available catalog for this request. Treat them as usable evidence even if there is no search, account, application, or catalog tool.

## Immediate-answer rule

When the customer has already given enough criteria to compare products, give the recommendation in the first substantive reply.

Do **not** respond only with a greeting, repeat the request, ask the customer to provide product information, claim terms are unavailable, defer the comparison, or transfer the customer merely because a tool is unavailable. Public product comparison does not require identity verification, account lookup, application processing, or a banking action.

A follow-up question is appropriate only after a complete initial recommendation, and only if it would refine a non-required preference such as annual-fee tolerance.

## Evidence boundary

Use only:

1. the customer's stated requirements and preferences; and
2. product documents supplied in the current task context.

For every factual claim, keep the benefit attached to the same exact card. Do not combine one card's rewards with another card's limit or protection benefit. Do not infer terms from a product name, product tier, or similar card. A missing fact is **unknown**, not a pass.

State documented qualification limits accurately: an approved-limit range or ceiling at or above a requested amount establishes that amount as *possible*, never guaranteed. Actual approval and the exact limit depend on underwriting and approval.

## Decision method

1. **Extract hard requirements.** These may include a maximum foreign transaction fee, purchase protection, and a requested possible credit limit.
2. **Extract preferences.** Examples are everyday spending, travel-focused spending, cash-back preference, annual-fee sensitivity, and convenience benefits.
3. **Make a per-card record.** Record only documented rewards and scope, foreign transaction fee, approved-limit range, purchase-protection window and cap, annual fee, and eligibility/access restrictions.
4. **Test hard requirements literally.**
   - “No foreign transaction fees” requires a documented `0%` foreign transaction fee for that card.
   - “Possibility of at least $X” requires a documented standard, typical, approved, or maximum limit that reaches $X.
   - “Purchase protection” requires documented protection for that same card.
   - If a required term is conditional, disclose the condition. It does not qualify as unconditional unless the customer's conditions satisfy it.
5. **Rank only cards that pass every hard requirement.** For a customer who uses a card for both everyday purchases and travel, favor a documented flat all-eligible-purchases reward when it serves both spend types well. Do not invent travel categories or rates.
6. **Recommend directly.** Name the best documented fit and connect each stated requirement to that card's documented terms. Alternatives are optional and must be fully qualifying.

## Required customer-facing content

For a qualifying recommendation, the response must include all of these items in clear prose:

- the exact card name and an explicit recommendation, best-match statement, or option framing;
- the documented rewards rate and reward scope, connected to the customer's everyday and/or travel spending;
- the documented `0%` foreign transaction fee when no foreign fee is required;
- the words **purchase protection**, plus its documented time window and per-claim cap, or explicitly documented unlimited coverage;
- the documented credit-limit range or ceiling showing why the requested amount is possible; and
- a clear statement that the exact limit is subject to underwriting and approval and is not guaranteed.

Use wording such as “eligible purchases” when that is a condition in the documents. Preserve qualifications such as policy terms, exclusions, merchant-category conditions, subscriptions, invitation-only access, score thresholds, and annual fees.

## Response pattern

Use this structure after verifying the facts:

1. **Recommendation:** “I recommend **[exact card name]** as the best match for your needs.”
2. **Spend fit:** State **[documented reward rate]** on **[documented reward scope]**, and explain why that fits the stated everyday and travel pattern.
3. **Hard requirements:** State the `0%` foreign transaction fee and the exact purchase-protection period and cap/coverage.
4. **Limit note:** State **[documented range or ceiling]**, say the customer's requested limit is possible within it, and say it remains subject to underwriting and approval.
5. **Optional alternatives:** Give only cards that independently pass every hard requirement. Put each material restriction immediately beside that alternative.

Do not make a recommendation if no card is documented to pass every hard requirement. Instead, identify the specific unmet or undocumented requirement per plausible card and ask whether the customer wants to relax it.

## Known restriction handling

A card may still be a qualifying alternative when it meets every requested product term but has an access condition. State the condition prominently rather than omitting it. Examples include a premium subscription requirement, invitation-only status, score consideration threshold, annual fee, or a narrower reward scope.

Do not call a card qualifying when a condition required for a requested feature is not established as met. Do not represent an eligibility threshold as an approval guarantee.

## Optional deterministic helper

Use `scripts/recommend_cards.py` when facts have been transcribed into structured records. It reads one JSON object from stdin and emits one JSON object on stdout.

Input schema:

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
      "name": "Exact name from the supplied documents",
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

Use JSON numeric values for percentages and money amounts; use `null` for unknown values. The helper reports each hard-requirement result, qualifying cards, ranking, and warnings. It does not make approval decisions or retrieve facts.

Runnable call:

```bash
python3 scripts/recommend_cards.py < candidates.json
```

Use `scripts/render_recommendation.py` only after extracting an evidence-supported record for a qualifying primary card. It produces a customer-facing draft and refuses a primary card that lacks a required documented term.

```bash
python3 scripts/render_recommendation.py < recommendation.json
```

If scripts are not needed or cannot be run, perform the same checks manually and still provide the direct recommendation.

## Final check before sending

- A named primary card passes every hard requirement using its own documented facts.
- The answer contains its rewards rationale, `0%` foreign-fee term, purchase-protection terms, and limit range/ceiling.
- The requested credit limit is described as possible, subject to underwriting and approval, never promised.
- Every named alternative independently passes the hard requirements.
- Each alternative's material access restriction, fee, reward limitation, or lower protection cap is disclosed.
- No unsupported claim of missing product information, account action, application result, or transfer appears in the response.
