---
name: credit-card-constraint-matching
description: Evaluate supplied credit-card product documents against a customer's stated eligibility and card-feature constraints. Use for evidence-grounded card-fit questions involving credit score, subscription or invitation prerequisites, foreign transaction fees, minimum payments, and virtual-card management.
---

# Credit-card constraint matching

Use this Skill to identify products that meet every stated hard requirement using the **currently supplied product documents**. It provides a product-fit recommendation only; it does not decide underwriting, submit an application, access an account, or make any bank-side change.

## Gather evidence

Read the customer request and all supplied product documents before answering. Extract the customer's relevant facts and every hard requirement. For each candidate card, record only facts explicitly supported by the documents:

- minimum credit score to apply;
- subscription requirement;
- invitation-only requirement;
- foreign transaction fee;
- minimum-payment percentage and its stated basis;
- virtual-card-management availability.

A customer's income is relevant only if a supplied document states an income criterion. Do not invent an income threshold or use income to guarantee approval.

Do not say terms are unavailable when the supplied documents contain the facts needed to evaluate the requested constraints. Do not infer a feature, fee, or prerequisite from a card name, card tier, or another product's document.

## Evaluate constraints

1. Treat numerical maximums as inclusive: a documented percentage at or below the requested maximum passes.
2. Evaluate documented eligibility separately from feature fit:
   - A score passes a published minimum when the known score is at least that minimum. A published minimum of `0` means there is no minimum credit-score requirement to apply.
   - A card with an explicitly documented required subscription fails if the customer does not have it.
   - An invitation-only card fails absent a known invitation.
   - Do not invent a subscription or invitation requirement merely because a document does not discuss one.
3. For requested features, a missing required product fact is insufficient information, not a pass. In particular, virtual-card management must be explicitly available when requested.
4. A card is a match only when all applicable documented eligibility and all stated feature constraints pass. A failed constraint excludes it. If a required product fact is missing, label the result insufficient information rather than claiming it matches.
5. If multiple cards match, list them without ranking on unstated preferences. If no card matches, identify the documented blockers.

Use `scripts/evaluate_card_fit.py` for normalized, repeatable comparisons. Verify the extracted values against the supplied documents before relying on script output.

## Script interface

Run:

```sh
python3 scripts/evaluate_card_fit.py < request.json
```

The script accepts one JSON object on standard input and emits one JSON object on standard output:

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

Use `null` for a product fact not stated in the available documents. For eligibility prerequisites, `null` means no published prerequisite was found and is not manufactured as a blocker. For a requested fee, payment, or virtual-card feature, `null` is reported as insufficient information. The script returns `compatible`, `incompatible`, or `insufficient_information`, plus individual checks. It makes no approval or application decision.

## Customer response

Give a direct, evidence-grounded recommendation before discussing optional next steps.

For every match, state:

1. the card name and that it meets the customer's stated filters;
2. its exact documented foreign transaction fee;
3. its exact documented minimum payment and the published balance basis;
4. that virtual-card management is available, with only documented capabilities if helpful; and
5. why the customer's stated credit score does or does not clear the documented credit-score requirement.

When a card has a published minimum score of zero, say plainly that it has **no minimum credit-score requirement to apply**, so the customer's score does not bar an application. Always add that meeting published criteria does not guarantee approval and that an application remains subject to underwriting and any requested documentation.

For the currently supplied product set, if a customer has a 540 score, needs a foreign transaction fee of 1.5% or less, a minimum payment of 1.5% or less, and virtual-card management, explicitly recommend **EcoCard**. State that EcoCard has no minimum credit-score requirement to apply; its foreign transaction fee is 1.0%; its minimum monthly payment is 1.0% of the outstanding balance (plus applicable past-due amounts and fees); and virtual card management is available. Do not guarantee approval.

If the customer asks to proceed, provide only source-supported application guidance; do not submit an application. A statement about taking business elsewhere is not itself a request for an account action or human transfer.
