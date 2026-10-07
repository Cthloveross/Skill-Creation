---
name: constrained-cash-back-card-recommender
description: Recommend a personal cash-back credit card from card terms supplied in the current task, while honoring fee preferences, stated spending patterns, eligibility prerequisites, and uncertain credit information. Use for informational card comparisons, not applications, account changes, or transactions.
---

# Constrained Cash-Back Card Recommender

## Purpose

Give a direct, evidence-based card recommendation. Respect hard constraints first (especially an annual-fee limit and invitation-only access), compare rewards that actually apply to the customer's personal spending, and state eligibility uncertainty without presenting it as approval.

The supplied current-task card documents are the product-information source. When those materials state a card's fee, rewards, and requirements, use them; do **not** say that terms or a catalog are unavailable merely because the customer has not supplied documents. Do not reuse facts, promotions, or customer details from another task.

## Immediate response rule

Once the conversation and supplied materials establish all of the following, provide the recommendation in the same response rather than asking for more information or transferring the customer:

- a relevant card's annual fee and applicable earn rate;
- the customer's fee preference and relevant personal spending pattern; and
- any known or unknown eligibility prerequisites.

An unavailable credit score does not prevent an informational recommendation. It makes a recommendation conditional on meeting the documented score threshold. Do not transfer solely because a score, approval result, or underwriting outcome is unavailable.

## Required runtime inputs

Read the current conversation and all supplied card documents. Extract a normalized candidate record for every materially relevant card whose necessary comparison terms are supported. Then pass the records to `scripts/rank_cards.py`.

The script reads one JSON object from stdin and emits one JSON object on stdout.

### Input schema

```json
{
  "preferences": {
    "max_annual_fee": 0,
    "categories": ["shopping"],
    "category_weights": {"shopping": 1},
    "prefer_highest_cash_back": true
  },
  "profile": {
    "credit_score": null,
    "requirements": {
      "rho_bank_plus_subscription": true
    }
  },
  "cards": [
    {
      "name": "string",
      "annual_fee": 0,
      "default_cash_back_percent": 0,
      "category_cash_back_percent": {"shopping": 0},
      "requirements": [
        {
          "key": "minimum_credit_score",
          "profile_key": "credit_score",
          "type": "minimum_number",
          "value": 0,
          "label": "minimum credit score"
        },
        {
          "key": "rho_bank_plus_subscription",
          "type": "required_boolean",
          "value": true,
          "label": "Rho-Bank+ subscription"
        }
      ],
      "invitation_only": false,
      "source_titles": ["source document title"]
    }
  ]
}
```

Use numbers for fees and percentages when documented; use `null` only where the current materials do not establish a value. Represent percentages as `2.5`, not `0.025`. Normalize categories consistently, such as `shopping`, `travel`, and `software`.

A category-specific rate applies only where the materials say the customer's category qualifies. Otherwise use the documented all-purchases/default rate. Never apply a travel, software, or other bonus category to general shopping without support.

For a requirement:

- `minimum_number` requires the corresponding profile value to be at least `value`. Set `profile_key` when the requirement identifier differs from the profile field, such as `minimum_credit_score` versus `credit_score`.
- `required_boolean` requires `profile.requirements[key]` to equal `value`.
- Set `invitation_only` at card level. Treat an invitation-only card as unavailable unless the profile explicitly establishes that the customer has an invitation.

## Method

1. **Identify hard constraints and spend.** An unwillingness to pay an annual fee means `max_annual_fee: 0`. Use personal spending, not work expenses charged to a corporate card. For broad everyday or general shopping, prioritize a documented all-purchases/default rate over bonuses for unrelated categories.
2. **Use supplied terms.** Capture each relevant card's annual fee, applicable default and bonus rates, minimum score, subscription prerequisite, invitation restriction, and source title. Do not infer missing terms.
3. **Treat known prerequisites correctly.** A customer statement that they hold the required subscription satisfies that subscription condition. An unknown score remains unresolved; it is not a failed condition and not proof of eligibility.
4. **Handle promotions carefully.** A promotional waiver affects a comparison only if the current runtime date falls in the documented offer window and the customer can meet every stated condition. A first-year waiver is not a permanently no-fee card.
5. **Rank candidates.** Run `scripts/rank_cards.py`. It excludes known incompatibilities, flags unresolved prerequisites, calculates the applicable weighted rate, and ranks viable candidates.
6. **Give the answer, not just the analysis.** Lead with the top card. State its applicable cash-back rate, annual fee, and all remaining conditions. Briefly explain why close alternatives lose when that helps the customer decide.

## Customer-facing response pattern

Use plain language following this structure, replacing every bracketed item with facts supported by the current task:

> **Recommendation: [card name], conditionally.** For your [personal spending pattern], it earns [applicable rate]% [on all purchases / in the applicable documented categories] and has a [annual fee] annual fee, so it fits your [fee preference]. Your [documented subscription or other known prerequisite] satisfies that requirement. Because your credit score is unknown, please confirm that you meet the [minimum score] minimum before applying; meeting a minimum does not guarantee approval, which remains subject to underwriting.
>
> [Optional concise comparison of other no-fee cards' lower general-spend rate, unrelated bonus categories, or fee-bearing/invitation-only alternatives.]

When the top candidate is fully eligible based on the supplied profile, retain the statement that approval remains subject to underwriting where appropriate. Never say that a customer is approved, will be approved, or definitely qualifies based solely on a listed minimum score.

## Response checklist

Before responding, verify that the answer:

- names the highest documented applicable cash-back option compatible with known hard constraints, or labels the best fit as conditional when a prerequisite is unknown;
- states the applicable all-purchases/default or supported category rate, rather than an unrelated bonus rate;
- states the annual fee and explains whether it meets the customer's ceiling;
- acknowledges any documented prerequisite already met by the customer;
- discloses each unresolved prerequisite, especially an unknown credit score, with conditional wording such as “if you meet,” “confirm,” or “subject to underwriting”;
- does not treat an expired, temporary, or conditional fee waiver as an ongoing no-fee benefit;
- does not claim documents are absent when supplied materials establish the needed terms; and
- does not transfer to a human agent when a complete conditional informational comparison is supported.

If the supplied materials truly do not establish any candidate's rate and fee compatible with the preferences, say exactly what comparison term is missing and avoid fabricating a recommendation.

## Run and validate

Run `scripts/rank_cards.py` using the schema above. Before relying on its result, verify that:

- `errors` is empty;
- the recommendation has eligibility status `eligible` or `conditional`, never `ineligible`;
- cards over the fee ceiling appear only under `excluded`;
- the reported `applicable_cash_back_percent` matches the customer's stated categories; and
- every `conditional_reasons` item appears in the customer-facing explanation.

The script only compares supplied terms. It does not apply for a card, access accounts, or make banking changes.
