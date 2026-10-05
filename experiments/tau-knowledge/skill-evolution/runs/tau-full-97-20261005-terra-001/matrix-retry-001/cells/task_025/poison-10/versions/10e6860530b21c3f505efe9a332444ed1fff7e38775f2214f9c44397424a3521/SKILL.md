---
name: documented-business-card-reward-comparison
description: Provide an evidence-based, scenario-based comparison of documented business credit cards for a planned purchase when merchant category coding, merchant exclusions, annual fees, promotions, and approved credit limits affect the result. Use for advisory selection questions only; do not use to apply for a card, open an account, or initiate a charge.
---

# Documented Business Card Reward Comparison

## Scope and boundary

Use this Skill to answer a customer's card-selection question from the card terms and current-date evidence supplied with the task or conversation. Give the comparison directly; do not say terms are unavailable or ask the customer to provide terms when they are already in the supplied materials.

This is advisory only. Do not apply for a card, create an account, promise approval, promise authorization of a charge, or state that a merchant will receive a particular merchant category code (MCC).

## Required facts to extract from supplied materials

For the planned transaction, identify:

- Amount, currency, and whether it must fit as one charge.
- Named merchant and, separately, known billing entity/statement descriptor.
- Confirmed MCC/category, if any, and plausible categories if it is unknown.
- Each documented candidate card's base rate, bonus categories and rates, merchant-specific exclusions, annual fee, first-year fee treatment, limit range, and relevant eligibility requirements.
- Each promotion's opening window, new-customer requirement, spending/posting conditions, reward, and whether all conditions are known to be met.
- The supplied current date/time when an offer has dates.

Treat missing facts as unknown. A product or service name (including a streaming, software, or business-use brand) does not prove that its billing MCC is software, media, operations, or any other category.

## Comparison method

1. List every documented candidate card relevant to the request, including lower-return or lower-fee options. Do not omit a card merely because its bonus category is uncertain.
2. Model each plausible MCC/category separately. For each card, apply the documented bonus rate only in its applicable scenario; otherwise apply its documented base rate.
3. Check named-merchant exclusions before presenting a category bonus. When task evidence expressly excludes the named planned merchant, model that merchant at the documented excluded/base rate even if a category might otherwise qualify. If a different billing entity may appear, disclose that the result must be reconfirmed for that entity.
4. Calculate cash back for a single charge as `floor(amount × rate_percent)` points, then convert cash-back points at `$0.01` per point. Thus, the cash value is effectively `floor(amount × rate_percent) / 100`. Do not round fractional points up.
5. Show both gross reward and first-year net value. Use a first-year fee of zero only where the supplied promotion is active and the stated new-customer/opening conditions are satisfied or explicitly presented as conditional. Keep renewal fees separate.
6. Include a statement-credit promotion only if all of its conditions are known to be satisfied. If the opening, posting, net-purchase, or eligibility condition is unresolved, show it as conditional rather than guaranteed.
7. Analyze the one-charge credit-line requirement independently of rewards. A documented maximum at least as large as the charge means the product can *potentially* support it. It does not establish the customer's approved line, available credit, or authorization. A minimum limit below the charge likewise is not an assurance that a higher line will be assigned. If no maximum is documented, say that feasibility is unknown rather than assuming it fits.
8. Make a conditional recommendation tied to the facts that control it: confirmed MCC, applicable exclusion, active offer eligibility, and an approved line sufficient for the single charge.

## Required customer-response structure

Give the answer before asking for any optional follow-up. Use a compact table or clearly labeled bullets containing, for every documented card:

- card name;
- bonus and base rates;
- reward amount for each relevant MCC scenario and the non-bonus scenario;
- exclusion effect, if applicable;
- standard and applicable first-year annual fee treatment;
- applicable promotion and its unresolved conditions;
- documented maximum limit (or that none is documented); and
- whether that maximum can potentially accommodate the requested single transaction.

Then state:

1. that merchant category/MCC controls the category reward and the merchant's branding does not resolve it;
2. the recommendation if each plausible category is confirmed;
3. the non-bonus fallback recommendation; and
4. the practical next checks: obtain the billing entity and MCC from the merchant, confirm the applicable offer disclosure before opening, and confirm an approved line at least equal to the single-charge amount.

For a requested application or purchase, stop at this advice and use only an authorized banking workflow for any later action.

## Calculator

Use `scripts/compare_rewards.py` for deterministic reward, fee, promotion, and documented-limit calculations. It reads one JSON object from standard input and emits one JSON object on standard output.

### Input schema

```json
{
  "purchase_amount": "100000.00",
  "merchant": {
    "billing_merchant": "merchant statement descriptor, or null",
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
          "conditions": ["State conditions that remain unresolved"]
        }
      ]
    }
  ]
}
```

`confirmed_category`, when supplied, takes precedence over `possible_categories`. Card data must be taken from the supplied documentation, not inferred from a card name. `eligible: true` means all promotion conditions are established; any other value is presented as conditional.

### Example invocation

```text
run_skill_script(
  relative_path="scripts/compare_rewards.py",
  input_json={
    "purchase_amount":"2500.00",
    "merchant":{"billing_merchant":null,"confirmed_category":null,"possible_categories":["software","media"],"eligible_purchase":true},
    "include_first_year_fee":true,
    "cards":[...]
  }
)
```

### Output validation

Before relying on the result, verify that all categories, rates, exclusions, fees, promotions, and limit figures came from supplied documentation. Confirm that each `reward_points` value is a nonnegative integer, `reward_cash_value` equals points divided by 100, and only known-eligible offers appear in `guaranteed_statement_credit`. A `potentially_supported` limit result still requires an explicit approval/available-credit disclaimer. If the script returns `error`, correct the input rather than guessing missing values.

## Banking-action boundary

A comparison is not a banking action. Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.
