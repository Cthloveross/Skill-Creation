---
name: documented-business-card-reward-comparison
description: Compare documented business credit-card choices for a planned purchase when merchant category coding, merchant-specific exclusions, annual fees, promotions, and credit-line capacity affect the outcome. Use for advisory card-selection questions; not for applications, account opening, or charging a card.
---

# Documented Business Card Reward Comparison

## Scope and safety boundary

Use this Skill when supplied materials document card terms and a customer asks which card could provide the best return for a planned purchase. Provide the analysis directly from those materials; do not claim that terms are unavailable when they are supplied.

This is advisory only. Do **not** apply for a card, open an account, change a credit line, or initiate a payment. Do not promise approval, an assigned limit, available credit, transaction authorization, promotion eligibility, or a particular merchant category code (MCC).

## Extract the decision facts

Read the supplied task materials and identify:

- purchase amount, currency, and whether it is one charge;
- product/brand named by the customer, actual billing entity or statement descriptor if known, and confirmed MCC/category if any;
- plausible category scenarios when MCC is unknown, including software/SaaS, media/streaming, operations, and an other/non-bonus fallback where relevant;
- every documented candidate card's base rate, bonus categories, merchant exclusions, annual fees, fee waivers, promotions, limit range, and material eligibility thresholds;
- promotion dates and the supplied current date; and
- facts that are unknown, including whether the account will be new/eligible and whether a sufficient line will be approved.

A product name, a streaming brand, a software-like service, or a business purpose does not establish the billing entity or MCC. Rewards depend on the category submitted by the merchant/payment processor.

## Analysis method

1. **Cover all relevant documented options.** Include every candidate card supported by the supplied materials, including no-fee and lower-return choices when they bear on the comparison.
2. **Model category scenarios separately.** Apply a bonus only in the category to which the card terms assign it. Apply the base rate in every other or unconfirmed category.
3. **Handle merchant exclusions precisely.**
   - If the actual billing entity/descriptor is confirmed to be a listed excluded merchant, use the documented excluded/base rate.
   - If the customer named a brand that appears in an exclusion list but the billing entity is not confirmed, call this an exclusion **risk**. Show both the otherwise-applicable bonus result and the excluded/base-rate result; do not assert that either will occur.
   - If the billing entity is known not to be listed, state that this does not itself establish the MCC.
4. **Calculate the reward deterministically.** For one transaction, calculate `floor(amount × rate_percent)` cash-back points, then value points at $0.01 each. Thus a whole-dollar amount at 4% produces $4,000 per $100,000 of eligible spend. Do not round fractional points up.
5. **Compare first-year economics.** State gross cash back, first-year annual fee, and first-year net value. Treat a fee waiver as conditional unless the supplied date is in its window and all stated customer/opening conditions are known. State the renewal/standard fee separately.
6. **Handle spending-credit promotions separately.** Include a statement credit as guaranteed only if every stated condition is established. Otherwise label its value and conditions as conditional; do not use it as the basis for a categorical recommendation.
7. **Assess the one-charge capacity independently.** A published maximum at least equal to the purchase means that product can *potentially* fit the charge. It does not establish approval, the assigned line, remaining available credit, an authorization result, or any individual spending control. A published minimum below the purchase is not an assurance of a higher line. If no maximum is documented, say feasibility is unknown.
8. **Make a conditional recommendation.** Identify the leading option for each confirmed MCC/exclusion scenario, then identify the non-bonus fallback. Tie the advice to a sufficient approved and available line.

## Required customer-facing response

Answer before asking an optional follow-up. Use a compact table or labeled bullets that includes, for each documented candidate card:

- card name;
- base and bonus reward rates;
- cash-back calculation for each relevant category scenario and non-bonus fallback;
- merchant-exclusion result or exclusion risk;
- standard annual fee and first-year fee/waiver status;
- applicable promotions and unresolved conditions;
- documented maximum line (or that none is documented); and
- whether the published maximum can potentially accommodate the single charge.

Then clearly state:

1. that MCC/merchant category controls rewards and branding alone does not resolve it;
2. the recommendation if each plausible category is confirmed;
3. the fallback recommendation if no bonus category applies;
4. that any merchant-specific exclusion must be checked against the actual billing entity/descriptor; and
5. the next checks: obtain the actual billing entity and MCC from the merchant, verify the offer disclosure before opening, and confirm an approved line and available credit at least equal to the one-time charge.

When terms are date-sensitive, explicitly anchor the conclusion to the supplied current date. When the customer asks about applying or making the charge, stop after the advisory answer and use an authorized banking workflow for any later action.

## Calculator

Use `scripts/compare_rewards.py` to make repeatable calculations. The script reads one JSON object on stdin and writes one JSON object on stdout. Card facts passed to the script must be taken from supplied documentation; the script does not invent product terms.

### Input schema

```json
{
  "purchase_amount": "100000.00",
  "merchant": {
    "named_brand": "customer-described brand or null",
    "billing_merchant": "confirmed statement descriptor/billing entity or null",
    "confirmed_category": null,
    "possible_categories": ["software", "media", "operations"],
    "eligible_purchase": true
  },
  "include_first_year_fee": true,
  "cards": [
    {
      "name": "documented card name",
      "base_rate_percent": "1.0",
      "category_rates_percent": {"software": "4.0"},
      "excluded_merchants": ["documented excluded merchant"],
      "first_year_annual_fee": "0.00",
      "standard_annual_fee": "450.00",
      "credit_limit_min": "75000.00",
      "credit_limit_max": "400000.00",
      "promotions": [
        {
          "name": "documented promotion",
          "eligible": false,
          "statement_credit": "500.00",
          "conditions": ["Document unresolved requirements"]
        }
      ]
    }
  ]
}
```

`confirmed_category` takes precedence over `possible_categories`. `billing_merchant` is an established descriptor, while `named_brand` is only what the customer calls the seller. A brand matching an exclusion without a confirmed billing entity produces an exclusion-risk alternative, not a conclusive excluded outcome. `eligible: true` means all promotion conditions have been established; any other value is presented as conditional.

### Runnable call example

```text
run_skill_script(
  relative_path="scripts/compare_rewards.py",
  input_json={
    "purchase_amount":"2500.00",
    "merchant":{"named_brand":null,"billing_merchant":null,"confirmed_category":null,"possible_categories":["software","media"],"eligible_purchase":true},
    "include_first_year_fee":true,
    "cards":[...]
  }
)
```

### Validate before using output

Confirm that each entered category, rate, exclusion, fee, promotion date/status, and limit came from supplied materials. Each `reward_points` must be a nonnegative integer and `reward_cash_value` must equal points divided by 100. Only promotions marked eligible appear in `guaranteed_statement_credit`. `potentially_supported` always requires the approval/available-credit disclaimer. If the script returns `error`, correct the input or disclose the missing fact instead of guessing.

## Banking-action boundary

A comparison is not a banking action. Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.
