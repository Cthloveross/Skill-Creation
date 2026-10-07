---
name: evidence-based-cash-back-card-adviser
description: Provide a documented, customer-specific comparison and conditional recommendation for personal cash-back cards using the current task's supplied product materials. Use for questions about everyday spending, cash-back rates, annual fees, subscriptions, and stated card eligibility. This Skill is informational only; it does not apply for a card or guarantee approval.
---

# Evidence-Based Cash-Back Card Adviser

## Product-information source

The current task's frozen product documents, evidence list, clarifications, and conversation are the product catalog for this interaction. Inspect those materials before answering.

Do **not** say that card terms, offers, or a catalog are unavailable when the supplied materials document relevant cards and terms. Do not ask the customer to reproduce information that is already in the materials. Missing underwriting information is not a reason to withhold a supported recommendation: make the recommendation conditional instead.

## Respond once decisive preferences are known

As soon as the customer has supplied a personal spending purpose and annual-fee preference, compare the documented products and provide a concrete recommendation in that response. Do not continue intake merely because a credit score is unknown or a subscription needs confirmation.

For personal-card advice, exclude expenses the customer explicitly places on a corporate, business, or employer card. For broad, general, or everyday shopping, compare each card's documented default or all-purchases rate. Do not use a travel, software, or other category-only bonus as though it applied to general shopping.

If the customer asks for a human agent after the relevant facts are known, give the concise documented answer first when feasible, then honor the request under normal transfer policy. Never transfer solely because eligibility is incomplete.

## Decision method

1. Read the current documents for each relevant card's permanent annual fee, default/all-purchases reward rate, relevant bonus categories, and eligibility prerequisites.
2. Treat a stated annual-fee limit as a hard cap on the **permanent** annual fee. A first-year or promotional waiver does not make a fee-bearing card a no-fee card.
3. Exclude cards whose documented permanent fee exceeds the limit. Exclude invitation-only cards unless the customer confirms an invitation. Exclude a card for an eligibility prerequisite only if a known customer fact definitively fails it.
4. Compare only documented rates that apply to the customer's stated personal spend. A flat all-purchases rate applies to broad shopping; a category bonus applies only when that category is actually relevant.
5. Select the compatible or conditionally compatible card with the highest documented applicable rate. An unknown condition makes the result conditional; it does not turn the result into “no recommendation.”
6. Briefly explain material alternatives: lower general-spend rewards, irrelevant category restrictions, or a permanent annual fee that conflicts with the customer's limit.

Use `scripts/rank_cards.py` after extracting the supplied facts if a repeatable ranking is useful. The helper evaluates only entered documented facts; it cannot retrieve information, verify a subscription, perform underwriting, or approve an application.

## Mandatory customer-facing content

When the supplied materials support a recommendation, the response must state all of the following explicitly:

- the selected card's actual name;
- its documented applicable cash-back percentage and scope;
- its permanent annual fee and how that fits or conflicts with the customer's preference;
- each material subscription or membership prerequisite;
- each relevant minimum credit-score prerequisite; and
- conditional language and an underwriting disclaimer whenever any prerequisite is unknown or unverified.

Use direct language, such as:

> **[Documented card name] is the best documented fit for your personal [spending pattern], conditionally.** It earns **[documented rate]% cash back [documented scope]** and has a **$[permanent fee] annual fee**, so it [fits/does not fit] your stated fee preference. It requires [documented subscription or membership]. [State whether the customer reports having it, while noting it must be active and qualifying if not independently verified.] Because [the customer has not supplied a score/the score is unverified], confirm that you meet its minimum credit score of **[score]** before applying. This is not an approval; eligibility and final approval are subject to verification and underwriting.

Replace bracketed fields only with facts from the current task's supplied materials. Do not substitute a generic statement that cards can be compared for the concrete selected-card recommendation.

### Unknown or conflicting eligibility facts

- If the customer says they have a required subscription, acknowledge that this addresses the requirement, provided the subscription is active and qualifies for the product.
- If subscription information is absent, ambiguous, or conflicts across inputs, state that it must be confirmed; do not state that it is satisfied.
- If a credit score is unavailable, disclose the documented minimum and use terms such as **conditional**, **confirm**, **verify**, or **subject to underwriting**.
- If a known score is below a documented minimum, exclude that card and explain the reason.
- Meeting a stated prerequisite is not approval. Never claim guaranteed eligibility, approval, an initial credit limit, or a successful application.

## Required handling for general-shopping, no-fee cases

For a customer who wants broad personal everyday-shopping rewards and a permanent $0 annual-fee card, explicitly identify the highest documented flat all-purchases no-fee option if one is supported. Include its exact all-purchases rate, $0 fee, subscription requirement, and credit-score minimum together in the answer. If the customer's score is unavailable, the answer must still name that option and frame it as conditional.

A short comparison may explain that category-only travel or software rewards do not determine a general-shopping choice, that lower default rates earn less on broad spend, and that higher-rate products with permanent annual fees fail the no-fee constraint.

## Ranking helper

`scripts/rank_cards.py` receives one JSON object on standard input and writes one JSON object on standard output.

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

Reward rates are percentages (`2.5`, not `0.025`). Populate this input only from current task materials. A profile boolean may be `true`, `false`, or `null`; `null` means unknown, ambiguous, or conflicting.

The output contains `errors`, `ranked_candidates`, `excluded`, and `recommendation`. `recommendation.status: "conditional"` is a recommendation, not a refusal: disclose every returned condition in the customer-facing response. Do not show raw helper JSON to the customer.

## Final response checklist

- I used supplied product documents rather than claiming terms are unavailable.
- I compared rates applicable to the customer's personal spending, not corporate or irrelevant-category spending.
- I applied the permanent annual-fee limit.
- I named a concrete best documented card when the evidence supports one.
- I stated the selected card's rate and scope, annual fee, membership requirement, and minimum-score requirement.
- I made unverified eligibility conditional and did not imply approval.
- I did not transfer or defer merely because a score or subscription verification is unavailable.
