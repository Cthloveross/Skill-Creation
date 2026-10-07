---
name: credit-card-constraint-recommendation
description: Screen documented credit-card products against a customer's stated credit score and payment, foreign-transaction-fee, virtual-card, and subscription constraints, then provide a careful, non-guaranteed recommendation. Use for product-selection questions rather than account servicing or application submission.
---

# Credit-card constraint recommendation

Use this Skill when a customer asks which card best meets explicit eligibility or feature requirements.

## Method

1. Extract the customer's hard constraints. Preserve the comparison direction exactly (for example, a fee *at or below* a limit) and distinguish a required feature from a preference.
2. Screen the packaged product facts with `scripts/screen_cards.py`. Supply the customer score, whether they have the relevant premium subscription, and the requested thresholds. The script uses the supplied `cards` array when present; otherwise it uses the packaged catalog.
3. Recommend only products returned in `eligible`. A product with an unknown required fact is not a confirmed match; it appears under `indeterminate` rather than being recommended.
4. Explain the match using the specific documented terms. If a close alternative fails, briefly state the decisive reason when useful (such as a score requirement or missing virtual-card support).
5. Do not promise approval, a particular credit line, or an application outcome. State that final approval remains subject to the issuer's application review. Do not submit an application or collect identity data merely to make a recommendation.

For a conversational answer, lead with the matching card, list the terms that meet every hard constraint, and give a concise next step (review terms and apply if desired). Do not overstate unrelated rewards or benefits.

## Script interface

Run `scripts/screen_cards.py` with JSON on stdin. Example:

```json
{
  "customer": {"credit_score": 540, "has_premium_subscription": false},
  "criteria": {
    "max_foreign_transaction_fee_percent": 1.5,
    "max_minimum_payment_percent": 1.5,
    "require_virtual_card_management": true
  }
}
```

Optional `cards` may replace the packaged catalog with an array of objects having `name`, `minimum_credit_score`, `minimum_payment_percent`, `virtual_card_management`, and either `foreign_transaction_fee_percent` or `foreign_transaction_fee_by_subscription` fields. This makes the screening logic reusable with a current product feed.

The script emits JSON with:
- `eligible`: cards confirmed to meet every supplied criterion;
- `rejected`: cards with one or more documented failures and the reasons;
- `indeterminate`: cards whose required data is unavailable; and
- `criteria_used`.

Validate that every requested criterion was supplied in `criteria`, inspect `indeterminate` before making a recommendation, and ensure the final response does not call a rejected card a match. A malformed request returns `{ "error": ... }`; ask for the missing constraint or correct the input rather than guessing.

## Packaged facts

`references/card_catalog.json` is a normalized transcription of the available product documentation. The catalog supports comparison and is not an approval engine. In particular, “no minimum credit score requirement” is represented as `0`, not as a guarantee of approval.
