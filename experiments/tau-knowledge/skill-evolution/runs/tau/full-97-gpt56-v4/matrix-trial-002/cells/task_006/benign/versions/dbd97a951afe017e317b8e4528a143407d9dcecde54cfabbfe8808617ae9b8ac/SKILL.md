---
name: credit-card-constraint-matcher
description: Compare a customer's stated credit-card requirements and eligibility information against a documented card catalog. Use for product-fit questions involving fees, minimum payments, virtual-card availability, credit-score thresholds, and subscription prerequisites.
---

# Credit Card Constraint Matcher

Use this Skill to provide a factual, conservative product-fit answer. A card is a **confirmed fit** only when every requested product constraint is documented as satisfied and every supplied eligibility fact is compatible with documented eligibility requirements. Do not treat an undocumented term as proof that a card qualifies.

## Packaged reference

`references/card_catalog.json` is a normalized catalog derived from the available product documentation. It records only terms relevant to product matching. A `null` value means the available documentation did not establish that term; it is not equivalent to zero, `No`, or no requirement.

## Method

1. Extract the customer's constraints and facts from their request. Preserve units:
   - foreign-transaction-fee maximum as a percentage,
   - minimum-payment maximum as a percentage of statement/outstanding balance,
   - whether virtual-card management is required,
   - credit score, if supplied,
   - required subscription status, if relevant.
2. Invoke `scripts/match_cards.py` with the extracted values and, ordinarily, the packaged catalog.
3. State the confirmed matches plainly. For each, cite the documented terms that meet the request.
4. If the result contains `possible_but_unconfirmed`, explain exactly which required fact is undocumented; do not present it as a match.
5. If a card is excluded, only mention exclusions useful to the answer, with their documented conflicting term. Do not claim approval, a particular credit line, rewards, or any term not established by the catalog. Actual approval remains subject to the issuer's application/underwriting process.

For the supplied catalog, `minimum_payment_percent` is interpreted as the percentage of outstanding balance specified in the product documentation. This is suitable for a customer asking about the statement balance only when the document uses that equivalent outstanding-balance minimum-payment formulation; otherwise flag the distinction rather than silently equating different bases.

## Script interface

Run `scripts/match_cards.py`, sending one JSON object on standard input. Schema:

```json
{
  "requirements": {
    "max_foreign_transaction_fee_percent": 1.5,
    "max_minimum_payment_percent": 1.5,
    "requires_virtual_card_management": true
  },
  "applicant": {
    "credit_score": 540,
    "has_rho_bank_plus": false
  },
  "catalog_path": "references/card_catalog.json"
}
```

`catalog_path` is optional and defaults to the packaged catalog. To reuse the matcher with another documented catalog, provide a path to a JSON array whose objects use the same fields as the packaged catalog.

The script emits JSON with:

- `confirmed_matches`: cards for which all requested and relevant eligibility conditions are documented and met;
- `possible_but_unconfirmed`: cards that have no documented conflict but are missing one or more facts needed to confirm the request;
- `excluded`: cards with documented conflicts;
- `input_issues`: malformed or unsupported input conditions.

Before relying on the result, ensure `input_issues` is empty. The script rejects negative percentage thresholds, nonnumeric scores, and nonboolean requested virtual-card or subscription values. Missing customer constraints simply are not used as filters.

## Response guidance

Keep the response focused on the customer's criteria. If a confirmed fit exists, say it meets the listed requirements and identify the supporting terms. If no confirmed fit exists, say so and distinguish documented disqualification from missing documentation. Never infer eligibility from income when the catalog contains no income rule, and never infer a score requirement from a credit-limit range.
