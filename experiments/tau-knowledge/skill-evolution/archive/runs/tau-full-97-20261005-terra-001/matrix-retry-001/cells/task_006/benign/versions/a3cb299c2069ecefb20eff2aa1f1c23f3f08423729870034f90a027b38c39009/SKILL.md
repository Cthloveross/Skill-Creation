---
name: credit-card-constraint-matching
description: Evaluate published credit-card terms and eligibility prerequisites against a customer's stated card requirements. Use for product-fit questions involving credit score, subscription or invitation prerequisites, foreign transaction fees, minimum-payment percentages, and virtual-card management.
---

# Credit-card constraint matching

Use this Skill to identify cards that meet **all** of a customer's stated hard requirements while accurately separating product fit from an approval decision.

## Required inputs

Read the current customer request and the currently supplied product documents. Capture:

- Customer facts that are relevant to published eligibility requirements, such as credit score, subscription status, invitation status, and income.
- Every hard requirement the customer states, including numerical ceilings and required features.
- For each candidate card, only the terms explicitly published in the supplied sources:
  - minimum credit score;
  - whether a subscription is required;
  - whether the product is invitation-only;
  - foreign transaction fee percentage;
  - minimum-payment percentage and its stated balance basis;
  - virtual-card-management availability.

Do not infer an unavailable feature, a fee, or an eligibility condition from the card name, tier, or another card's document. Treat a missing fact as unknown rather than as a pass.

A stated income is relevant only when a supplied product document makes income an eligibility requirement. Do not invent an income threshold.

## Evaluation method

1. Convert percentages to numeric percentages, preserving their published meaning. A product at or below a requested maximum passes that constraint.
2. Evaluate eligibility separately from features:
   - A customer passes a published minimum credit-score condition only when their known score is at least that minimum. A stated minimum of zero means no score requirement.
   - A required subscription must be currently held; do not assume that the customer will obtain it.
   - An invitation-only product requires an invitation. A sufficient score alone does not satisfy that requirement.
3. Evaluate feature constraints:
   - Compare the published foreign transaction fee to the customer's maximum.
   - Compare the published minimum-payment percentage to the customer's maximum. Retain the document's balance basis (for example, outstanding balance) in the explanation; do not silently relabel it.
   - If virtual-card management is required, the source must explicitly say it is available.
4. A card is a match only if all applicable eligibility and feature checks pass. Any failed check makes it incompatible. Any required missing fact makes the result insufficient-information, not a match.
5. If there are multiple matches, present all matches or ask the customer for a preference that is not addressed by the published terms. Do not rank cards using unstated assumptions.

For repeatable comparisons, normalize the extracted facts into the script input described below and run `scripts/evaluate_card_fit.py`.

## Script interface

Run:

```sh
python3 scripts/evaluate_card_fit.py < request.json
```

The script accepts one JSON object on standard input and emits one JSON object on standard output. The request shape is:

```json
{
  "profile": {
    "credit_score": "number or null",
    "has_premium_subscription": "boolean or null",
    "invitation_received": "boolean or null"
  },
  "requirements": {
    "max_foreign_transaction_fee_pct": "number or null",
    "max_minimum_payment_pct": "number or null",
    "requires_virtual_card_management": "boolean"
  },
  "cards": [
    {
      "name": "string",
      "minimum_credit_score": "number or null",
      "premium_subscription_required": "boolean or null",
      "invitation_only": "boolean or null",
      "foreign_transaction_fee_pct": "number or null",
      "minimum_payment_pct": "number or null",
      "minimum_payment_basis": "string or null",
      "virtual_card_management": "boolean or null"
    }
  ]
}
```

Use JSON `null` for an absent or unconfirmed source fact. The script returns each card's `status` (`compatible`, `incompatible`, or `insufficient_information`) and the individual passed, failed, and unknown checks. Validate that the card names and values sent to the script were transcribed from the current sources before relying on its result. The script deliberately does not decide approval and does not apply for a product.

## Customer response

Respond directly and concisely:

1. State whether a card matches the customer's stated filters, and name each match.
2. Give the exact published facts that establish the match: eligibility prerequisite(s), foreign transaction fee, minimum-payment percentage and its published basis, and virtual-card-management availability.
3. Say that meeting the listed criteria does not guarantee approval; underwriting and the application process still apply.
4. If the customer wants to proceed, provide only source-supported next steps. For an online application, this commonly includes completing the application with the requested identity, personal, and financial information, reviewing disclosures, submitting it, and activating an approved card. Do not submit an application or claim an approval on the customer's behalf.
5. If no card matches, plainly say so and identify the blocking published requirements. Do not pretend that a near match fits.

Do not expose internal reasoning, fabricate a rate or benefit, or represent a card as suitable beyond the explicit filters the customer gave. No identity verification, account lookup, account change, or banking action is needed for a general product-fit answer.

A frustrated statement about taking business elsewhere is not by itself a request for a transfer. If, after an unavailable-offer explanation, the customer explicitly demands a human agent, use the normal transfer process with `customer_demands_after_unavailable_offer_refusal`. For an ordinary explicit request for a human without that context, use `customer_requests_human_no_specific_reason`.
