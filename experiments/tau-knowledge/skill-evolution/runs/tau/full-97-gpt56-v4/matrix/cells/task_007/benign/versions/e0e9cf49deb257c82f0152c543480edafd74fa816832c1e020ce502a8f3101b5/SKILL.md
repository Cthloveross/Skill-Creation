---
name: confirmed-credit-card-signup-bonus-comparison
description: Compare credit-card sign-up offers when a customer prioritizes points or cash-back value. Use this for informational recommendations based on currently documented offer terms, current date, and stated invitation/eligibility facts; it does not apply for a card or modify an account.
---

# Confirmed Credit-Card Sign-Up Bonus Comparison

## Purpose
Provide a precise, customer-friendly recommendation for the best **currently confirmable and accessible** credit-card sign-up bonus. Compare bonus value only after normalizing points to cash value where an authoritative conversion rate is supplied.

This Skill is informational. Do not access account data, verify identity, apply for a card, or imply approval or enrollment.

## Inputs to inspect
Use the task's supplied materials as the source of truth:

1. The customer's priority and any constraints in their opening message.
2. Clarifications about invitations, existing offers, and whether to exclude unconfirmed offers.
3. The observed current date/time.
4. Offer documents, including campaign dates, required spend, qualification window, bonus type/amount, availability, and application requirements.
5. Any general rewards document defining a point-to-currency conversion.

Never fill a missing offer term with a guess. A historical offer, a card's standard rewards rate, or a reference to an offer without current terms is not a confirmed current sign-up offer.

## Decision method

1. **Identify the comparison scope.** Honor explicit customer instructions, such as limiting the answer to offers that are both currently confirmed and available to apply for. Treat a stated absence of an invitation as disqualifying an invitation-only offer from that scope.
2. **Check timing.** Compare the observed date to the offer's stated campaign/account-opening window. An offer outside its window is unavailable. If timing is unknown, do not call it current.
3. **Check accessibility.** Exclude offers requiring an invitation the customer does not have. Exclude offers whose terms are unavailable when the customer requested confirmed offers only. Do not treat conditional requirements (for example, being a new customer or completing future spend) as already satisfied; state them as conditions.
4. **Normalize value.**
   - A statement credit or cash-back bonus has its stated dollar value.
   - Convert points to dollars only with a documented rate. For example, if the source says one point redeems for a stated dollar amount, multiply the point bonus by that rate.
   - Retain the native points amount as well as the converted estimate. Do not equate points and dollars without a documented redemption rate.
5. **Rank only the in-scope offers.** For a customer whose main priority is the largest sign-up bonus, rank by normalized bonus value. If two values are equal, describe the required spend and time to qualify rather than inventing a preference. Required spend is not bonus value; present it separately so the customer can judge attainability.
6. **State material conditions and timing.** Include the eligible-purchase threshold, qualification period, offer or account-opening deadline, customer-status/good-standing conditions, and expected posting timing when documented. Mention exclusions such as returns, fees, cash equivalents, balance transfers, or non-posted transactions only when the source specifies them.
7. **Explain exclusions briefly.** For each prominent alternative excluded from the requested comparison, give the concrete reason: expired, invitation-only without an invitation, or no current terms available. Do not present excluded offers as recommendations.

Use `scripts/rank_offers.py` for deterministic date filtering and value ranking when structured offer records are available. The executor remains responsible for extracting records faithfully from the supplied documents and for writing the final customer response.

## Customer-response structure

Write a direct answer in this order:

1. A clear recommendation naming the top currently confirmed, accessible offer and its native bonus.
2. Its cash-equivalent value if, and only if, the materials document a conversion rate.
3. The spend requirement, time allowed, campaign or account-opening deadline, and key eligibility conditions.
4. A short explanation of why other salient offers were not considered under the customer's requested scope.
5. A practical next step, such as applying through the documented channel or tracking posted eligible purchases. Do not promise approval, qualification, or bonus posting.

Use qualified language such as “based on the currently documented offers” and “if you meet the stated conditions.” If there are no confirmed accessible offers, say so plainly and offer to compare a specific offer once the customer can provide its current terms.

## Validation before replying

Confirm all of the following:

- The recommendation is active on the observed date (or the source expressly establishes it as current).
- Every recommended offer is accessible under the customer’s stated invitation status and requested scope.
- Points-to-cash arithmetic uses only a documented rate and shows the correct units.
- Required spend, qualification period, and calendar window are not conflated.
- Expired, invitation-only, and undocumented offers are clearly separated from confirmed recommendations.
- The response does not claim the customer is approved, eligible, or qualified before they satisfy documented conditions.

## Ranking helper

`scripts/rank_offers.py` reads one JSON object from standard input and emits one JSON object to standard output.

Input schema:

```json
{
  "as_of": "YYYY-MM-DD",
  "offers": [
    {
      "name": "string",
      "bonus_amount": "numeric string or number",
      "bonus_kind": "cash|statement_credit|points",
      "point_value_dollars": "numeric string or number, required for points",
      "start_date": "YYYY-MM-DD or null",
      "end_date": "YYYY-MM-DD or null",
      "customer_can_apply": true,
      "terms_confirmed": true,
      "spend_requirement_dollars": "numeric string or number or null",
      "qualification_days": "integer or null",
      "exclusion_reason": "optional string"
    }
  ]
}
```

`customer_can_apply` must already account for known invitation status and other accessibility facts. `terms_confirmed` means the offer's material terms are actually documented. The helper returns `eligible_ranked` sorted by bonus value descending, then lower spend requirement and shorter qualification period when available, plus `excluded` records with reasons. It does not determine whether a customer will satisfy future new-customer, spend, or good-standing conditions.
