---
name: business-card-large-purchase-advisor
description: Compare supported business credit-card options for a planned large purchase, calculate conditional rewards, and communicate underwriting, merchant-category, and promotion constraints without promising approval. Use for prospective-card questions where the merchant coding, purchase amount, and applicant eligibility may be incomplete.
---

# Business Card Large-Purchase Advisor

Use this Skill to provide a careful product comparison for a planned business charge. It distinguishes a published card limit range from an approved and currently available credit line, and distinguishes a guaranteed reward rate from a rate that depends on merchant coding.

## Inputs

Run `scripts/card_advisor.py` with JSON on stdin. Schema:

```json
{
  "purchase": {
    "amount": 100000,
    "merchant_name": "merchant name",
    "direct_brand": "optional billing brand",
    "category": "optional processor/MCC category"
  },
  "applicant": {
    "personal_credit_score": null,
    "business_paydex": null,
    "established_business": null
  },
  "as_of": "optional YYYY-MM-DD"
}
```

`amount` must be a positive number. `category` is optional and may be a category name such as `travel`, `software`, `media`, or `operations`. Use `null` when the payment processor category/MCC is not known. Applicant fields are optional; omission means eligibility cannot be determined, not that the applicant is ineligible.

The script emits JSON with:

- `options`: card-by-card rates, cash-back values, stored reward-point equivalents, eligibility status, and limit feasibility.
- `recommendation`: the option with the highest non-contingent calculated return among cards whose published maximum can accommodate the purchase, when one can be identified.
- `suggested_reply`: customer-ready comparison language.
- `needed_confirmations`: information required before stating a contingent rate or that a charge can be completed.

For cash-back cards, database reward points represent cents of cash back: one point equals $0.01. Thus a calculated $1.00 cash-back reward is represented by 100 stored points.

## Method

1. Identify the single purchase amount and whether it must fit on one card. A published maximum at or above the amount means only that the product *may* be able to support it; approval and available credit are still required.
2. Treat the merchant category/MCC as controlling for category bonuses. Do not infer a qualifying category from a merchant name, the item description, or the customer’s expectation.
3. Apply explicit merchant exclusions before a general software bonus. In particular, a direct Apple/Apple Music bill is not eligible for the Business Silver software bonus and earns its standard rate.
4. Compare each card’s ordinary rate and every applicable conditional rate. Label a result as conditional if coding is unknown or unverified.
5. Check the stated personal-score and, for established businesses, PAYDEX thresholds only when the customer supplied those facts. Never claim that meeting thresholds guarantees approval, a credit limit, or a particular available balance.
6. If the transaction must be made immediately, make clear that opening a card does not ensure a sufficient line will be approved and available in time. Recommend confirming the approved line and the merchant’s payment-processor category before relying on the card.
7. Discuss fees and promotional waivers only with their eligibility conditions and dates. Do not apply for a card, alter an account, or imply that an application has been submitted.

## Customer response requirements

Use `suggested_reply` as a factual base, then answer in clear prose:

- Lead with the best non-contingent comparison and separately state the higher possible return only where its qualifying coding is confirmed.
- State that the large charge requires an approved line and sufficient available credit, rather than treating the product maximum as a promise.
- State the score/PAYDEX requirements for any recommended product, or say that they must be checked if applicant data is missing.
- For an unknown MCC, ask the merchant or processor to confirm the category before the purchase. Do not tell the customer Apple Music will code as Media or Software.
- If a first-year fee waiver is in effect as of the supplied date, say it applies only to eligible new accounts opened in its published window and disclose the later standard annual fee.

If the customer asks to apply, direct them to the normal application channel described for the product. Application and underwriting decisions must use the declared banking workflow; this Skill only provides an informational comparison.

## Runnable example

```bash
python scripts/card_advisor.py <<'JSON'
{"purchase":{"amount":25000,"merchant_name":"Example vendor","direct_brand":null,"category":null},"applicant":{"personal_credit_score":null,"business_paydex":null,"established_business":null},"as_of":"2025-12-01"}
JSON
```

## Validation

Before using the output, confirm that `purchase.amount` matches the proposed one-time charge, inspect `needed_confirmations`, and ensure each advertised bonus is labeled confirmed only when the supplied category establishes it. Reject script output containing `error` and obtain corrected input rather than guessing. For any recommendation, verify that `limit_assessment` says `published_max_can_cover`; even then, preserve the approved-line and available-credit caveat.
