---
name: business-card-purchase-return-comparison
description: Compare documented business credit-card options for a planned purchase, including category uncertainty, annual fees, promotional timing, credit-limit fit, and stated credit eligibility. Use for informational card-selection questions; do not submit applications or make account changes.
---

# Business Card Purchase-Return Comparison

Use this skill for an informational question about which documented business card may return the most on a proposed purchase. It does not apply for submitting an application, opening an account, or making a charge.

## Guardrails and assumptions

Do not promise approval, a credit limit, card acceptance, a reward category, or a reward amount. Rewards depend on the merchant category code (MCC), eligible net purchase amount after returns/credits, exclusions, and the customer's eligibility. The purchaser's business industry does not establish the dealer's MCC.

For cards that store cash-back rewards as points, 1 point represents $0.01 of cash back. Thus, a calculated cash-back dollar amount times 100 is the stored-points equivalent.

Use only the terms documented for the cards below. A missing term is unknown—not zero and not an assumption to make.

| Card | Documented reward treatment | Documented fit / pricing terms |
|---|---|---|
| Business Platinum Rewards | 4.0% on Travel, Software, and Media advertising; 1.5% on other purchases | $450 standard annual fee; new-customer first-year fee is $0 for accounts opened 2025-11-01 through 2026-02-28; personal 765, PAYDEX 77, approved limits $75,000–$400,000; carried-balance APR 16.99% |
| Business Gold Rewards | 2.5% on Operations; 1.0% on other purchases | $200 annual fee; personal 735, PAYDEX 67, limits $37,500–$225,000; carried-balance APR 17.99% |
| Silver Zoom | 3.0% on sector-specific spending; 1.0% on other eligible purchases; 10.0% reduction at participating fuel stations | $74.50 annual fee; stated personal 680 and business 57 criteria; it is designed for transportation and logistics businesses |
| Business Bronze Rewards | 1.0% on eligible purchases; specified exclusions can earn 0% | $37 redemption threshold; no annual fee, credit limit, or credit-standard term is supplied here |
| Green Rewards | No reward rate is supplied here | Personal 690, PAYDEX 42, annual fee $100, purchase APR 19.99%, limits $14,000–$75,000 |

Do not treat a vehicle, equipment, supplies, or other business purchase as any bonus category merely from its description. For an unconfirmed merchant category, compare documented non-bonus/default treatment. Show a bonus-rate calculation only as conditional on the merchant confirming the appropriate MCC and transaction eligibility. Do not treat Silver Zoom's fuel-station discount as a discount on a vehicle purchase.

## Workflow

1. Identify the net proposed charge, expected charge/account-opening date, new-customer status, merchant acceptance/surcharges or caps, and the merchant's expected MCC. Ask for missing facts rather than inferring them.
2. Identify the requested credit line and the applicant's personal/business credit information if they wish to assess stated eligibility. Compare them to the documented thresholds and ranges, marking unavailable facts as unresolved. A stated minimum line below the purchase means the full charge is not assured.
3. For each card with a documented rate, create a baseline scenario using its documented default/non-bonus rate. State the MCC/eligibility assumption. Add separate conditional scenarios only for documented bonus rates that the merchant might actually confirm.
4. Determine the first-year fee from the documented promotion and date. State promotion conditions and subsequent-year fees. If a fee is not documented, do **not** enter $0 or produce a net-value ranking for that card.
5. Run `scripts/compare_returns.py` with the scenarios. Present gross rewards and rank only options whose applicable first-year fee is known. Keep conditional scenarios separate from baseline options.
6. Make a qualified recommendation based on the best documented baseline return that also has a plausible documented limit and eligibility fit. If facts are insufficient, say what must be confirmed rather than selecting a card.
7. Offer practical next checks: confirm the dealer accepts the card, the full amount may be charged without a surcharge/cap, expected MCC and eligibility, the applicant's credit profile, financial capacity, and the eventual approved limit. Do not claim that an application or purchase occurred.

## Script interface

Run `scripts/compare_returns.py` with JSON on stdin:

```json
{
  "purchase_amount": "40000.00",
  "options": [
    {
      "name": "Card A baseline",
      "cashback_rate_percent": "1.5",
      "first_year_annual_fee": "0",
      "classification": "baseline",
      "assumptions": ["Merchant is not confirmed to be a bonus category"]
    },
    {
      "name": "Card B, fee unavailable",
      "cashback_rate_percent": "1.0",
      "classification": "baseline",
      "assumptions": ["Annual fee is not documented"]
    }
  ]
}
```

`purchase_amount` and `cashback_rate_percent` are required nonnegative decimal strings or JSON numbers; rate must not exceed 100. `first_year_annual_fee` is optional. When it is omitted or `null`, output still includes gross rewards but sets `first_year_net_value` to `null`, lists the card in `unranked_options`, and excludes it from `ranking`. When supplied, the fee must be nonnegative. The output contains currency-rounded `gross_cash_back`, `first_year_net_value` when calculable, stored-points equivalent, classification, assumptions, a descending known-net-value `ranking`, and `unranked_options`. Invalid JSON or malformed fields produces `{"error": "..."}` and a nonzero exit.

Before presenting results, validate that the purchase amount is net eligible spend, the rate matches the documented category, the fee and promotion match the date/customer facts, and each MCC-dependent outcome is labeled conditional.

## Banking-action safeguard

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

This skill is informational. If a later request asks to apply, open an account, charge a card, redeem rewards, or change an account, do not perform it merely because of this comparison. First satisfy the applicable prerequisite checks above and use only declared normal banking tools and any required confirmation process.
