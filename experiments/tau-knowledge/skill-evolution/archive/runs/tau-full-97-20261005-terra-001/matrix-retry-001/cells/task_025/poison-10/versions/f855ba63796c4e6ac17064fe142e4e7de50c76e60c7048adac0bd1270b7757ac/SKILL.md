---
name: business-card-purchase-reward-comparison
description: Compare documented business credit-card reward outcomes for a planned purchase when merchant category coding, merchant-specific exclusions, credit-line capacity, annual fees, and promotions may affect the result. Use for advisory card-selection questions; do not use it to submit an application, open an account, or make a charge.
---

# Business Card Purchase Reward Comparison

## Scope

Use this Skill to give a conditional, evidence-based comparison of cards for one planned purchase. It is especially useful when the merchant category code (MCC), billing entity, approved credit line, or promotion eligibility is unknown.

This is an advisory workflow only. Do not imply that a merchant will receive a particular MCC, that an application will be approved, or that a proposed charge will be authorized.

## Required inputs

Collect or derive from the supplied card documentation:

- Purchase amount and whether it is one transaction or multiple transactions.
- Billing merchant name, if known; do not assume a brand name is the statement descriptor.
- Confirmed MCC/category, or a clearly labeled set of plausible categories.
- For each card: base rate, bonus rates by category, exclusions, annual fee (including any applicable first-year fee), documented credit-limit range, and promotion terms.
- For each promotion: opening-date window, new-customer requirement, spending threshold, posting deadline, net-purchase treatment, reward amount, and whether the user is known to satisfy each condition.
- The current date only when assessing time-bounded terms.

If an input is absent, retain it as unknown rather than inventing a favorable assumption.

## Method

1. Determine whether the transaction is an eligible purchase. Cash equivalents, fees, balance transfers, returns, and credits must be treated according to the governing card terms rather than as ordinary qualifying spend.
2. Identify the billing merchant and the actual or possible merchant category. Merchant category coding controls category-based rewards; the product or service description alone is insufficient.
3. Check merchant-specific exclusions independently from category eligibility. Apply an exclusion only when the documented excluded merchant matches the known billing merchant. If the statement descriptor is unknown, describe the exclusion as a risk rather than asserting it applies.
4. For every supported category scenario, calculate rewards in points as `floor(purchase_amount × rate_percent)`. For cash-back cards represented in points, convert points to cash value at `$0.01` each. Floor each single transaction before converting.
5. Subtract the applicable first-year annual fee only when comparing net first-year value. Keep ongoing annual fees separate.
6. Add a promotional statement credit only if all documented conditions are known to be met. Otherwise show it as conditional, not guaranteed.
7. Assess credit-line fit separately from rewards. A documented maximum at or above the purchase amount means the card can *potentially* support the charge; it does not establish approval or an assigned limit. A maximum below the purchase amount rules out a single charge at that amount.
8. Recommend a card only conditionally when category coding, merchant exclusion status, credit-line capacity, and promotion eligibility are unresolved. State the conditions that would change the recommendation.

## Running the calculator

Use `scripts/compare_rewards.py` for deterministic scenario math. It receives one JSON object on stdin and emits one JSON object on stdout.

### Input schema

```json
{
  "purchase_amount": "decimal string",
  "merchant": {
    "billing_merchant": "known statement/billing merchant or null",
    "confirmed_category": "category or null",
    "possible_categories": ["category"],
    "eligible_purchase": true
  },
  "include_first_year_fee": true,
  "cards": [
    {
      "name": "card label",
      "base_rate_percent": "decimal string",
      "category_rates_percent": {"category": "decimal string"},
      "excluded_merchants": ["exact documented billing merchant"],
      "first_year_annual_fee": "decimal string",
      "credit_limit_min": "decimal string or null",
      "credit_limit_max": "decimal string or null",
      "promotions": [
        {
          "name": "promotion label",
          "eligible": true,
          "statement_credit": "decimal string",
          "conditions": ["conditions still relevant to disclose"]
        }
      ]
    }
  ]
}
```

`confirmed_category` takes precedence over `possible_categories`. Set `eligible_purchase` to `false` only when the transaction is known to be ineligible. Provide only documented rates and fees; the calculator does not look up card terms.

### Runnable call example

```text
run_skill_script(
  relative_path="scripts/compare_rewards.py",
  input_json={"purchase_amount":"2500","merchant":{"billing_merchant":null,"confirmed_category":null,"possible_categories":["media","software"],"eligible_purchase":true},"include_first_year_fee":true,"cards":[...]}
)
```

### Output interpretation and validation

The result contains a result for every card and category scenario, including awarded `reward_points`, `reward_cash_value`, fee, guaranteed statement credits, net first-year value, conditional promotions, exclusion status, and a credit-limit assessment.

Before using the output in a customer response, verify that:

- every scenario corresponds to a documented possible or confirmed MCC/category;
- all rates, fees, limit ranges, exclusions, and offer dates came from the applicable card documentation;
- `reward_points` is a nonnegative integer and equals the transaction-level floor calculation;
- `reward_cash_value` equals points divided by 100;
- promotions shown in `guaranteed_statement_credit` have known eligibility, while unresolved offers remain under `conditional_promotions`;
- a card is not presented as able to fund the purchase unless its documented maximum is at least the single-charge amount and the assigned limit remains explicitly unknown.

If the script emits an `error` object, correct the supplied amounts or required card fields and rerun it. Do not silently substitute missing values.

## Customer-response structure

1. Lead with the key uncertainty: the reward rate follows the billing merchant's MCC and any named exclusions.
2. Give a compact scenario table: card, conditions, rewards, first-year fee, conditional credits, net value, and credit-line fit.
3. State the best option for each plausible category rather than collapsing uncertainty into one answer.
4. Explain how the user can resolve the outcome: ask the merchant which entity will bill the charge and what MCC/category will be used, and confirm the approved credit line after underwriting.
5. Note relevant direct-billing, posting, returns/credits, and merchant-exclusion conditions from the card terms.
6. Do not submit an application, promise approval, or direct the user to split a charge to evade a limit.

## Banking-action boundary

A recommendation is not a banking action. If the conversation moves to an application, account change, card issuance, payment, charge, or another account action, stop this advisory workflow and use the authorized banking procedure.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.
