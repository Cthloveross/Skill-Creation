---
name: business-card-large-purchase-recommendation
description: Compare business credit-card options for a large planned purchase, including capacity, merchant-category eligibility, time-bounded promotions, fees, and cash-back calculations. Use when a customer asks which business card gives the best return but qualification or merchant coding may be uncertain.
---

# Business Card Recommendation for a Large Purchase

Provide an informational comparison; do not apply for a card, promise approval, or represent a tentative merchant category as guaranteed. No identity verification or account lookup is needed for a general product comparison.

## Required inputs

Collect or identify:

1. The one-time net purchase amount and whether it must be charged in one transaction.
2. Merchant/service and the likely merchant category, if known.
3. The current date and each relevant offer's open and close dates.
4. The candidate cards' approved-limit ranges, rewards rules, annual fees, underwriting requirements, and exclusions.
5. Whether the customer values gross rewards only or rewards net of a first-year annual fee.

For a single charge, an advertised maximum limit is not enough: explain that the customer needs an *approved credit line and available credit* at least equal to the charge when it posts.

## Method

1. **Screen for transaction capacity.** Exclude a card when its documented maximum is below the purchase amount. Mark a card whose maximum can cover the amount as conditional on approval and available credit; do not imply that the maximum will be granted.
2. **Classify conservatively.** Rewards depend on the payment processor's merchant category code (MCC), not merely the customer’s business purpose, merchant name, or product description. Apply named exclusions exactly. An exclusion for one product type does not establish treatment for a different product from the same brand.
3. **Separate documented outcomes.** For each viable card, show:
   - the documented/base outcome;
   - a higher outcome only if the required category is actually confirmed; and
   - why an unconfirmed category should not be used as the recommendation's promised return.
4. **Apply promotions only after eligibility checks.** Check account-opening timing, new-customer condition, duration, and whether the promotion multiplies both bonus and ordinary rates. State the timing risk if opening/application approval near an offer cutoff is not documented.
5. **Calculate transparently.** Cash-back dollars equal `purchase amount × rate / 100`. If comparing net first-year value, subtract only a fee that is documented as applicable; separately disclose gross cash back. Use `scripts/compare_rewards.py` for rounding and ranking after the facts are established.
6. **Recommend conditionally.** Name the best documented option under stated conditions, then provide a fallback when the leading card cannot supply enough credit or the promotion is missed. Mention material underwriting thresholds for cards that are otherwise suitable.

## Apple Music / large-business-purchase analysis

When the customer describes a company-wide Apple Music subscription, use these guardrails from `references/business_card_rules.md`:

- Streaming services are described as an **entertainment** category, while software is a distinct category. Do not call the subscription software merely because it is digital or recurring.
- Business Silver's Apple exclusion is for Apple as a hardware/electronics merchant. It does not itself answer how an Apple Music subscription is categorized. Nor does it make Apple Music eligible for the 10% software rate.
- Business Platinum's enhanced media treatment is for travel, software, and media advertising. Examples of qualifying streaming media concern advertising placements, not an ordinary streaming subscription. Therefore, use Platinum's 1.5% ordinary rate unless the issuer/merchant confirms a qualifying enhanced MCC.
- Business Gold's operations rate also depends on operations coding. Its guidance identifies entertainment, personal, or non-business coded transactions as non-qualifying; do not promise 2.5% for a music subscription without confirmed operations coding.

For the documented date of **2025-11-14**, the useful comparison for a $100,000 single purchase is:

| Card | Capacity assessment | Conservative cash back | Important conditional result |
| --- | --- | ---: | --- |
| Business Silver | Its $17,500–$112,500 range can cover the charge only if approval and available credit are at least $100,000. | $1,000 at 1%; $2,000 if the same-day double-cash-back promotion is valid for the newly opened account. | $10,000 at 10%, or $20,000 under the multiplier, requires actual qualifying travel/software coding and must not be promised for Apple Music. |
| Business Platinum | Its $75,000–$400,000 range can cover the charge, conditional on approval and available credit. | $1,500 at 1.5%. | $4,000 requires confirmed qualifying travel, software, or media-advertising coding. |
| Business Gold | Its $37,500–$225,000 range can cover the charge, conditional on approval and available credit. | $1,000 at 1%. | $2,500 requires confirmed operations coding. |

On that date, Business Silver's double-cash-back offer ends that day and requires the account to be opened during its stated offer window; its normal $1,000 outcome is doubled to $2,000, not reclassified as software. Its standard annual fee is $122.50 if no waiver applies, so the comparison should distinguish $2,000 gross from $1,877.50 after that fee. The Business Platinum first-year-fee-waiver window is active on that date for eligible new customers, so its conservative $1,500 gross result is also $1,500 net of a waived first-year fee. Do not assume a waiver outside its documented window.

Thus, if the customer can open Business Silver within the documented promotional window **and** receives at least $100,000 of available credit, it has the largest documented conservative first-year return for this purchase ($2,000 gross; $1,877.50 after its standard fee). Business Platinum is the stronger fallback for capacity and has a $1,500 documented ordinary-rate return with a contemporaneous first-year waiver, but has materially higher documented credit requirements. Present Business Gold as another capacity-capable option, not as a 2.5% guarantee.

## Response format

Use a brief, customer-facing response with:

1. A direct answer naming the conditional leader and fallback.
2. A compact table or bullets giving rate, dollar result, capacity caveat, and first-year fee treatment.
3. A plain explanation that Apple Music is not documented as qualifying software or media advertising and that final rewards follow MCC.
4. Approval/available-credit and underwriting caveats.
5. A practical next step: confirm the merchant category and, before relying on a promotion, confirm that account opening—not merely application submission—will qualify before the cutoff.

Do not claim that a card will approve a particular limit, that Apple Music will earn a bonus rate, or that an expired/not-yet-effective offer applies.

## Calculation helper

Run `scripts/compare_rewards.py` with JSON on standard input. It accepts:

```text
{
  "amount": positive number or decimal string,
  "include_annual_fee": true or false,
  "options": [
    {
      "name": "card label",
      "can_cover_charge": true | false | "unknown",
      "base_rate_percent": nonnegative number,
      "bonus_rate_percent": nonnegative number (optional),
      "bonus_eligibility": "confirmed" | "unconfirmed" | "not_eligible" (optional),
      "promotion_multiplier": positive number (optional; default 1),
      "promotion_eligible": true | false (optional; default true),
      "annual_fee": nonnegative number (optional; default 0)
    }
  ]
}
```

It emits JSON containing conservative/base calculations, any explicitly labelled potential bonus calculation, fee-adjusted values, capacity status, and a ranking of only capacity-confirmed options. It does not decide MCC eligibility or promotion dates; make those policy determinations before invoking it. Validate that the returned amount matches the purchase amount, all displayed rates match the source rules, only `confirmed` bonuses are treated as guaranteed, and unknown/insufficient capacity is not described as ready for a single charge.
