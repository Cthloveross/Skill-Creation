---
name: credit-card-requirement-matcher
description: Compare documented credit-card offerings against a customer's stated requirements and spending priorities. Use for evidence-grounded card recommendations involving foreign transaction fees, purchase protection, possible credit limits, rewards, fees, and eligibility constraints.
---

# Credit Card Requirement Matcher

Use the product documentation supplied in the current task context as the card catalog. When those documents establish one or more matches, answer the customer directly with a grounded recommendation or comparison in the same response.

This is a product-information request: do **not** say the catalog or product information is unavailable when supplied documents contain relevant product terms. Do not request an account lookup, verify identity, apply for a card, or transfer the customer merely to compare products.

## Inputs

At runtime, collect:

1. The customer's explicit hard requirements and stated preferences.
2. Product facts from the supplied current documentation only, retaining the supporting document ID for every material fact.
3. A structured candidate list using the schema accepted by `scripts/recommend_cards.py`.

Do not combine facts from different products, including similarly named consumer and business cards. A benefit or limit applies only to the product documented with that benefit or limit. If documents for the *same product* materially conflict, identify the conflict and do not state either conflicting value as certain.

## Required workflow

1. **Separate hard requirements from preferences.**
   - Hard requirements are explicit conditions, such as no foreign transaction fee, purchase protection, or the possibility of a stated credit limit.
   - Preferences include the principal spending category, lower spending outside it, annual-fee sensitivity, and ancillary benefits.
2. **Build a fact record for each plausible product.** Record rewards and their scope, annual fee, foreign-transaction fee, upper credit-limit range, purchase-protection availability/window/cap, eligibility constraints, and source IDs.
3. **Evaluate each hard requirement literally.**
   - “No foreign transaction fee” requires a documented 0% foreign transaction fee.
   - “Possibility of at least $X credit limit” requires a documented standard or approved range with an upper bound of at least $X. It establishes only that the requested limit is possible, not that it will be approved.
   - “Purchase protection” requires a documented protection benefit. Preserve its documented time window, cap, and any stated terms or exclusions.
   - Unknown information is not a pass.
4. **Rank only products passing every hard requirement.** For everyday spending, favor a documented flat reward rate on all eligible purchases over a narrow-category rate. For travel-led spending, also consider a documented travel rate. Keep annual fees and access restrictions visible.
5. **Respond, rather than merely reporting analysis.** Name one qualified card as the recommendation. The answer must be useful even if no follow-up is received. Optionally list other qualified products with caveats.
6. **Use the helpers when structured facts are available.** `recommend_cards.py` performs deterministic qualification and ranking. `render_recommendation.py` turns documented candidate facts into a complete customer-facing draft. Review source documents before sending either result.

## Mandatory customer-facing recommendation

For a qualifying primary recommendation, communicate all of the following clearly and together:

- the exact card name and an explicit recommendation such as “I recommend” or “best match”;
- the documented rewards rate and scope, connected to the customer's everyday and/or travel-led spending pattern;
- its **0% foreign transaction fee** when that is the documented qualifying term;
- that it includes **purchase protection**, with the documented number of days and per-claim cap or documented unlimited coverage;
- the documented credit-limit range or ceiling that makes the requested limit possible; and
- that the exact initial limit and approval are determined by underwriting and are not guaranteed.

Use “eligible purchases” where the source uses that limitation. Preserve stated policy terms and exclusions for protection. Do not bury any requested feature in a generic benefits list.

For an alternative, call it qualifying only if every hard requirement is documented as met. State material constraints next to that alternative, including required subscription, invitation-only access, score threshold, annual fee, weaker rewards, or weaker protection. If no card passes all hard requirements, say which requirements lack documented support or fail; do not force a recommendation.

A reliable response layout is:

1. **Recommendation:** card name plus reward rationale for the stated spend.
2. **Why it meets your requirements:** 0% foreign fee, purchase-protection terms, and the limit range/ceiling.
3. **Approval note:** requested limit is possible from the documented range but subject to underwriting.
4. **Alternatives (optional):** only fully qualifying cards, each with meaningful caveats.

## Helper: qualification and ranking

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
      "name": "Exact product name from current documentation",
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

`null` means that current documentation does not establish the field. Numeric currency amounts are unformatted numbers. Set `unlimited` to `true` only if the document explicitly says that coverage is unlimited. `source_ids` must identify sources for the entered facts.

Example invocation:

```bash
python3 scripts/recommend_cards.py < candidates.json
```

The script emits `recommended_name`, qualified candidates with per-requirement checks, non-qualified candidates, and warnings. A rank is an aid, not an approval decision.

## Helper: customer-facing draft

After selecting the primary qualified product, run `scripts/render_recommendation.py` when a concise complete draft is useful. It receives the same product facts plus the selected primary name and emits `message` and validation flags.

```json
{
  "primary_name": "Exact qualified product name",
  "customer_priorities": {
    "primary_category": "travel",
    "everyday_spend": true,
    "requested_limit": 100000
  },
  "products": ["Use the product objects from the qualification schema"],
  "alternatives": ["Optional exact names of other qualified products"]
}
```

Example invocation:

```bash
python3 scripts/render_recommendation.py < recommendation_input.json
```

Only provide products whose facts were extracted from current documentation. The renderer rejects a primary product whose supplied facts do not establish the mandatory fee, protection, and requested-limit conditions.

## Output validation

Before responding, verify that:

- every explicit hard requirement has a pass, fail, or unknown determination;
- the named primary card is qualified and every material claim is supported by its product's source IDs;
- the response includes the card name, recommendation, reward rationale, 0% foreign-fee term, purchase-protection terms, and a qualifying credit-limit range or ceiling;
- the answer says the requested limit is possible, subject to approval/underwriting, rather than guaranteed;
- material eligibility barriers, fees, coverage caps, and exclusions are disclosed for any alternatives discussed;
- no facts were borrowed from another product or inferred from an absent term; and
- no account lookup, application, approval, or banking transaction was attempted.
