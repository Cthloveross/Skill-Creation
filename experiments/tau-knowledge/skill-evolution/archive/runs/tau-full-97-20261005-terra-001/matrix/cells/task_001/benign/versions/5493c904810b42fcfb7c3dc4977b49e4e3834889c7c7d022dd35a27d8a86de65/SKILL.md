---
name: constrained-cash-back-card-recommender
description: Recommend a personal cash-back credit card from product materials supplied in the current task when a customer has spending, annual-fee, and potentially incomplete eligibility constraints. Use for informational card comparisons only; do not use to submit an application, alter an account, or promise approval.
---

# Constrained Cash-Back Card Recommender

## Core rule

Treat the current task's supplied card documents, evidence, and conversation as the available product-information source. If they document a card's reward rate, permanent fee, and relevant requirements, use them. **Do not say the catalog or terms are unavailable, ask the customer to provide documents already supplied, or transfer solely because a score or another approval fact is unknown.**

A missing eligibility fact changes a supported recommendation from definite to conditional. It does not prevent an informational comparison.

## Decision procedure

1. Read the full conversation, clarifications, and every relevant supplied card document. Product facts may be split between an eligibility document, a rewards document, and a fee document.
2. Identify the customer's personal spending pattern. Exclude purchases that the customer says are charged to an employer or corporate card.
3. Apply hard constraints before comparing rewards:
   - A stated maximum annual fee applies to the **permanent** annual fee.
   - A temporary introductory waiver does not make a card permanently no-fee.
   - Exclude a card if its documented permanent fee exceeds the ceiling, or if a required permanent fee is not documented.
   - Exclude invitation-only products unless an invitation is confirmed.
4. For general, broad, or everyday shopping, compare each remaining card's documented all-purchases/default rate. Do not substitute a travel, software, or other category bonus unless the customer's personal spending is documented to qualify for it.
5. Select the highest documented applicable reward rate among cards satisfying known hard constraints. A card with unresolved eligibility may be selected **conditionally**.
6. State the recommendation in the same response, including its rate, rate scope, annual fee, requirements, and approval limitation. Briefly compare material alternatives when that explains the choice.

## Eligibility handling

Classify each requirement from the current conversation only:

| Customer fact | Treatment |
| --- | --- |
| Explicitly has an active required membership/subscription | Confirmed, unless another current statement materially contradicts it. |
| Explicitly does not have a required membership/subscription | Not currently met; do not describe the card as currently available. |
| Membership is unknown, ambiguous, or contradicted across supplied inputs | Unresolved; recommend only conditionally and ask the customer to verify that it is active and qualifies. |
| Credit score is unknown or unavailable | Unresolved; disclose the documented minimum score and make eligibility conditional. |
| Known score is below the documented minimum | Exclude the card. |
| Known score meets a listed minimum | Requirement is met for comparison purposes, but approval remains subject to underwriting. |

Do not resolve conflicting statements by silently choosing one. For example, where a customer reports an employer-provided subscription but another supplied turn indicates uncertainty about a required membership, say that the employer-provided subscription must be confirmed as active and qualifying. Likewise, never infer a credit score from income, employment, or account relationship.

## Required customer response

Lead with a concrete recommendation rather than a description of the search. For a conditional result, use wording with this structure, filling every fact from the supplied materials:

> **[Card name] is the best documented fit, conditionally.** It earns **[rate]% cash back [documented scope]** and has a **$[permanent fee] annual fee**, so it [does/does not] meet your fee preference. [State any confirmed prerequisite.] To qualify, please confirm [each unresolved subscription or other prerequisite] and that you meet the **[minimum] credit-score requirement**. This is a comparison, not an approval; final eligibility and approval are subject to underwriting.

When useful, add a short, supported comparison, such as: lower no-fee alternatives offer a lower default rate for general purchases; a higher category rate does not apply to the customer's stated spending; or a higher-rate product has a permanent annual fee and therefore fails the fee constraint. Do not use an unrelated bonus category to justify the recommendation.

The final answer must explicitly include:

1. the recommended card name;
2. the applicable cash-back percentage and its scope;
3. the permanent annual fee and connection to the customer's fee preference;
4. required subscription or membership information, including whether it is confirmed or needs verification;
5. a disclosed minimum credit score when relevant; and
6. conditional/underwriting language whenever any requirement or approval is unresolved.

Never state or imply that the customer is approved, definitely eligible, or will receive a particular credit limit.

## Deterministic ranking helper

Use `scripts/rank_cards.py` after extracting supported facts from the supplied materials. The script makes no account change and does not decide underwriting. It reads one JSON object from stdin and writes one JSON object to stdout.

### Input schema

```json
{
  "preferences": {
    "max_annual_fee": 0,
    "categories": ["shopping"],
    "category_weights": {"shopping": 1}
  },
  "profile": {
    "credit_score": null,
    "requirements": {
      "subscription_key": null
    }
  },
  "cards": [
    {
      "name": "string",
      "annual_fee": 0,
      "default_cash_back_percent": 0,
      "category_cash_back_percent": {"shopping": 0},
      "rate_scope": "on all purchases",
      "requirements": [
        {
          "key": "subscription_key",
          "type": "required_boolean",
          "value": true,
          "label": "subscription name"
        },
        {
          "key": "minimum_credit_score",
          "profile_key": "credit_score",
          "type": "minimum_number",
          "value": 0,
          "label": "minimum credit score"
        }
      ],
      "invitation_only": false,
      "source_titles": ["source title"]
    }
  ]
}
```

Use numbers for fees and percentage values (for example, `2.5`, not `0.025`). Include a category-specific rate only when its supplied document establishes that rate for the named category. Use `true` only for a confirmed requirement, `false` when it is known not to be met, and `null` for unknown, ambiguous, or conflicting information.

### Output schema and validation

The script returns:

- `errors`: input/schema issues;
- `ranked_candidates`: non-excluded cards ordered by applicable rate;
- `excluded`: cards that fail a known hard constraint or lack a needed comparable term;
- `recommendation`: the best eligible or conditional candidate, or `null`;
- `customer_message`: a factual draft; and
- `interpretation`: the meaning of a conditional result.

Before using the result, check that `errors` is empty, `recommendation` is not `null`, and its `eligibility_status` is `eligible` or `conditional`. Copy the factual terms from `customer_message`, then ensure the final customer response addresses any ambiguity present in the conversation. If no supported recommendation exists, explain the specific missing or incompatible term; do not fabricate a product fact.

### Runnable call example

The following is only a schema demonstration; populate all values from the current task's supplied documents and conversation:

```json
{"preferences":{"max_annual_fee":0,"categories":["shopping"],"category_weights":{"shopping":1}},"profile":{"credit_score":null,"requirements":{"subscription_key":null}},"cards":[{"name":"Documented card","annual_fee":0,"default_cash_back_percent":1,"category_cash_back_percent":{},"rate_scope":"on all purchases","requirements":[],"invitation_only":false,"source_titles":["Supplied terms"]}]}
```

## Final checklist

- I used supplied product materials rather than claiming they are missing.
- I used permanent, not promotional, annual fees.
- I optimized the rate applicable to the customer's personal spending.
- I did not use employer-paid corporate spending or an unrelated category bonus.
- I named the best supported card and stated rate, scope, and fee.
- I disclosed every relevant unresolved requirement, especially a minimum score.
- I handled contradictory membership evidence conditionally.
- I did not promise approval or transfer a customer merely because underwriting information is unknown.
