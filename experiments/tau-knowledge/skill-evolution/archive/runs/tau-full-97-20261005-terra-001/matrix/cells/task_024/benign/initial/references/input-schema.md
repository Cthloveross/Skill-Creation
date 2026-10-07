# Comparison calculator input schema

Pass one JSON object to `evaluate_business_card_options.py`.

```json
{
  "purchase_amounts": ["decimal amount for each separately rounded charge"],
  "purchase_category": "documented category label, or null when not confirmed",
  "merchant_name": "optional merchant name, or null",
  "as_of_date": "YYYY-MM-DD or timestamp beginning with YYYY-MM-DD",
  "opening_date": "YYYY-MM-DD or null",
  "new_customer": true,
  "products": [
    {
      "name": "card name",
      "annual_fee": "decimal annual fee",
      "eligibility": {
        "personal_credit_min": 0,
        "business_credit_min": 0,
        "business_credit_scale": "optional scale name"
      },
      "credit_limit": {"min": "decimal or null", "max": "decimal"},
      "default_rate_percent": "decimal percentage",
      "reward_rules": [
        {"categories": ["exact normalized category labels"], "rate_percent": "decimal percentage", "label": "optional display label"}
      ],
      "merchant_rate_overrides": [
        {"merchants": ["case-insensitive merchant names"], "rate_percent": "decimal percentage", "label": "optional exclusion label"}
      ],
      "first_year_fee_offers": [
        {
          "start": "YYYY-MM-DD",
          "end": "YYYY-MM-DD",
          "fee": "decimal fee charged in first year",
          "requires_new_customer": true,
          "requires_good_standing": true
        }
      ],
      "reward_promotions": [
        {
          "start": "YYYY-MM-DD",
          "end": "YYYY-MM-DD",
          "multiplier": "decimal multiplier",
          "requires_open_during": true,
          "requires_new_customer": true,
          "duration_months": 6
        }
      ]
    }
  ]
}
```

All rates are percentages: use `1.5` for 1.5%, not `0.015`. Omit optional arrays or set them to `[]` when the documents contain no such terms. Preserve documented conditions in the input rather than converting unknowns to favorable values.

## Interpretation

- `purchase_amounts` must contain positive amounts. Separate entries model separate transactions because rewards are floored per transaction.
- Category matching is case-insensitive but otherwise exact after whitespace normalization. If merchant coding is uncertain, set `purchase_category` to `null`; the calculator returns a default-rate scenario plus any enhanced possibilities.
- Merchant overrides take precedence over category rules. Use them for named exclusions or named special rates documented for a card.
- `as_of_date` controls whether an offer can be opened now. `opening_date` controls account-opening requirements and promotion duration. The script does not assume that an omitted opening date equals the current date.
- Use `new_customer: null` when that condition is unknown. The result will mark relevant offers conditional instead of treating them as qualified.
- The `credit_limit` result is an amount-versus-published-range screen only. It must be worded as subject to underwriting and assigned limit.

For a cash-back product represented operationally as points, `points` in output are whole points and `cash_value` is points divided by 100. The calculator emits fee information but does not assert that a fee waiver applies when required facts are unknown.
