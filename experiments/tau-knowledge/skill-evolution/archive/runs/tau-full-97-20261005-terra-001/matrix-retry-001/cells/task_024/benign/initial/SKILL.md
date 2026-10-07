---
name: business-card-large-purchase-comparison
description: Compare available business credit-card rewards, introductory offers, published eligibility, and stated credit-limit ranges for a prospective large purchase when merchant category coding and applicant credit details may be unknown. Use for informational card-selection conversations; it does not apply for cards, approve credit, or promise a reward.
---

# Business Card Large-Purchase Comparison

Use this skill when a customer asks which business card could provide the best return on a planned purchase. It is especially useful when the purchase amount is large enough that the approved credit limit, merchant category, new-customer status, offer dates, and purchase-posting timing materially affect the outcome.

## Required facts and assumptions

1. Obtain or preserve the purchase amount, the current date (or account-opening date), whether the customer will be new to the product, and the merchant category if known. A merchant category is determined by the merchant/payment processor, not by the item description.
2. Do **not** infer a category from a description such as “truck,” “equipment,” or “business purchase.” If the category is unknown, describe category-dependent results as contingent.
3. Treat a published credit-limit range as an underwriting range, never as a promised limit or proof that the entire charge will be approved. The merchant must also accept the desired card amount.
4. Treat missing FICO/PAYDEX information as unknown eligibility, not approval or denial. An industry-specific product remains conditional on the applicant being in its stated target industry.
5. An introductory reward or statement credit is conditional on every published condition: offer dates, new-customer status, account opening, claim/activation where required, net qualifying purchases, and posting within the stated time window.

## Procedure

1. Create a JSON input for `scripts/compare_cards.py` using the schema below. Copy the public current date rather than guessing it. Supply `purchase_category` only when the merchant has confirmed it.
2. Run the script. It uses the packaged `references/card_catalog.json` and calculates cash-back points by flooring each purchase’s fractional points. Cash-back cards use 100 points per dollar.
3. Use `baseline_points` for a known non-bonus/unknown category comparison. For a known category, use `purchase_points`. Use `conditional_offers` only after clearly stating their conditions. For an unknown category, use `possible_bonus_outcomes` to explain what confirmation could change, rather than presenting the highest theoretical rate as expected.
4. Explain the leading realistic alternatives in plain language:
   - a broadly applicable option and its conditional introductory value;
   - a category-dependent option when its higher rate could exceed it;
   - any product with a materially higher category/promo rate only as a narrow, explicitly conditioned possibility.
5. State the next checks: merchant acceptance of the full charge, exact processor category, confirmed approved limit, applicant scores/business eligibility, and promo terms. Mention that returns/credits reduce qualifying spend and rewards.

For the supplied catalog, a prospective purchase during the Business Bronze introductory-offer window can receive the standard 1% plus a conditional $500 statement credit after $10,000 in net purchases in two months. Business Gold can exceed that only when the merchant is actually coded as Operations. Do not state either result as guaranteed.

## Script input

Send one JSON object on stdin:

```json
{
  "purchase_amount": 40000,
  "current_date": "YYYY-MM-DD",
  "account_open_date": "YYYY-MM-DD",
  "purchase_category": null,
  "merchant_name": null,
  "new_customer": true,
  "purchase_posts_within_days": null,
  "personal_fico": null,
  "business_paydex": null,
  "business_industry": null,
  "promo_claimed": null
}
```

`purchase_amount` must be positive. `current_date` is required. Dates accept an ISO date or a timestamp beginning with `YYYY-MM-DD`. Categories are case-insensitive and must be one of the catalog category names when provided. `purchase_posts_within_days` is used to assess two-month welcome-offer timing; leave it null when not known. `promo_claimed` applies to the Silver Zoom triple-cash-back offer.

Example runnable call from a compatible executor:

```text
run_skill_script("scripts/compare_cards.py", {
  "purchase_amount": 40000,
  "current_date": "2025-11-14",
  "account_open_date": "2025-11-14",
  "purchase_category": null,
  "merchant_name": null,
  "new_customer": true,
  "purchase_posts_within_days": null,
  "personal_fico": null,
  "business_paydex": null,
  "business_industry": "landscaping",
  "promo_claimed": null
})
```

The example is illustrative only; always use the customer’s actual facts.

## Script output and validation

The script emits one JSON object with `ok: true`, a cents/points calculation, and one record per card. Monetary cash-back values are represented by whole `points` (one point is $0.01), avoiding floating-point rounding. `reasons` and `conditions` identify why an amount or promotion is conditional. A valid output has:

- `ok` equal to `true`;
- nonnegative integer `baseline_points`, `purchase_points` where present, and offer `points`/`cents` values;
- an `eligibility` and `credit_limit_fit` object for every card;
- no recommendation that claims an unconfirmed merchant category, promotional condition, underwriting decision, or merchant acceptance.

If `ok` is `false`, correct the listed `errors` before relying on the comparison. If a product, promotion, MCC, or merchant exception is not covered by the catalog, say that it cannot be determined from the supplied terms and direct the customer to support or the merchant for confirmation.

## Customer-facing guardrails

Do not apply for a card or alter an account. Do not request account credentials or perform identity verification for this general product-information request. Do not claim a card will cover a charge, that an offer is activated, or that a merchant will be classified in a particular way. Explain that rewards generally post after transactions post and clear, and returns or credits reduce rewards.
