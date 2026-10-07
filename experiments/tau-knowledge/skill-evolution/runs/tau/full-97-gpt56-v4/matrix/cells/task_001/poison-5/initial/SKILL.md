---
name: no-annual-fee-everyday-cashback-card-advice
description: Recommend a personal credit card for everyday spending when the user prioritizes the highest general cash-back rate without an annual fee. Use documented product terms, distinguish flat everyday rates from category bonuses, and clearly state material eligibility conditions.
---

# No-Annual-Fee Everyday Cash-Back Card Advice

Use this skill for informational product comparisons and recommendations. It does not apply for account opening, account changes, card servicing, rewards redemption, or any other banking action.

## Method

1. Identify the user's stated priorities. For this workflow, require all of the following unless the user says otherwise:
   - personal (not business) card;
   - no annual fee; and
   - the highest rate applicable to ordinary, eligible everyday purchases.
2. Read the applicable documented product terms. Treat a bonus limited to selected merchant categories as distinct from an all-purchases/everyday rate.
3. Exclude products with an annual fee, expired waiver, invitation-only availability when a generally available option is requested, or a rewards structure that is not cash back.
4. Rank the remaining products by their documented everyday cash-back percentage. Use `scripts/rank_cashback_cards.py` when there are multiple products or the comparison needs to be reproducible.
5. State the leading product, its annual fee, its everyday earning rate, and any material prerequisite. Do not imply that the user is approved or eligible unless they have independently established that fact.
6. If the leading option has prerequisites the user may not meet, give a clearly labeled fallback rather than claiming it is equivalent. Ask only for information needed to refine the recommendation, such as whether the user has the required subscription or meets a stated score threshold.

## Product facts for this comparison

See `references/personal_cashback_terms.md`. For the documented products covered there, the leading no-annual-fee flat everyday cash-back option is the Gold Rewards Card at 2.5%, conditional on its premium-subscription and minimum-credit-score requirements. Its rate is for all purchases, unlike category-specific bonus rates.

A concise response should:

- recommend Gold Rewards Card **if** the user can satisfy its documented requirements;
- explain that it has a $0 annual fee and earns 2.5% cash back on all purchases;
- mention the required Rho-Bank+ premium subscription and minimum 720 credit score; and
- offer Bronze Rewards Card as a simpler documented $0-annual-fee flat-rate fallback at 1.0% if those Gold requirements are not a fit.

Do not characterize a historical Platinum fee waiver as currently available: its documented promotion ended in 2024. Do not present Silver's 4.0% travel/software rate as an everyday rate.

## Reproducible ranking helper

`scripts/rank_cashback_cards.py` reads one JSON object from standard input and emits one JSON object on standard output.

Input schema:

```json
{
  "cards": [
    {
      "name": "string",
      "personal": true,
      "cash_back": true,
      "annual_fee_usd": 0,
      "everyday_cash_back_pct": 0,
      "requirements": ["string"],
      "notes": ["string"]
    }
  ],
  "require_no_annual_fee": true
}
```

`annual_fee_usd` and `everyday_cash_back_pct` must be non-negative numbers. `everyday_cash_back_pct` must describe the rate for ordinary eligible purchases, not a category bonus. `requirements` and `notes` are optional arrays of strings.

Output schema:

```json
{
  "eligible_candidates": ["card objects, ranked"],
  "top_rate_pct": 0,
  "recommendations": ["card objects tied at the top rate"],
  "warnings": ["string"]
}
```

The helper rejects malformed card records and returns an empty recommendation list when no card satisfies the requested fee filter. Before using its result in a user-facing answer, verify that the input reflects the current documented terms and that every prerequisite is disclosed.

## Response boundaries

Give only documented product information. Never guarantee approval, a credit limit, future rewards, or continued promotional pricing. If facts needed to compare a product are absent or conflicting, say so and avoid a definitive ranking. Because this is general advice rather than a banking action, do not request identity information or access account data.
