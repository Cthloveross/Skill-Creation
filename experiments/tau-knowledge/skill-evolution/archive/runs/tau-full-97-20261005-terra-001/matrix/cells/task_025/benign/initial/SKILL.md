---
name: business-credit-card-large-purchase-comparison
description: Compare business credit-card options for a proposed large purchase using documented reward rates, merchant-category restrictions, promotions, fees, credit-limit ceilings, and reward-point conversion. Use for informational card-selection questions; do not use it to submit an application or promise approval or reward qualification.
---

# Business credit-card large-purchase comparison

## Purpose

Give a conditional, evidence-based comparison of cards for one proposed business purchase. The comparison must distinguish a card's *maximum possible* line from an approved line, and a merchant's described product from its payment-network merchant category code (MCC).

This Skill is informational. Do not open an account, change an account, or represent that a charge will be approved. If the customer asks to apply, use only the normal banking application flow available to the execution agent; this Skill does not authorize an action.

## Required runtime inputs

Collect or derive these fields from the current customer request and the applicable card documents:

- `purchase_amount`: positive amount of the intended single charge.
- Merchant name/descriptor, purchase description, and any known MCC or confirmed rewards category.
- Whether the buyer is a new customer and the account-opening date, if a time-limited promotion or fee waiver matters.
- Candidate cards, including their documented maximum limit, annual fee, eligible bonus categories, exclusions, and all conditions for a promotion.
- Current date/time, from a supplied observation or `get_current_time` when the date is needed and no current observation is available.

Do **not** infer an MCC from a merchant name, product description, or the customer's intended business purpose. A described category can support a conditional scenario only; confirmed coding is required for a definitive bonus-rate statement.

## Method

1. **Identify the purchase constraint.** Treat the amount as one transaction, not as spend that may be split across cards. Exclude a card if its documented maximum credit line is below the amount. For every card whose maximum is at least the amount, say it is only a possible fit subject to underwriting, the approved line, available credit, and authorization controls.
2. **Extract rate scenarios.** For each viable card, list the base rate and every plausible higher rate. Attach the exact qualification: merchant coding, direct billing, card-specific merchant exclusion, promotional opening window, and/or account-age window.
3. **Resolve explicit exclusions before category bonuses.** If a card names the merchant or relevant merchant class as excluded from a bonus, do not present that bonus as available. Apply any documented promotional multiplier only when its terms cover the resulting standard or eligible rate.
4. **Check dates precisely.** Confirm that account opening is within a promotional date range and, where applicable, that the charge occurs within the customer-specific post-opening period. Do not assume a date window applies to an existing account or future applicant without checking.
5. **Calculate every scenario.** Supply the viable scenario rates and effective first-year fee to `scripts/compare_card_options.py`. The calculator returns cash back, points, first-year net after the supplied fee, and a capacity assessment.
6. **Rank conditionally.** Lead with the highest-return scenario only if its conditions can be met. Also identify the best fallback rate if merchant coding is not confirmed. State that a lower fee does not cure insufficient approved credit or an ineligible MCC.
7. **Give a clear next step.** Ask the customer to obtain the merchant descriptor/MCC or written confirmation of the processing category before making a large charge. They should also request or verify a credit line sufficient for the full authorization plus any holds. If their credit profile is unknown, summarize documented standards without saying they qualify.

## Response structure

Use concise customer-facing language in this order:

1. A direct recommendation framed as conditional, plus the reason.
2. A short option table: card, ability to potentially support the single charge, rate scenario, estimated cash back/points, first-year fee, and key condition.
3. Important exclusions and uncertainty, especially merchant coding and unguaranteed limits.
4. Promotion timing and standard fees after any waiver/promotion.
5. Practical verification steps and application eligibility caveat.

Format money to two decimals. For the listed cash-back cards, the backend may label rewards as points; use the supplied conversion of 100 points per currency unit (1 point = $0.01) and explain that the points represent cash back.

## Calculator

Run `scripts/compare_card_options.py` with JSON on stdin (or with `run_skill_script`). Its input schema is:

```json
{
  "purchase_amount": "2500.00",
  "points_per_currency_unit": 100,
  "offers": [
    {
      "name": "Example Business Card",
      "maximum_credit_limit": "5000.00",
      "annual_fee": "99.00",
      "first_year_fee": "0.00",
      "scenarios": [
        {
          "label": "confirmed qualifying category",
          "rate_pct": "3.0",
          "conditions": ["MCC is confirmed eligible"],
          "certainty": "conditional"
        },
        {
          "label": "base rate",
          "rate_pct": "1.0",
          "conditions": ["eligible purchase"],
          "certainty": "baseline"
        }
      ]
    }
  ]
}
```

All monetary values may be JSON numbers or decimal strings. `first_year_fee` is optional and defaults to `annual_fee`. `maximum_credit_limit` may be `null` when no ceiling is documented. The output is a JSON object with `ok`, `purchase_amount`, and a descending `results` list. Each result preserves the supplied conditions and includes `capacity_assessment`, `cash_back`, `reward_points`, `first_year_fee`, and `first_year_net_after_fee`.

Example executor call: run `scripts/compare_card_options.py` using the JSON object above. Replace the illustrative offer and values with facts extracted from the current task before relying on its output.

## Validation and failure handling

- Reject a missing, nonnumeric, zero, or negative purchase amount.
- Reject an empty offer list or a scenario with a negative rate.
- Treat omitted or unknown maximum limits as `unknown`, not sufficient.
- Treat absent MCC data as uncertainty; provide only conditional category scenarios and a documented baseline.
- If a card's maximum is below the charge, show it as unable to support that single charge rather than calculating it as a recommendation.
- If a promotion's eligibility date, new-customer status, opening date, or post-opening period is not established, do not include the promotional rate or waived fee as certain. Present it separately as pending verification if useful.
- The calculator is arithmetic only. It does not determine eligibility, merchant coding, account approval, promotion status, or available credit.

See `references/business_card_policy_facts.md` for the relevant documented card facts and source mapping.
