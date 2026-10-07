---
name: credit-card-requirement-matcher
description: Produce an evidence-grounded credit-card recommendation or comparison from product documents and a customer's stated spending priorities and hard requirements. Use for questions about rewards, foreign transaction fees, purchase protection, possible credit limits, fees, and eligibility restrictions.
---

# Credit Card Requirement Matcher

Use the product documents supplied in the current task context as the available catalog. A document included in the task is current usable product information for this request, even if no separate search, file, or catalog tool is available.

## Core behavior

For a customer asking which card meets stated criteria, provide the recommendation or comparison directly in the same response. Do not merely greet, repeat the request, ask for product documentation, state that the catalog is unavailable, or transfer the customer when supplied product documents establish relevant terms.

Do not require an account lookup, identity verification, application, or tool call to compare publicly supplied product terms. These actions are not needed for product advice.

If the opening message already states the customer’s spending pattern and requirements, treat it as sufficient to make a documented initial recommendation. A follow-up question is optional only after giving a useful answer.

## Inputs and evidence boundaries

At runtime, extract facts from:

1. the customer's explicit requirements and preferences; and
2. the product documents supplied with the current task.

Keep every fact attached to its exact product. Do not combine a limit from one card, a protection benefit from another, or similarly named consumer and business products. Do not infer a benefit when the documentation is silent. When documents for the same product conflict materially, disclose the conflict rather than asserting either value as certain.

The source documents are the authority for card terms. Exact approval limits, rewards eligibility, coverage, and availability remain subject to the documented terms.

## Decision procedure

1. **Identify hard requirements.** Examples include a maximum foreign transaction fee, required purchase protection, and a requested possible credit limit.
2. **Identify preferences.** These include everyday versus category-based spend, travel-led spend, annual-fee sensitivity, and convenience benefits.
3. **Build a record per plausible product.** Capture the reward rate and scope, foreign transaction fee, limit range, purchase-protection window and cap, annual fee, eligibility restrictions, and document IDs.
4. **Test hard requirements literally.**
   - “No foreign transaction fee” passes only with a documented 0% foreign transaction fee.
   - “Possibility of at least $X” passes only where the documented approved/standard range or ceiling reaches at least $X. This means the limit is possible, never guaranteed.
   - “Purchase protection” passes only when documented for that same product. Preserve stated days, caps, exclusions, and eligibility language.
   - Missing information is unknown, not a pass.
5. **Rank qualifying products.** A product must pass every hard requirement before it can be described as qualifying. For mixed everyday and travel-led spending, favor a documented flat reward on all eligible purchases when it is stronger than or comparable to a narrow travel-only rate. Keep material fees and access barriers visible.
6. **Give direct advice.** Name a primary qualified product and explain why it fits. Optionally compare other qualified products, including their material caveats.

## Mandatory response content

The primary recommendation must state all of the following in a connected customer-facing answer:

- the exact product name and an explicit recommendation, best-match statement, or clear option framing;
- the documented rewards rate and its scope, tied to the customer’s everyday and/or travel spending;
- the documented **0% foreign transaction fee** when that is the qualifying term;
- **purchase protection** and its documented time window plus per-claim cap or explicitly documented unlimited coverage;
- the documented credit-limit range or ceiling that makes the requested limit possible; and
- that the exact credit limit is subject to underwriting and approval and is not guaranteed.

Use “eligible purchases” where the documentation uses that limitation. Do not hide required features in a generic benefits list. Do not promise approval, a particular initial limit, or coverage beyond the stated policy terms.

A reliable answer structure is:

1. **Recommendation:** name the primary card and its reward rationale for the stated spend.
2. **Requirement match:** foreign-fee term, protection terms, and documented limit range.
3. **Approval note:** explain that the desired limit is possible within that range, subject to underwriting and approval.
4. **Alternatives, if useful:** list only fully qualifying products and put each eligibility or access constraint beside it.

For alternatives, disclose material constraints such as a premium subscription requirement, invitation-only status, score threshold, annual fee, lower reward rate, or lower protection cap. If no product passes every hard requirement, say which condition fails or is undocumented; do not force a recommendation.

## Structured helper: qualify and rank

When structured facts are useful, run `scripts/recommend_cards.py` with JSON on stdin:

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

`null` means the supplied documentation does not establish the field. Currency amounts are plain numbers. Set `unlimited` to `true` only where the source explicitly says so. `source_ids` identify the documents used for the record.

Runnable call:

```bash
python3 scripts/recommend_cards.py < candidates.json
```

The script emits qualified and non-qualified candidates, a deterministic recommendation rank, per-requirement results, and warnings. It does not make approval decisions.

## Structured helper: render the answer

After selecting a qualified primary card, `scripts/render_recommendation.py` can generate a complete customer-facing draft from the same documented records:

```json
{
  "primary_name": "Exact qualified product name",
  "customer_priorities": {
    "primary_category": "travel",
    "everyday_spend": true,
    "requested_limit": 100000
  },
  "products": ["Product records in the qualification schema"],
  "alternatives": ["Optional exact names of qualified alternatives"]
}
```

Runnable call:

```bash
python3 scripts/render_recommendation.py < recommendation_input.json
```

The renderer refuses a primary record that does not document the required foreign-fee, purchase-protection, or requested-limit conditions. If scripts cannot be run, perform the identical evidence check manually and still answer the customer directly.

## Final validation

Before responding, confirm that:

- each hard requirement is marked pass, fail, or unknown;
- the named primary product passes every hard requirement using facts from that product only;
- the response includes its reward rationale, 0% foreign-fee term, purchase-protection terms, and credit-limit range or ceiling;
- the requested limit is described as possible subject to approval/underwriting, never assured;
- every alternative called qualifying also passes all hard requirements;
- material eligibility barriers, fees, caps, and exclusions are disclosed beside alternatives; and
- no account action, application, credit decision, or transfer was attempted merely to provide product information.
