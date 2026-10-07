---
name: credit-card-signup-bonus-recommender
description: Recommend the best currently documented personal or business credit-card sign-up bonus when a customer prioritizes points, cash back, or statement-credit value. Use it to compare offer windows, invitation restrictions, customer eligibility, spending requirements, and point conversion rates without treating unavailable promotions as recommendations.
---

# Credit-card sign-up bonus recommender

Use this Skill for informational card-shopping requests. It does not apply for cards, change an account, determine underwriting approval, or require identity verification.

## Required runtime inputs

Collect these facts from the current task materials before ranking:

- The current/as-of timestamp.
- The requested card audience (`personal`, `business`, or `any`).
- Whether the customer has an invitation for each invitation-only offer, when relevant.
- Whether new-customer eligibility is known. If it is unknown, do not claim it is satisfied.
- Every documented sign-up bonus candidate, including its card name, offer dates, reward amount and unit, eligibility restrictions, required spend, qualification period, and source citation.
- A documented USD conversion for points when comparing a points award against cash back or statement credits.

Only include a positive sign-up award of points, cash back, or statement credit in the comparison. Do not count an annual-fee waiver as points or cash back unless the customer explicitly asks to compare fee value too. Do not invent an offer merely because a card's application terms are documented.

## Method

1. Extract all relevant promotion candidates from the supplied task documents. Preserve the supporting document title or ID in each candidate's `source` field.
2. Establish current availability using the supplied as-of date. A date window is inclusive. An expired offer, future offer, audience mismatch, known missing invitation, or known failed new-customer condition is unavailable.
3. Convert points to dollars only when the supplied evidence establishes a redemption conversion. Treat a statement credit denominated in USD as dollar-for-dollar. Never confuse a count of points with a dollar amount.
4. Run `scripts/rank_signup_offers.py` using the schema below. It ranks documented, currently active offers by cash-equivalent bonus value while separating eligible, conditional, unverified, unrankable, and excluded offers.
5. Use the result to write a direct recommendation:
   - Name the highest-value currently eligible offer; if none are fully verified but an active offer is conditional, name the highest-value conditional offer and clearly state the unmet or unconfirmed condition.
   - State the reward both in its native form and USD equivalent when conversion evidence exists.
   - State the offer end date, qualifying spend, qualification period, and material account-status or new-customer requirements.
   - Briefly explain why a larger-looking offer was not recommended when that fact is relevant (for example, it is invitation-only and the customer lacks an invitation, or its window has ended).
   - Qualify the conclusion as the best **among the documented offers currently available to the customer**, not as a market-wide claim.
6. Cite or identify the source documents used. If no offer is both documented and currently available, say that no documented current eligible sign-up award was found; do not substitute an expired, invitation-only, or unsupported offer.

For an active bonus that requires the customer to be new and that status was not provided, phrase the recommendation conditionally (for example, “if you are a new customer”). Do not ask for identity details simply to give general promotion information.

## Ranking script

`scripts/rank_signup_offers.py` reads one JSON object from standard input and emits one JSON object to standard output.

### Input schema

```json
{
  "as_of": "ISO-8601 timestamp or YYYY-MM-DD",
  "desired_audience": "personal | business | any",
  "invited_offer_ids": ["offer identifiers for invitations the customer has"],
  "is_new_customer": true,
  "offers": [
    {
      "id": "stable offer identifier",
      "card_name": "display name",
      "audience": "personal | business | any",
      "offer_start": "YYYY-MM-DD",
      "offer_end": "YYYY-MM-DD",
      "requires_invitation": false,
      "new_customer_required": true,
      "spend_requirement_usd": "optional decimal amount",
      "qualification_months": "optional number",
      "reward": {
        "amount": "positive decimal amount",
        "unit": "points, USD, or other native unit",
        "conversion_usd_per_unit": "optional documented decimal conversion"
      },
      "terms": ["material documented condition"],
      "source": {"document_id": "source ID", "title": "source title"}
    }
  ]
}
```

`invited_offer_ids` may be omitted when invitation status is unknown; invitation-required offers then remain conditional rather than being represented as available. `is_new_customer` may be omitted or `null` when unknown. Use `[]` when the customer has affirmatively said they have no invitation. An offer without both a start and end date is classified as `unverified` rather than current.

The output includes `recommendation`, ranked `eligible` and `conditional` candidates, and excluded or unsupported candidates with reasons. `recommendation` is `null` when there is no rankable currently active candidate.

A minimal runnable interface check (with no offers) is:

```sh
printf '%s\n' '{"as_of":"2025-01-01","desired_audience":"personal","invited_offer_ids":[],"offers":[]}' | python3 scripts/rank_signup_offers.py
```

## Validation before responding

Inspect the script's `validation` object and ensure all of the following are true for a positive recommendation:

- `recommendation_is_current` is true.
- `selection_is_maximum_in_selected_pool` is true.
- The selected candidate is not in `excluded`, `unverified`, or `unrankable`.
- The conversion rate and any dollar equivalent used in prose came from supplied evidence.
- The response discloses every condition listed under the selected candidate's `conditions` that is not known to be met.

If the input is malformed, the script emits `{"ok": false, "error": ...}`. Correct the extracted task facts rather than guessing missing dates, eligibility, reward values, or conversions.
