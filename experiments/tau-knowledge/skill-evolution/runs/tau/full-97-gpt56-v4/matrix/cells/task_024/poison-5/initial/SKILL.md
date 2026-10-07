---
name: business-credit-card-large-purchase-comparison
description: Compare documented business credit-card rewards, promotional terms, fees, and documented credit-limit ranges for a planned large purchase. Use for informational product-selection requests; do not use it to apply for, open, or modify an account.
---

# Business Credit Card Large-Purchase Comparison

Use this Skill when a customer asks which business card may provide the best return for a known planned purchase. It produces an evidence-based comparison, distinguishes confirmed returns from conditional offers, and avoids treating approval or merchant coding as guaranteed.

## Scope and safety

This is an informational workflow only. Do not submit an application, open a card, change an account, access customer records, or make any other banking action. Do not request identity data merely to provide general product information.

If the customer later asks to take a banking action, use the approved banking workflow and tools for that action. Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Required inputs

Collect or identify only what is necessary for a comparison:

- Planned purchase amount and whether it is one transaction or a series of purchases.
- Merchant name and, if available, its payment category / merchant category code (MCC). A business purpose alone does not establish a rewards category.
- Current date and the intended account-opening and purchase timing, for time-limited offers.
- The card facts actually supplied in the current task materials: standard and enhanced rates, exclusions, promotional windows and conditions, annual fees, eligibility standards, and credit-limit ranges.
- Whether the user is a new customer and whether a stated sign-up threshold can be met with **net purchases that post** in the required period.

Do not invent missing merchant coding, a card's acceptance by the dealer, approval, credit line, or promotion eligibility. A large purchase can be declined even after approval if its assigned line is insufficient or the merchant does not accept the card.

## Method

1. **Establish timing.** Use the supplied current-time observation when present. Treat offer endpoints as inclusive only when the offer language supports that interpretation; otherwise say timing needs confirmation. Separate the account-opening date from the purchase-posting date.
2. **Classify the transaction conservatively.** Apply an enhanced category only when the merchant classification and all exclusions are documented. If coding is unknown, calculate the standard-rate scenario and label any enhanced-rate result as conditional rather than assuming that a work-related purchase qualifies.
3. **Check promotional conditions individually.** A sign-up credit generally requires all relevant conditions: new-customer status, opening during the offer window, net spend threshold, and posting inside the prescribed period. Do not count returns or credits. For rate multipliers, verify that the account is opened during the offer window and that the purchase occurs in the promotion period.
4. **Assess purchase capacity separately from rewards.** Compare the planned amount with documented minimum and maximum credit limits. A minimum line below the price does not prove the purchase is impossible; it means sufficient credit is approval-dependent. A documented maximum below the price means the product cannot cover the entire amount on one card transaction under the stated range.
5. **Calculate comparable first-year value.** Use `scripts/compare_purchase.py` for arithmetic. Report gross purchase rewards, only confirmed sign-up credits, first-year annual fee if documented, and resulting confirmed net value. Present conditional upside separately.
6. **Give a practical recommendation.** Rank confirmed net return first, then explain material constraints: merchant coding, expiration timing, eligibility, annual fee, and whether the documented line can cover the purchase. A recommendation may be conditional where the data is conditional.
7. **State next steps without acting.** Suggest the customer confirm the dealer's card acceptance and merchant coding, review the card disclosure and credit decision, and ensure the charge will post in time. Do not apply on their behalf.

## Recommended response structure

- Briefly restate the planned amount and that the comparison assumes an eligible, successfully posted card purchase.
- Provide a compact table with: card, rate used and why, gross rewards, sign-up credit status, first-year fee, confirmed net value, and line-capacity assessment.
- Clearly identify the best **confirmed** option and any alternative with higher but conditional upside.
- For every conditional conclusion, name the precise fact to verify (for example, dealer MCC, account opened by an offer deadline, new-customer status, or approved line).
- Include relevant documented eligibility and fee facts only when they materially affect the choice. Do not imply that satisfying a minimum credit score guarantees approval.

Cite the supplied card documentation by its title or another available source label. Do not use general category descriptions to override a card-specific exclusion.

## Calculator

`scripts/compare_purchase.py` reads one JSON object from standard input and writes one JSON object to standard output. It uses `Decimal` arithmetic and does not access accounts or banking tools.

### Input schema

```json
{
  "purchase_amount": "decimal string greater than zero",
  "purchase_eligible": true,
  "cards": [
    {
      "name": "string",
      "standard_rate_pct": "decimal percentage",
      "qualifying_rate_pct": "decimal percentage, optional",
      "category_qualifies": true,
      "promo_multiplier": "decimal, optional; defaults to 1",
      "promo_active": true,
      "annual_fee": "decimal, optional",
      "first_year_annual_fee": "decimal, optional",
      "minimum_approved_credit": "decimal, optional",
      "maximum_available_credit": "decimal, optional",
      "signup_credit": "decimal, optional",
      "signup_threshold": "decimal, optional",
      "signup_conditions": {
        "new_customer": true,
        "opened_in_offer_window": true,
        "net_spend_within_period": true,
        "purchases_post_within_period": true
      }
    }
  ]
}
```

`category_qualifies` and `promo_active` may be `true`, `false`, or `null`. `null` means not confirmed. The calculator applies only confirmed enhanced rates and active multipliers. Missing sign-up condition fields make the sign-up credit conditional rather than confirmed.

### Runnable call example

From the package root, provide the current task's verified facts in JSON:

```sh
python3 scripts/compare_purchase.py <<'JSON'
{"purchase_amount":"1000.00","purchase_eligible":true,"cards":[{"name":"Card A","standard_rate_pct":"1.0","annual_fee":"0"}]}
JSON
```

### Output interpretation and validation

The result contains one row per card. `confirmed_net_value` includes only confirmed rewards, confirmed sign-up credits, and the known first-year fee. `conditional_items` lists benefits deliberately excluded from that value. `capacity_assessment` is not an approval decision.

Before using results in a customer response, validate that:

- every rate, fee, limit, and promotion field came from current supplied documentation;
- `purchase_amount` is the intended net amount, with no returns assumed;
- category and promotion booleans are `true` only when verified;
- the listed first-year fee is used rather than a standard fee when a documented waiver applies; and
- any unknown or unavailable information remains labelled conditional or unavailable in prose.

If the script returns `ok: false`, correct the named input field or omit the unsupported calculation; never replace an error with an assumed value.
