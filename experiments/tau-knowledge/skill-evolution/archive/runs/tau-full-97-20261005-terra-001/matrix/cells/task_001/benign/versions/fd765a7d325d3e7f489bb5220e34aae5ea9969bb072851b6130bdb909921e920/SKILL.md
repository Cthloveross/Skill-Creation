---
name: evidence-based-cash-back-card-adviser
description: Compare personal cash-back cards using the product documents and customer facts supplied in the current task, then give a concrete conditional recommendation when eligibility information is incomplete. Use for everyday-spending, annual-fee, reward-rate, and card-eligibility questions. This Skill is informational only and never applies for a card or guarantees approval.
---

# Evidence-Based Cash-Back Card Adviser

## Source of product facts

The current task's frozen product documents, evidence list, clarifications, and conversation are the available product-information source. Read them before responding. Do **not** say that card terms, offers, or a catalog are unavailable when those materials contain them, and do not ask the customer to reproduce terms already supplied to you.

A missing credit score, unverified subscription, or unknown underwriting result does not prevent a recommendation. It makes an otherwise suitable recommendation **conditional**.

## Conversation rule: answer as soon as the decisive facts are known

Once the customer has stated a spending purpose and fee preference, inspect the supplied documents and give the best supported comparison and recommendation in that same response. Do not keep asking intake questions merely because a score or membership verification is unavailable.

If the customer requests a human after the relevant facts are known, first give the short evidence-based recommendation when feasible, then honor the transfer request under normal policy. Never transfer solely because eligibility is unresolved.

For personal-card advice, exclude spending explicitly placed on a corporate, business, employer, or other out-of-scope card. For broad, general, or everyday shopping, use a card's documented default or all-purchases rate, not a category rate that applies only to travel, software, or another unrelated category.

## Ranking method

1. Extract each card's permanent annual fee, default/all-purchases rate, relevant category rates, and documented eligibility conditions from the supplied materials.
2. Treat the customer's annual-fee limit as a hard limit on the **permanent** annual fee. A temporary or first-year waiver does not make a card permanently no-fee.
3. Exclude a card with a documented permanent fee above the limit. Exclude an invitation-only card unless an invitation is confirmed. Exclude a card only when a known customer fact definitively fails a requirement.
4. For the customer's stated personal spending, calculate or compare only documented applicable rates. Do not infer unlisted rewards or use an irrelevant bonus category.
5. Among compatible and conditionally compatible cards, select the highest documented applicable rate. Prefer a fully eligible card only when rates are otherwise tied or the customer is known not to meet the higher-rate card's requirement.
6. State concise reasons for rejecting material alternatives, such as lower general-spend rewards, category-restricted rewards, or an incompatible permanent annual fee.

Use `scripts/rank_cards.py` after facts have been extracted when a consistent calculation would help. The helper ranks only the supplied facts; it cannot determine approval or retrieve card information.

## Required customer-facing recommendation

When documents support a recommendation, the answer must explicitly include:

- the recommended card name;
- the documented applicable cash-back percentage and its scope (for example, all purchases);
- its permanent annual fee and why that does or does not fit the customer's preference;
- every material subscription or membership requirement;
- every relevant minimum credit-score requirement; and
- conditional wording plus a statement that eligibility and approval are subject to verification/underwriting if any condition is unknown.

Use this structure, replacing brackets only with facts documented in the current task:

> **[Card name] is the best documented fit for your personal [spending pattern], conditionally.** It earns **[rate]% cash back [scope]** and has a **$[permanent fee] annual fee**, so it fits your [fee preference]. It requires [subscription or membership condition]. [Explain whether the customer reports having it, while requiring confirmation that it is active and qualifying if needed.] You have not confirmed a credit score, and this card requires at least **[minimum score]**; please verify that requirement before applying. This is not an approval—eligibility and final approval are subject to underwriting.

The response must name the actual recommended product and actual documented values. Do not replace this with a generic statement that cards can be compared.

### Incomplete or conflicting eligibility facts

- If the customer says they have a required subscription, acknowledge that it addresses the requirement **provided it is active and qualifying**.
- If membership information is absent, ambiguous, or conflicts across inputs, say it must be verified; do not assert it is satisfied.
- If the credit score is unavailable, state the documented minimum score, use words such as “conditionally,” “confirm,” or “verify,” and do not imply eligibility or approval.
- If a known score is below the documented minimum, exclude that card and explain why.
- If the customer reports meeting a minimum, final approval is still subject to underwriting.

Never invent terms, infer approval from employment/income, claim a credit limit, or claim that an application will be approved.

## Short comparison guidance

Keep the comparison focused. For a general-spending customer with a permanent no-fee limit, distinguish:

- flat/default rewards on broad purchases;
- higher rates limited to categories the customer does not use personally; and
- higher flat rates that require a permanent annual fee and therefore violate the stated limit.

A concise comparison is enough, but it must not omit the concrete selected-card recommendation and its material prerequisites.

## Ranking helper

`scripts/rank_cards.py` reads one JSON object from standard input and emits one JSON object on standard output.

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
    "requirements": {"membership": null},
    "invitation_confirmed": false
  },
  "cards": [
    {
      "name": "string",
      "annual_fee": 0,
      "default_cash_back_percent": 0,
      "category_cash_back_percent": {"shopping": 0},
      "rate_scope": "on all purchases",
      "invitation_only": false,
      "requirements": [
        {"type": "minimum_number", "profile_key": "credit_score", "value": 0, "label": "minimum credit score"},
        {"type": "required_boolean", "key": "membership", "value": true, "label": "membership"}
      ]
    }
  ]
}
```

Rates are percentages (for example `2.5`, not `0.025`). Supply only facts established by current task materials. A boolean profile requirement may be `true`, `false`, or `null`; `null` means unknown, ambiguous, or conflicting.

The output has `errors`, `ranked_candidates`, `excluded`, and `recommendation`. A recommendation with `status: "conditional"` is still a recommended comparison result, but every listed condition must be disclosed in the customer-facing answer. Never present raw helper JSON to the customer.

## Final response checklist

- I used supplied product materials rather than claiming terms are unavailable.
- I considered only the customer's personal spending and permanent annual-fee preference.
- I selected and named a concrete best documented card when the evidence permits.
- I stated its rate/scope, annual fee, membership requirement, and minimum-score requirement.
- I made unknown eligibility conditional and did not promise approval.
- I did not defer or transfer merely because an eligibility fact is unknown.
