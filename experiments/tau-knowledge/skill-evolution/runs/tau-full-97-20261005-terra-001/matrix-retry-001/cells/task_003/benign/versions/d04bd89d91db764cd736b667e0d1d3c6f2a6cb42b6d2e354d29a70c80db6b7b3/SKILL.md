---
name: credit-card-requirement-matcher
description: Compare documented credit-card offerings against a customer's hard requirements and spending priorities. Use when recommending one or more cards from supplied product documentation, especially for foreign transaction fees, purchase protection, potential credit limits, rewards, fees, and eligibility constraints.
---

# Credit Card Requirement Matcher

Use this Skill to make an evidence-grounded card recommendation without treating underwriting outcomes, coverage exclusions, or invitation status as guarantees.

## Inputs

At runtime, collect:

1. The customer's stated hard requirements and preferences.
2. Product facts from the supplied product documents only. Preserve the document ID for every material fact.
3. A structured JSON candidate list following the schema accepted by `scripts/recommend_cards.py`.

Do not invent unavailable product terms. Do not use one product's terms for another product, including similarly named consumer and business products. If documents conflict, describe the conflict, cite both sources, and do not claim the disputed value is certain.

## Method

1. **Separate hard requirements from preferences.**
   - Hard requirements are explicit constraints such as no foreign transaction fee, purchase protection, or a possible credit limit at least a stated amount.
   - Preferences include primary spending categories, low spending outside those categories, annual-fee tolerance, and desired ancillary benefits.
2. **Extract comparable facts.** For each product, capture its reward rate and scope, annual fee, foreign-transaction fee, maximum documented approved-limit range, purchase-protection availability/window/cap, eligibility restrictions, and evidence IDs.
3. **Evaluate literal fit.**
   - “No foreign transaction fees” requires a documented 0% fee.
   - “Possibility of at least $X limit” requires the documented upper end of the approved/standard range to be at least `$X`; say approval and the actual line remain underwriting-dependent.
   - “Purchase protection” requires a documented protection benefit. State its documented window, cap, and policy/exclusion qualification when available.
   - Treat unknown facts as not established, rather than assuming they qualify.
4. **Rank qualifying cards.** Prefer a reward structure that matches the stated spending pattern. For broad everyday spending, a documented flat all-purchases rate generally fits better than a narrow category rate; for travel-led spending, give documented travel-specific earnings substantial weight. Consider fees and meaningful eligibility barriers as tradeoffs, not as silent disqualifiers unless the customer made them hard requirements.
5. **Run the helper.** Supply the extracted facts and requirements to the helper. It performs deterministic eligibility filtering and a transparent preference ranking; it does not replace document review.
6. **Respond clearly.** Lead with the best-supported option, then name viable alternatives and their tradeoffs. Cite document IDs inline or in a compact evidence list. Explain material limitations: actual approval/limit is not guaranteed; rewards require eligible/posted purchases where documented; and protection is subject to terms/exclusions.

## Helper interface

Run `scripts/recommend_cards.py` with a JSON object on stdin:

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

`null` means the supplied documentation does not establish that fact. `max_per_claim` may be a number or `null`; set `unlimited: true` only where documentation explicitly says so. `source_ids` is an array of relevant document IDs.

The script emits JSON with `qualified`, `not_qualified`, and `warnings`. A product is qualified only when every supplied hard requirement is established and met. Review the returned `reasons`, `tradeoffs`, and source IDs before drafting the customer-facing answer.

Example runnable invocation:

```bash
python3 scripts/recommend_cards.py < candidates.json
```

## Output validation

Before delivering a recommendation, ensure that:

- Every stated hard requirement has an explicit pass/fail/unknown determination.
- The primary recommendation is in `qualified` and its cited sources support each required feature.
- Any alternative is either qualified or clearly labeled as not meeting a particular requirement.
- Dollar limits are described as a documented possible range/ceiling, never as an approved limit for this customer.
- Eligibility constraints, annual fees, reward scope, and protection limits are not omitted when material.
- No account lookup, application, approval, or financial transaction is attempted; this Skill provides product comparison only.

If no card has all required facts or meets all hard requirements, say so and identify the missing or failing criterion rather than forcing a recommendation.
