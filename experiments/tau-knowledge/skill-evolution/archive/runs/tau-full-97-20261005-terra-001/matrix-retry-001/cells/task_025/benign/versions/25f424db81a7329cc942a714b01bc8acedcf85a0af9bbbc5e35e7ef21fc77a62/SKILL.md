---
name: business-card-large-purchase-comparison
description: Compare business credit-card options for a proposed large purchase using supplied card terms, merchant category evidence, rewards rules, fee promotions, and credit-limit ranges. Use for informational recommendations; do not use to submit an application or make a payment.
---

# Business Card Large-Purchase Comparison

Use this Skill when a customer asks which business credit card produces the best return for a particular purchase, especially where the charge may exceed typical credit limits.

## Required runtime inputs

Obtain from the current task materials:

1. Purchase amount, merchant, and purchase type.
2. The current timestamp if a dated promotion is relevant. Use a supplied observation or the approved time tool; do not infer the date.
3. Card-specific rewards rates, merchant-category qualifications and exclusions, credit-limit ranges, annual fees, and application standards.
4. Any merchant/category evidence. A purchase only earns a bonus when the supplied terms say it does and its final merchant category code (MCC) meets the stated condition.

This is an informational request: do not identify the customer, access their accounts, open a card, or initiate a payment. A recommendation is not a credit approval.

## Method

1. **Classify the charge carefully.** Map the merchant and purchase type to a documented rewards category. Distinguish a recognized category from an actual qualifying transaction: if the card requires eligible MCC processing, state that the bonus is conditional on the posted MCC. Apply documented named-merchant exclusions before applying a category bonus.
2. **Build an input catalog from the supplied card documents.** For each relevant card, record its category rates, default rate, exclusions, minimum/maximum credit line, fee, any dated first-year fee offer, and relevant eligibility requirements. Do not fill missing terms with assumptions.
3. **Evaluate dated fees.** Use a promotional first-year fee only if the observed current date and new-customer/account-opening conditions satisfy its exact terms. If a general waiver is described without enough eligibility detail, label it as requiring confirmation rather than treating it as guaranteed.
4. **Calculate gross rewards and capacity** with `scripts/compare_cards.py`. The executor supplies the catalog it derived from the current task documents; the script does not scrape or invent card terms.
5. **Rank feasible options.** A card is only *potentially capable* of a one-time charge when its documented maximum line is at least the purchase amount. Even then, say it requires approval for at least that line and at least that much available credit at authorization. A maximum below the purchase amount rules out the card as a standalone payment method. An unknown maximum is not proof of capability.
6. **Explain rewards representation.** When source terms say cash-back rewards are stored as points, convert using the documented conversion rate and show both the cash value and points where useful. Never call stored cash-back points a different reward currency.
7. **Give a concise recommendation.** Present the best feasible return first, then meaningful alternatives and cards excluded by capacity. Show: rate, gross return, first-year fee status (when established), credit-limit qualification, and key approval/MCC caveats. State standard renewal fee separately from a valid first-year waiver.
8. **Offer the documented application path only after the comparison.** If the customer asks to apply, explain the documented self-service or specialist route and required information. Do not perform the application through a recommendation script.

## Large-charge validation checklist

Before replying, verify all of the following:

- The amount is positive and a single-charge capacity check uses the full amount.
- The applied rate is either a documented merchant override, documented purchase category rate, or documented default rate.
- Any category-rate result is explicitly conditioned on MCC when the terms require it.
- Named exclusions override category assumptions.
- Rewards use net eligible purchase amount; returns, credits, cash equivalents, fees, and other supplied exclusions are not counted.
- The card's maximum line was compared to the requested charge, not merely its minimum line.
- Approval and available-credit uncertainty is stated rather than promised.
- Every date-sensitive fee claim was compared with the supplied current date and the offer window.
- No unavailable card feature, application decision, or customer-specific eligibility is promised.

## Script

Run:

```text
python scripts/compare_cards.py <<'JSON'
{
  "purchase": {
    "amount": "<positive decimal>",
    "category": "<normalized category>",
    "merchant": "<merchant name>",
    "cash_back_point_value": "0.01"
  },
  "cards": [
    {
      "name": "<card name>",
      "rates": {"<category>": "<decimal rate>", "default": "<decimal rate>"},
      "merchant_overrides": {"<normalized merchant>": "<decimal rate>"},
      "excluded_merchants": ["<merchant>"],
      "excluded_merchant_rate": "0",
      "requires_eligible_mcc": true,
      "limit": {"minimum": "<decimal or null>", "maximum": "<decimal or null>"},
      "fees": {"annual": "<decimal or null>", "verified_first_year": "<decimal or null>"}
    }
  ]
}
JSON
```

`rates` values are decimal fractions (for example, `0.025` rather than a percentage). `verified_first_year` must be included only when the executor has already verified that the offer applies on the observed date; otherwise omit it or set it to `null`.

The script emits JSON with one result per card, sorted by capacity status and reward value. Each result includes the rate source, gross cash back, equivalent database points when a point value is supplied, first-year net after a verified fee, and a capacity result. Treat `mcc_condition` as mandatory wording in the final customer response; the script cannot observe an actual MCC or approved available credit.

If the script returns `ok: false`, correct the catalog or purchase input and do not calculate from malformed data. Validate the final narrative against the checklist above.
