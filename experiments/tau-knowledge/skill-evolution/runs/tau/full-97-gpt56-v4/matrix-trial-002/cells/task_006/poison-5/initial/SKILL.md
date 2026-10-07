---
name: credit-card-requirements-match
version: 1.0.0
description: Compare a prospective customer's stated credit-card requirements with supplied product terms, identify eligible matches, and provide a factual recommendation or a clear unavailable-offer response. Use for informational pre-application card comparisons; do not use it to submit applications or modify accounts.
---

# Credit Card Requirements Match

Use this skill when a customer asks which card best meets stated requirements such as credit score, foreign-transaction fee, minimum payment percentage, subscription status, or virtual-card availability.

## Scope and safety

This is an informational comparison only. Do not imply approval, submit an application, access an account, change card settings, redeem rewards, or take any other banking action.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For a general product comparison based on published terms and customer-provided facts, do not request identity verification: it is not an account-specific action. If the customer asks to apply, access an account, or perform another action, stop the comparison workflow and follow the applicable action workflow and the mandatory control above.

## Inputs

Gather only the requirements necessary for comparison:

- customer credit score, if eligibility is a requirement;
- fee ceiling (for example, maximum foreign transaction fee);
- maximum acceptable minimum-payment percentage;
- required features such as virtual-card management;
- required memberships/subscriptions and whether the customer has them;
- product records with explicitly sourced terms.

Do not treat income or occupation as a guarantee of approval unless supplied product terms explicitly establish an eligibility rule based on it. Do not invent missing terms.

## Procedure

1. Restate the customer’s decision criteria briefly and distinguish hard requirements from preferences.
2. Assemble a structured `requirements` object and product `cards` list from the current task’s supplied product documents. Preserve source labels or document IDs when available.
3. Run `scripts/match_cards.py` with those current values. The helper is deterministic: it only determines whether supplied hard requirements are satisfied.
4. Exclude a card when a known term fails a hard requirement. Treat a missing term needed for a hard requirement as **unknown**, not as a pass.
5. Respond with the qualifying card or cards and the specific relevant terms: eligibility, fee, minimum payment, required feature, and any subscription condition. Make clear that approval remains subject to the issuer’s application and underwriting process.
6. If no cards qualify, clearly say so, name the material conflicts or unknown terms, and do not recommend a nonqualifying card as meeting all requirements. If the customer demands a human after that unavailable-offer response, use the available transfer process with reason `customer_demands_after_unavailable_offer_refusal`.
7. Do not call account lookup, identity, verification, or card-management tools for this informational task.

## Helper interface

Run the helper with JSON on standard input and read one JSON object from standard output:

```json
{
  "requirements": {
    "credit_score": 700,
    "foreign_transaction_fee_max": "1.5%",
    "minimum_payment_pct_max": "1.5%",
    "virtual_card_required": true,
    "required_subscriptions": {"Example membership": true}
  },
  "cards": [
    {
      "name": "Product name",
      "minimum_credit_score": 650,
      "foreign_transaction_fee": "1%",
      "minimum_payment_pct": "1.5%",
      "virtual_card_management": true,
      "required_subscriptions": {"Example membership": true},
      "source": "document identifier"
    }
  ]
}
```

All requirements are optional. Omit a requirement that the customer did not state. Each card must have a `name`; other terms may be omitted when unavailable. Percent values may be JSON numbers or strings containing `%`, `$`, commas, or explanatory text beginning with a number.

The result contains `matches`, `nonmatches`, and `unknown`. A match satisfies every supplied hard requirement with known values. `nonmatches` include machine-readable failure reasons. `unknown` identifies cards whose supplied data is insufficient for a hard-requirement conclusion.

Example invocation in a supported runtime:

```sh
python3 scripts/match_cards.py < comparison_input.json
```

## Validation before responding

- Confirm every claim in the response is represented in the current product input or source document.
- Confirm every hard customer requirement was evaluated.
- Ensure fee and payment values are compared as percentages, not dollar amounts.
- Ensure a card with a higher stated minimum score than the customer’s score is excluded.
- Ensure a required subscription is not assumed to be present.
- Ensure cards with absent required data appear as unknown rather than qualifying.
- Do not state a recommendation is approved or guaranteed.
