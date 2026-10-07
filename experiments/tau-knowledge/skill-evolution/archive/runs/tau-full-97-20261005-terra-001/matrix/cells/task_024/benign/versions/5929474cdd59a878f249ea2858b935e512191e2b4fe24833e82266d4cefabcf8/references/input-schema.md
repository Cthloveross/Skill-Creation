# Business-card comparison calculator input

Pass one JSON object to `scripts/evaluate_business_card_options.py`.

```json
{
  "purchase_amounts": ["decimal amount for each separately rounded charge"],
  "purchase_category": "normalized documented category, or null if not confirmed",
  "merchant_name": "merchant name, or null",
  "as_of_date": "YYYY-MM-DD or timestamp beginning YYYY-MM-DD",
  "opening_date": "YYYY-MM-DD or null",
  "new_customer": true,
  "products": [
    {
      "name": "card name",
      "annual_fee": "decimal",
      "eligibility": {
        "personal_credit_min": 0,
        "business_credit_min": 0,
        "business_credit_scale": "optional scale"
      },
      "credit_limit": {"min": "decimal or null", "max": "decimal"},
      "default_rate_percent": "decimal percentage",
      "reward_rules": [
        {
          "categories": ["category labels"],
          "rate_percent": "decimal percentage",
          "label": "display label"
        }
      ],
      "merchant_rate_overrides": [
        {
          "merchants": ["merchant names"],
          "rate_percent": "decimal percentage",
          "label": "display label"
        }
      ],
      "first_year_fee_offers": [
        {
          "start": "YYYY-MM-DD",
          "end": "YYYY-MM-DD",
          "fee": "decimal",
          "requires_new_customer": true,
          "requires_good_standing": true
        }
      ],
      "reward_promotions": [
        {
          "start": "YYYY-MM-DD",
          "end": "YYYY-MM-DD",
          "multiplier": "decimal",
          "requires_open_during": true,
          "requires_new_customer": true,
          "duration_months": 6
        }
      ],
      "statement_credit_offers": [
        {
          "start": "YYYY-MM-DD",
          "end": "YYYY-MM-DD",
          "credit": "decimal",
          "net_purchase_threshold": "decimal",
          "period_months": 2,
          "requires_open_during": true,
          "requires_new_customer": true,
          "purchases_must_post": true
        }
      ]
    }
  ]
}
```

## Interpretation

- Rates are percentages: use `1.5` for 1.5%, not `0.015`.
- `purchase_amounts` models separately charged transactions. The calculator floors fractional reward points for each amount before totaling them. Provide one amount for a single charge.
- If dealer MCC/category is unknown, use `purchase_category: null`. Output will include the default scenario and enhanced scenarios marked as conditional. Do not select a category based solely on what was purchased.
- Category and merchant matching are case-insensitive after whitespace normalization. A matching named merchant override takes precedence over a category rule.
- `opening_date` controls account-opening offers. Use `null` if it is genuinely unknown; do not substitute the current date. Set `new_customer` to `null` if unknown.
- Offer windows are inclusive. For a statement credit, `threshold_met_by_planned_purchases` means only that the planned net amount is sufficient; it does not prove that qualifying purchases will post in time or that the offer will be fulfilled.
- A first-year fee offer needs `start` and `end` because it is an account-opening offer. A reward promotion with `requires_open_during: true` is also evaluated against the opening date. If it has `duration_months`, the calculator reports its opening-date duration but cannot prove a future charge will post within it.
- `first_year_net_cash_value` is gross cash-back value minus the listed first-year fee. It does not include conditional statement credits.
- All published-limit results are screening results only, not an approval or line guarantee.
