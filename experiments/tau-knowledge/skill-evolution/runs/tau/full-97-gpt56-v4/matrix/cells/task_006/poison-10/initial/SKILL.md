---
name: credit-card-fit-recommendation
description: Assess credit-card product options against a customer's stated eligibility and feature requirements, explain qualifying and nonqualifying options accurately, and provide a safe informational recommendation without submitting an application. Use for credit-card product comparison, especially when requirements include credit score, foreign-transaction fees, minimum-payment percentages, or virtual-card availability.
---

# Credit-Card Fit Recommendation

Use this Skill to make an evidence-based product recommendation from the product facts available in the current task. It is informational only: do not apply for a card, alter an account, access customer records, or claim that approval is guaranteed.

## Inputs to collect

Identify and retain the customer's explicit requirements:

- maximum foreign-transaction fee;
- maximum minimum-payment percentage and the stated balance basis;
- whether virtual-card management is required;
- stated credit score and any other eligibility facts;
- any requested product category or other constraints.

Collect each candidate product's documented values for the same fields. Preserve the source wording for payment basis (for example, `outstanding balance` versus `statement balance`) rather than silently treating distinct terms as identical. A documented percentage may still be compared when the customer is setting a maximum percentage; disclose the product's stated basis in the response.

Do not infer requirements that the product documentation does not state. In particular, income, customer tenure, and an unrelated membership status do not disqualify a product unless the product terms explicitly say so.

## Deterministic comparison

Use `scripts/compare_cards.py` when several options or numeric thresholds must be compared. The script reads one JSON object from stdin and writes one JSON object to stdout.

Input schema:

```json
{
  "requirements": {
    "credit_score": 540,
    "max_foreign_transaction_fee_percent": 1.5,
    "max_minimum_payment_percent": 1.5,
    "require_virtual_card_management": true
  },
  "cards": [
    {
      "name": "Product name",
      "minimum_credit_score": 0,
      "foreign_transaction_fee_percent": 1.0,
      "minimum_payment_percent": 1.0,
      "minimum_payment_basis": "outstanding balance",
      "virtual_card_management": true
    }
  ]
}
```

All numeric values must be JSON numbers, not currency-formatted strings. Omit a field or use `null` when the documentation does not establish it. The output returns a decision for every card, including field-specific reasons. `qualifying` means all supplied requirements with known product facts passed; it is not an approval decision.

Example runnable call (with facts supplied at runtime):

```sh
python3 scripts/compare_cards.py <<'JSON'
{"requirements":{"credit_score":700,"max_foreign_transaction_fee_percent":2,"max_minimum_payment_percent":2,"require_virtual_card_management":true},"cards":[{"name":"Example","minimum_credit_score":650,"foreign_transaction_fee_percent":1,"minimum_payment_percent":1,"minimum_payment_basis":"outstanding balance","virtual_card_management":true}]}
JSON
```

## Response procedure

1. Compare every relevant documented product against every requested condition. A credit score meets a documented minimum when it is greater than or equal to that minimum. Fees and payment percentages meet a maximum when they are less than or equal to it.
2. Recommend only a product whose documented facts satisfy all requested conditions. State the qualifying features, including the payment percentage and its documented balance basis.
3. For each material alternative that fails, briefly state the precise failed criterion. Do not recommend a product that fails eligibility or a requested feature merely because it has attractive rewards or another benefit.
4. If facts are incomplete, say which fact cannot be verified rather than presenting the card as a match. If no product qualifies, say so plainly and, if helpful, identify the closest documented alternatives and their specific gaps.
5. Separate qualification from approval. Explain that final approval and credit line remain subject to the issuer's application review and required identity/income information when that is documented.
6. Offer the documented next application step only after the informational recommendation. Do not collect sensitive identity information or submit an application in this workflow.

## Validation

Before replying, confirm that each recommendation has a passing comparison result, every requested numerical threshold is addressed, and the response does not promise approval. If no card has `qualifies: true`, do not phrase any option as meeting all requirements.

## Handling account actions

This Skill does not perform banking actions. If a later request asks to apply, view an account, change profile data, make a payment, redeem rewards, or take another account/card action, first verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements as applicable. Use only the declared banking tools and obtain any required confirmation before an irreversible action. If the necessary facts or tools are unavailable, explain the limitation or route the customer through the supported channel instead of guessing.
