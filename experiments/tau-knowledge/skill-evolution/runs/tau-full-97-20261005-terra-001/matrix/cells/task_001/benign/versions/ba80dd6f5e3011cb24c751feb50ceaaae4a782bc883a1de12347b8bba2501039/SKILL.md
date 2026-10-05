---
name: constrained-cash-back-card-recommender
description: Provide a supported, conditional personal cash-back card recommendation from card materials supplied with the current task. Use when a customer states spending priorities, fee preferences, and possibly incomplete eligibility information. Do not use for submitting applications, changing accounts, or making transactions.
---

# Constrained Cash-Back Card Recommender

## Objective

Give the customer a concrete recommendation when the supplied card materials support one. Compare rewards against the customer's **personal** spending and apply hard constraints, especially annual-fee preferences, before optimizing reward rates.

The current task's supplied card documents are the product-information source. They are sufficient evidence when they state the relevant terms. Never ask the customer to provide a catalog, rates, or terms that are already supplied in the task, and do not say that product terms are unavailable in that situation.

## When to answer immediately

Once the conversation establishes a spending pattern and fee preference, inspect the supplied materials and answer in the same response if a compatible card's fee and applicable earn rate are documented. This remains true when:

- the customer does not know their credit score;
- approval or an underwriting result is unavailable; or
- a required subscription is already confirmed by the customer.

A missing score makes the recommendation **conditional**; it is not a reason to transfer the customer or withhold a comparison. Do not transfer merely because information needed for approval is unknown.

## Gather and normalize the current-task facts

Read the complete current conversation and all relevant supplied documents, including separate documents for eligibility, fees, and rewards. Build a candidate record only from supported terms.

For every materially relevant card, capture:

- card name;
- permanent annual fee (not merely a temporary promotional waiver);
- default or all-purchases cash-back rate;
- category-specific rates and their qualifying categories, if any;
- minimum credit score and other eligibility requirements;
- invitation-only restrictions; and
- source titles for traceability.

Use personal spending only. Do not use travel, business, or other expenses charged to an employer's corporate card to justify a personal-card travel bonus. For broad everyday or general shopping, use a documented all-purchases/default rate unless the documents explicitly establish that a higher category rate applies to that spending.

An annual-fee ceiling is a hard constraint. A card whose permanent fee is above the ceiling, or whose permanent fee cannot be established, cannot be presented as satisfying a no-fee preference. A limited-time or first-year fee waiver does not make a card permanently no-fee.

## Evaluate eligibility correctly

Use these rules for each documented requirement:

- A customer statement that they have the required subscription satisfies that subscription requirement.
- An unknown credit score is unresolved, not failed and not satisfied. State the documented minimum and make the recommendation conditional.
- A known score below the documented minimum excludes the card.
- Treat invitation-only cards as unavailable unless the customer explicitly confirms an invitation.
- Meeting a listed minimum does not guarantee approval. Approval and the final credit limit remain subject to underwriting.

## Rank candidates with the packaged helper

Create the JSON input described below and run `scripts/rank_cards.py`. The script reads one JSON object from stdin and emits one JSON object on stdout. It performs deterministic constraint filtering, rate selection, eligibility classification, and customer-message drafting; it does not apply for a card or access an account.

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
    "requirements": {"required_subscription_key": true}
  },
  "cards": [
    {
      "name": "string",
      "annual_fee": 0,
      "default_cash_back_percent": 0,
      "category_cash_back_percent": {"shopping": 0},
      "rate_scope": "on all purchases",
      "requirements": [
        {
          "key": "required_subscription_key",
          "type": "required_boolean",
          "value": true,
          "label": "subscription name"
        },
        {
          "key": "minimum_credit_score",
          "profile_key": "credit_score",
          "type": "minimum_number",
          "value": 0,
          "label": "minimum credit score"
        }
      ],
      "invitation_only": false,
      "source_titles": ["source document title"]
    }
  ]
}
```

Represent cash-back percentages as percentage values (for example, `2.5`, not `0.025`) and fees as numbers. Supply a category rate only if the document says it applies to that category. `rate_scope` should be a supported customer-facing description such as `on all purchases` or `on eligible shopping purchases`.

For `minimum_number`, `profile_key` maps the requirement to a profile value. For `required_boolean`, the customer value is read from `profile.requirements[key]`.

## Interpret the output

Check that `errors` is empty. Use `recommendation` only when its `eligibility_status` is `eligible` or `conditional`; never recommend an entry in `excluded`.

Use the emitted `customer_message` as the factual core of the response, completing it only with supported context. It deliberately identifies confirmed prerequisites, unresolved requirements, and underwriting uncertainty. If the script produces no recommendation, explain the specific missing or incompatible comparison term rather than fabricating a card or promising eligibility.

## Required customer-facing response

Lead with the recommendation, rather than narrating the search process. A complete answer must include:

1. the recommended card's name;
2. the cash-back rate that applies to the customer's stated personal spending and the documented scope of that rate;
3. its annual fee and whether it meets the customer's fee preference;
4. acknowledgement of each prerequisite the customer has already established; and
5. every unresolved requirement, especially a missing score, using conditional language such as “confirm,” “if you meet,” “conditional,” or “subject to underwriting.”

A concise comparison is useful when it explains why alternatives lose: for example, a lower default rate, an unrelated bonus category, a fee above the stated ceiling, or an invitation restriction. Do not imply that a customer is approved, will be approved, or definitely qualifies.

## Final checklist

Before sending the response, verify that it:

- uses supplied materials rather than claiming they are absent;
- respects a no-annual-fee preference using the permanent annual fee;
- selects the highest supported applicable rate among cards meeting known hard constraints;
- does not apply unrelated category bonuses to general spending;
- recognizes a confirmed prerequisite such as a subscription;
- explicitly states an unknown score's documented minimum and conditional status;
- says approval is subject to underwriting; and
- does not transfer a customer when a conditional informational recommendation is supported.
