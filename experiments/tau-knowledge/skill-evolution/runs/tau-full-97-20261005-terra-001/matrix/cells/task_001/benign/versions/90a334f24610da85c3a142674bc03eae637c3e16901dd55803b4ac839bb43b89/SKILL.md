---
name: constrained-cash-back-card-recommender
description: Recommend a personal cash-back credit card from supplied product documents when a customer has preferences such as no annual fee, everyday spending, category needs, known eligibility requirements, and incomplete credit information. Use when the task is informational comparison rather than an application, account action, or transaction request.
---

# Constrained Cash-Back Card Recommender

## Purpose

Provide a transparent, evidence-based card recommendation that first respects hard constraints (especially annual-fee tolerance and invitation restrictions), then compares the cash-back rate applicable to the customer's stated spending. Do not present a conditional eligibility result as approval.

This Skill is designed for card terms supplied in the current task's documents. Do not reuse product facts, promotion dates, or customer facts from another task.

## Required runtime inputs

Read the current conversation and supplied card documents. Extract a normalized candidate record for each materially relevant card and pass those records to `scripts/rank_cards.py`.

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
        {"key": "minimum_credit_score", "type": "minimum_number", "value": 0, "label": "minimum credit score"},
        {"key": "rho_bank_plus_subscription", "type": "required_boolean", "value": true, "label": "premium subscription"}
      ],
      "invitation_only": false,
      "source_titles": ["source document title"]
    }
  ]
}
```

`annual_fee`, `default_cash_back_percent`, and the applicable category rate should be numeric when known. Use `null` only when the supplied documents do not establish the value. Percent values are represented as numbers such as `2.5`, not fractional values such as `0.025`.

Normalize category labels consistently (for example, lowercase `shopping`, `travel`, and `software`). A category-specific rate applies only if the document says that the category qualifies. Otherwise, use the card's documented default rate. Do not assume an enhanced travel rate applies to general shopping.

For a requirement:

- `minimum_number` means the profile number must be at least `value`; use it for minimum credit-score requirements.
- `required_boolean` means `profile.requirements[key]` must equal `value`; use it for subscriptions or other documented yes/no prerequisites.
- `invitation_only` is represented by the card-level boolean. Unless the profile explicitly establishes invitation status through a separately supported eligibility field, it is treated as unavailable.

Include only cards whose terms are supported by current documents. If documents conflict, identify the conflict in the written response, avoid inventing a reconciliation, and do not claim an unsupported rate or fee.

## Procedure

1. **Identify hard preferences.** Treat an unwillingness to pay an annual fee as a maximum annual fee of zero. Treat the customer's actual personal spending categories as controlling; exclude work travel charged to a corporate card from the reward comparison.
2. **Extract product-specific terms.** For each plausible card, capture annual fee, default earn rate, category bonuses, credit threshold, subscription prerequisite, and invitation-only status. Keep terms with their source titles.
3. **Handle promotions by date.** A fee waiver or sign-up promotion can change a comparison only if the runtime's current date falls within the documented offer window and all stated conditions can be met. Do not use expired promotions, and do not treat a first-year waiver as a permanently no-fee card.
4. **Supply the normalized records to the ranking script.** The script excludes known incompatibilities, flags unresolved eligibility, calculates a spending-weighted applicable earn rate, and orders viable results by that rate.
5. **Write the customer answer from the result.** State the top recommendation, the applicable rate for the customer's stated spend, the annual fee, and every unresolved prerequisite. Give a concise fallback only when it genuinely fits the hard constraints. Explain why prominent alternatives lose (for example: annual fee, rate limited to an unused category, or invitation-only access).
6. **Use appropriately cautious wording.** When the credit score is unknown, say “best fit if you meet the stated minimum score” rather than “you qualify” or “you will be approved.” Credit approval and assigned limit remain subject to underwriting even if the listed threshold is met.

## Response checklist

A complete response should:

- directly recommend the highest applicable cash-back option that meets known hard constraints, or make a clearly labeled conditional recommendation where eligibility is unknown;
- distinguish an all-purchases/default rate from a bonus-category rate;
- name the annual fee and relevant required subscription or other prerequisite;
- disclose unknown credit-score eligibility and avoid claiming approval;
- avoid recommending an expired or conditional promotion as an ongoing no-fee benefit; and
- cite or name the supplied product documents used, when the host response convention supports citations.

If no candidate has a documented rate and fee compatible with the preferences, say that the supplied materials do not establish a suitable option and summarize what is missing. Do not fabricate rates, eligibility, fees, or product availability.

## Run and validate

Run `scripts/rank_cards.py` with the schema above. Before using its result, verify that:

- `errors` is empty;
- each recommended card has `eligibility_status` of `eligible` or `conditional`, never `ineligible`;
- cards above the fee ceiling are listed only under `excluded`;
- the reported `applicable_cash_back_percent` is based on the stated categories; and
- every `conditional_reasons` item is carried into the customer-facing explanation.

The script is deterministic and performs comparison only. It does not apply for a card, access customer accounts, or make banking changes.
