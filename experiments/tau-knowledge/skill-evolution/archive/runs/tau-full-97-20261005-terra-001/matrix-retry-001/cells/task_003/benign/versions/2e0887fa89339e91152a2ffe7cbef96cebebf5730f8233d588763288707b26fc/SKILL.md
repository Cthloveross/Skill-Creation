---
name: credit-card-requirement-matcher
description: Compare documented credit-card offerings against a customer's stated requirements and spending priorities. Use for evidence-grounded card recommendations involving foreign transaction fees, purchase protection, possible credit limits, rewards, fees, and eligibility constraints.
---

# Credit Card Requirement Matcher

Use the product documentation supplied in the current task context as the card catalog. Provide a direct recommendation when the documentation establishes a match. Do not say product information is unavailable, request an account lookup, verify identity, apply for a card, or transfer the customer merely because this is a product-comparison request.

## Inputs

At runtime, collect:

1. The customer's explicit hard requirements and their preferences.
2. Product facts from the supplied documentation only, retaining the supporting document ID for every material claim.
3. A structured candidate list using the schema accepted by `scripts/recommend_cards.py`.

Do not combine facts from different products, including similarly named consumer and business cards. If the documents conflict about a material term, state the conflict and avoid presenting either value as certain.

## Method

1. **Separate requirements from preferences.**
   - Hard requirements are explicit conditions, such as a maximum foreign-transaction fee, purchase protection, or the possibility of a stated credit limit.
   - Preferences include the primary spending category, spending outside that category, annual-fee sensitivity, and ancillary benefits.
2. **Extract comparable facts per product.** Record the rewards rate and scope, annual fee, foreign-transaction fee, documented upper credit-limit range, purchase-protection availability/window/cap, eligibility constraints, and source IDs.
3. **Evaluate literal hard-requirement fit.**
   - “No foreign transaction fee” requires a documented 0% foreign transaction fee.
   - “Possibility of at least $X credit limit” requires a documented approved or standard range whose upper bound is at least $X. It is not a promise that the customer will receive that limit.
   - “Purchase protection” requires a documented protection benefit. Give the documented benefit window and coverage cap, and note policy terms/exclusions when stated.
   - Treat unknown facts as unestablished, not as qualifying.
4. **Rank cards that meet all hard requirements.** For an everyday-spend request, favor a documented flat all-eligible-purchases reward rate over a narrow category rate. For travel-led spending, consider a documented travel reward rate as well. Treat fees and eligibility barriers as visible tradeoffs unless the customer made them hard disqualifiers.
5. **Use the helper when structured facts are available.** It deterministically checks hard requirements and ranks qualified candidates. It does not replace review of the source documents.
6. **Give useful advice in the same response.** Lead with one documented primary recommendation; then optionally provide qualifying alternatives with their significant tradeoffs.

## Required customer-facing content

For the primary recommendation, state all of the following when documented and relevant to the request:

- the card name and an explicit recommendation (for example, “best match” or “I recommend”);
- why its rewards structure fits both the customer's primary category and everyday spending;
- its foreign transaction fee, explicitly including 0% where applicable;
- that it includes purchase protection, along with its documented days and per-claim cap or documented unlimited coverage;
- the documented credit-limit range or ceiling that makes the requested limit possible; and
- that the exact credit limit and approval remain underwriting-dependent.

Use precise language: rewards apply only to eligible purchases when that is what the material says, and protection remains subject to applicable terms and exclusions. Do not bury a requirement match in a generic list of benefits.

For alternatives, only call a card a qualifying alternative if every hard requirement is documented as met. Clearly disclose material restrictions such as a required subscription, invitation-only status, score threshold, annual fee, or weaker rewards. If no product meets every hard requirement, explain the specific missing or failing feature rather than forcing a recommendation.

A compact response structure is:

1. **Recommendation:** name the best-supported qualifying product and connect its rewards to the stated spending pattern.
2. **Hard-requirement check:** fee, purchase protection, and possible-limit evidence.
3. **Alternatives:** qualifying options and their material caveats, if useful.
4. **Important limitation:** actual approval and credit line are not guaranteed.

Cite supporting document IDs inline or in a short evidence list where the channel supports citations.

## Helper interface

Run `scripts/recommend_cards.py` with JSON on stdin:

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
      "name": "Product name from documentation",
      "flat_cashback_pct": 0,
      "travel_cashback_pct": null,
      "annual_fee": null,
      "foreign_transaction_fee_pct": null,
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

`null` means the documentation does not establish that field. `max_per_claim` may be a number or `null`; use `unlimited: true` only when the documentation explicitly says coverage is unlimited. `source_ids` must identify the material supporting the entered facts.

Example runnable invocation:

```bash
python3 scripts/recommend_cards.py < candidates.json
```

The script emits JSON with `recommended_name`, `qualified`, `not_qualified`, and `warnings`. Review the returned requirement checks and the original documentation before drafting the final response. A ranking is a transparent aid, not an approval decision.

## Output validation

Before responding, check that:

- each explicit hard requirement has a pass, fail, or unknown determination;
- the named primary recommendation is qualified and each claimed feature is supported by its source IDs;
- the response explicitly addresses the requested fee, protection, and possible credit limit;
- the primary recommendation's reward explanation relates to the customer's stated spending pattern;
- credit-limit language says “possible” or describes a documented range and never guarantees approval;
- eligibility constraints, material fees, protection caps, and exclusions are not omitted; and
- no account lookup, application, approval, or banking transaction is attempted.
