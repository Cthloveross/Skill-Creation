---
name: high_value_business_card_rewards_advisor
description: Analyze a proposed high-value business-card purchase when merchant classification, exclusions, credit limits, fees, promotions, or applicant eligibility may affect the best card. Use for an advisory comparison; it does not apply for a card or make account changes.
---

# High-Value Business Card Rewards Advisor

Use this Skill to give a conditional, evidence-based card comparison for a large planned purchase. It is especially appropriate when the merchant's billing descriptor or merchant category code (MCC) is unknown.

## Scope and assumptions

This package contains the supplied rules for Business Silver, Business Gold, Business Platinum, and the Business Bronze feasibility constraint. It calculates gross cash-back value for one net purchase; it does not predict an issuer's approval decision, merchant coding, authorization outcome, posting date, or actual available credit.

For cash-back cards, database rewards expressed as points represent cash back at **100 points per dollar** (1 point = $0.01). The helper returns both values.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements. This Skill is advisory only: do not apply for a card, charge a card, change an account, or represent that any prerequisite has been verified. For a future application or charge, specifically confirm the approved and currently available line is sufficient for the full transaction and any authorization requirements.

## Required inputs to establish

Collect or preserve, without guessing:

1. Net planned purchase amount and whether it must be one transaction.
2. Merchant name and the merchant's expected processor-assigned category/MCC or an explicit statement that it is unknown.
3. Current date, prospective account-opening date, and whether the applicant is a new customer when a date-limited fee promotion is relevant.
4. Whether the applicant can meet the stated personal/business-credit thresholds and can obtain a sufficient approved credit limit.
5. Any returns, credits, split billing, platform/intermediary billing, or non-qualifying transaction features.

A product/service label does not establish the MCC. When MCC is unknown, do not name one unconditional "best" card. Explain the category-contingent outcomes and tell the customer to obtain the prospective billing category or descriptor from the merchant before relying on a bonus rate.

## Workflow

1. Build a JSON object matching `scripts/analyze_purchase.py`'s schema below. Supply dates as `YYYY-MM-DD` where known. Use `merchant_category: null` when it is not confirmed.
2. Run the helper. It validates the amount and dates, applies card-specific exclusions, identifies whether a stated maximum line can theoretically support a required single purchase, computes each rate scenario, and evaluates known first-year annual-fee waivers.
3. Convert its structured output into a concise customer answer:
   - Lead with the need for a sufficient *approved and available* credit line, not merely a published maximum.
   - State the specific rate and dollar/points value for each confirmed or conditional category.
   - Distinguish a category that is merely possible from one confirmed by merchant processing.
   - Identify named exclusions exactly. An exclusion on one card must not be assumed to apply to another card.
   - If rates are tied, say they are tied rather than inventing a ranking. Compare fees only when eligibility/date facts are known; do not subtract an annual fee from rewards unless the customer asks for net first-year value and the fee applicability is established.
   - Mention the applicable eligibility thresholds and annual-fee/promotion timing as constraints, without claiming approval.
4. If key facts remain unknown, ask the merchant to confirm the MCC/billing category and advise the customer to verify it on the posted transaction. If an issued transaction is miscoded, direct the customer to retain the receipt and seek a category review where the product terms permit it.

## Product rules incorporated by the helper

- **Business Silver:** 10% for qualifying travel/software categories and 1% otherwise. Apple is expressly excluded from the 10% software bonus and earns 1%. Published limits are $17,500–$112,500; stated eligibility is personal credit 700 and PAYDEX 47 for established businesses. Standard annual fee is $122.50. A new-customer first-year waiver applies only for accounts opened 2025-11-15 through 2026-01-15.
- **Business Gold:** 2.5% for qualifying operations MCCs and 1% otherwise. Software use alone is insufficient: processor MCC controls qualification. Published maximum line is $225,000; stated eligibility is personal credit 735 and PAYDEX 67. Annual fee is $200.
- **Business Platinum:** 4% for qualifying travel, software, or media/advertising MCCs and 1.5% otherwise. Published limits are $75,000–$400,000; stated eligibility is personal credit 765 and PAYDEX 77. Standard annual fee is $450. A new-customer first-year waiver applies only for accounts opened 2025-11-01 through 2026-02-28.
- **Business Bronze:** its published maximum line is $75,000, so it cannot support a required $100,000 purchase as one transaction. Do not treat an unrelated welcome offer as overcoming the line constraint.

All rewards are based on net purchases. Returns or credits reduce earned rewards. Fees, cash equivalents, and balance transfers are not reward-earning purchases where the relevant product rules exclude them.

## Helper interface

Run `scripts/analyze_purchase.py`, passing one JSON object on standard input. It emits one JSON object on standard output.

Input schema:

```json
{
  "purchase_amount": 100000,
  "merchant_name": "Merchant name or null",
  "merchant_category": null,
  "requires_single_transaction": true,
  "current_date": "YYYY-MM-DD or null",
  "account_open_date": "YYYY-MM-DD or null",
  "new_customer": true
}
```

`purchase_amount` must be a positive numeric amount. `merchant_category` may be `travel`, `software`, `media_advertising`, `operations`, `other`, or `null`; aliases such as `media` and `media-advertising` are accepted. Dates are optional but must be ISO dates if supplied. `account_open_date` is used for fee-waiver evaluation; if absent, the current date is used only as a planning assumption and is disclosed in output.

Output highlights:

- `cards`: a per-card result containing support feasibility, conditions, earnings scenarios, eligibility, and fee information.
- `decision_guidance`: category-specific rate rankings that must remain conditional until the MCC is confirmed.
- `unresolved_items`: facts that prevent a definitive recommendation.
- `errors`: present instead of an analysis for invalid inputs.

Example executor call (illustrative only; replace all values with the current request):

```json
{"purchase_amount": 25000, "merchant_name": "Example Merchant", "merchant_category": null, "requires_single_transaction": true, "current_date": "2026-01-01", "account_open_date": null, "new_customer": true}
```

## Validation before responding

Check that the helper returned no `errors`, the amount is the user's net one-transaction amount, and all dollar rewards equal `purchase_amount × rate` rounded to cents. Confirm that any card described as viable has a published maximum at least as large as a required single transaction; still state that actual approval and available credit are unconfirmed. Do not call a category confirmed merely because the merchant sells a matching service.