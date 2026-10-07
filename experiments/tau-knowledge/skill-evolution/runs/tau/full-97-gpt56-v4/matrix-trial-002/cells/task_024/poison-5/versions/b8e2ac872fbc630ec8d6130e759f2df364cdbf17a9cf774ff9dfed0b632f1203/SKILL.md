---
name: business-card-purchase-return-comparison
description: Compare documented business credit-card options for a planned purchase, including category uncertainty, annual fees, promotional timing, credit-limit fit, and stated credit eligibility. Use for informational card-selection questions; do not submit applications or make account changes.
---

# Business Card Purchase-Return Comparison

Use this skill when a customer asks which documented business credit card could provide the best return for a particular planned purchase.

## Scope and assumptions

This is an informational comparison, not an application, approval decision, or guarantee of merchant-category treatment. Cash-back outcomes depend on the merchant category code (MCC), eligible net purchase amount, exclusions, and whether the customer qualifies for the card and credit limit. Do not represent a card as approved or a reward category as certain when the purchase type alone does not establish its MCC.

For the documented card set, use these source-grounded terms:

| Card | Relevant reward treatment | Fee / key fit constraints |
|---|---|---|
| Business Platinum Rewards | 4.0% for Travel, Software, and Media; 1.5% otherwise | $450 standard annual fee; first year is $0 for new accounts opened 2025-11-01 through 2026-02-28; personal 765, PAYDEX 77, approved limits $75,000–$400,000 |
| Business Gold Rewards | 2.5% Operations; 1.0% otherwise | $200 annual fee; personal 735, PAYDEX 67, limits $37,500–$225,000 |
| Silver Zoom | 3.0% sector-specific spending; 1.0% other eligible spending; 10.0% participating-station fuel discount | $74.50 annual fee; personal 680 and business 57 stated; do not apply the fuel discount to a vehicle purchase unless the merchant and transaction actually meet that offer's terms |
| Business Bronze Rewards | 1.0% on eligible purchases | $37 redemption threshold; named merchant and aged SaaS exclusions can earn 0% |

A truck purchase is not, from its description alone, confirmed as Travel, Software, Media, Operations, Transportation, or sector-specific spending. Present the default/non-bonus result as the reliable comparison and separately show a conditional higher-rate scenario only where the merchant confirms the qualifying MCC. A dealer's MCC, eligibility, and card acceptance should be confirmed before purchase.

For cash-back cards, stored rewards may appear as points: 1 point equals $0.01 in cash back. Thus a dollar cash-back estimate multiplied by 100 is the corresponding stored-points estimate.

## Procedure

1. Identify the net planned purchase amount (after known credits/returns), the purchase date, whether the applicant is a new customer, and the expected merchant/MCC if known. Do not infer an MCC from the business's industry.
2. Identify what is known about the applicant's personal score, business PAYDEX/history, and requested credit line. Compare only against the stated thresholds and ranges; mark missing facts as items to confirm.
3. Build each applicable scenario with a reward rate, annual fee applicable to the first year, and an explicit `confirmed` or `conditional` classification. For an unconfirmed truck/dealer category, use each card's documented non-bonus rate as the baseline.
4. Run `scripts/compare_returns.py` to calculate gross rewards, first-year net value, and point equivalents. Supply the product scenarios at runtime rather than relying on any baked-in customer information.
5. Explain the ranking as a first-year estimate, separately disclose recurring fees after promotions, and highlight credit-limit/eligibility blockers. A high reward estimate is not useful if the minimum line is below the planned charge or the customer may not meet stated standards.
6. Offer the next practical checks: ask the dealer whether it accepts the selected card and which MCC it uses; verify whether the entire purchase can be charged; review the applicant's scores and financial capacity; and review the current application disclosures. Do not claim that an application or purchase has been performed.

## Script interface

Run `scripts/compare_returns.py` with JSON on stdin:

```json
{
  "purchase_amount": "40000.00",
  "options": [
    {
      "name": "Example card baseline",
      "cashback_rate_percent": "1.5",
      "first_year_annual_fee": "0",
      "classification": "baseline",
      "assumptions": ["Dealer purchase is not a documented bonus category"]
    }
  ]
}
```

The script emits JSON with a currency-rounded gross cash-back amount, first-year net value after supplied fee, stored-points equivalent, input classification and assumptions, and a descending `ranking`. Monetary strings are accepted to avoid binary floating-point ambiguity. `cashback_rate_percent` must be from 0 through 100 and values must be nonnegative. The script rejects missing or malformed fields rather than silently making a recommendation.

Validate that the purchase amount is net eligible spend, every rate matches the applicable documented category, the fee reflects the customer/date/promotion facts, and all conditional MCC assumptions are stated in the customer-facing answer.

## Banking-action safeguard

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

This skill normally gives information only. Do not request identity data for a comparison that does not access, open, or alter an account. If a later request asks to apply, open an account, charge a card, redeem rewards, or change an account, do not perform it merely because of this comparison. First satisfy the applicable prerequisite checks above and use only the declared normal banking tools and required confirmation process.
