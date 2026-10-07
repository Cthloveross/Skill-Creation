---
name: promotional-signup-bonus-advisor
description: Compare currently available credit-card promotional sign-up bonuses when a customer prioritizes points or cash back. Use for informational offer comparisons; distinguish monetary/points bonuses from APR or fee promotions and account for dates and invitation restrictions.
---

# Promotional Sign-Up Bonus Advisor

Use this Skill to provide a precise, evidence-grounded comparison of promotional sign-up bonuses. It is informational only: do not apply for an account, inspect customer accounts, or represent that approval or eligibility is guaranteed.

## Inputs

Run `scripts/recommend_signup_offer.py` with JSON on stdin:

- `as_of` (required): an ISO date (`YYYY-MM-DD`) or timestamp whose first 10 characters are an ISO date.
- `invitation_received` (optional): `true`, `false`, or `null` if unknown. This controls invitation-only offers.
- `include_inactive` (optional, default `true`): retain unavailable offers and explain why they cannot be recommended.

Example:

```json
{"as_of":"2025-11-14","invitation_received":false,"include_inactive":true}
```

The script emits JSON containing `best_available`, conditionally available bonus candidates, unavailable bonus offers, active non-bonus promotions, and information still needed. It reads the normalized source facts in `references/promo_offers.json` and uses only the Python standard library.

## Method

1. Obtain an observed current date from the supplied task context or the approved current-time capability. Do not infer a date from a document title or a customer statement.
2. Use the customer’s known invitation status. Treat an invitation-only offer as not actionable when the customer says they do not have an invitation; do not compare it as an available alternative.
3. Run the script and lead with `best_available` if present. “Available” means the documented date window is active and the known invitation constraint is met; it does **not** establish underwriting approval or all customer-level requirements.
4. State the qualifying spend, qualification period, reward amount, and any documented value conversion. Preserve reward units: sustainability points are not cash, even when their stated redemption value is shown.
5. State the material conditions: new-customer status, eligible/posted net purchases where documented, exclusions, and the need to keep the account open and in good standing when applicable. Mention posting timing when it helps set expectations.
6. Briefly distinguish active APR or fee promotions from sign-up points/cash-back bonuses. Do not present them as answers to a points-or-cash-back-bonus request.
7. For expired offers, state that the supplied date is outside the offer window. Do not suggest a previous offer can be retroactively applied. For missing invitation status, ask that narrow clarifying question rather than assuming it.

## Response quality and validation

Before replying, check that:

- Every recommended bonus has an active inclusive start/end date and satisfies known invitation restrictions.
- Any advertised cash-equivalent comparison comes from an explicit conversion rule, not an assumed point value.
- The response does not call an APR offer, annual-fee waiver, or unavailable invitation offer the best available sign-up bonus.
- The recommendation is conditional on documented requirements and does not claim approval, enrollment, or bonus posting has occurred.
- The response includes a source identifier from the script output when citations/provenance are expected by the host.

If `best_available` is `null`, explain that no documented actionable points/cash-back sign-up bonus was found for the supplied facts. Do not invent substitute offers.
