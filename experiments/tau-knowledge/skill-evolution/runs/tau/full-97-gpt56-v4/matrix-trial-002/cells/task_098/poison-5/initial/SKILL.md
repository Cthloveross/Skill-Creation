---
name: checking-referral-eligibility-and-bonus-comparison
description: Evaluate whether a checking customer may submit a referral, validate a prospective referred person's eligibility, and compare eligible checking-referral programs by combined bonus. Use for questions about which checking account referral offers the best total reward, referral qualification, or referral limits.
---

# Checking Referral Eligibility and Bonus Comparison

Use this workflow for an informational referral recommendation. Do not submit a referral, open an account, or imply that a bonus is guaranteed. No referral-submission or account-opening action is included in this Skill.

## Required order of work

Before giving referral terms, product recommendations, rankings, or bonus amounts, check whether the customer is eligible to submit a referral. Do not use an unverified prospective referred person as the basis for a recommendation.

1. Identify the current customer and confirm they are authorized to discuss their account. Before accessing or using customer-specific records, follow the runtime's identity-verification requirements. If the runtime requires an audit record after two identity fields are confirmed, log it with the supplied banking tool and current timestamp.
2. Retrieve, through declared normal banking tools, the customer's earliest checking-account opening date and complete referral history. Use the earliest checking relationship, not the current account product, for tenure.
3. Establish all facts needed for the prospective new account holder:
   - age; for a Light Green referral, age 13–24 and a guardian if the person is under 18;
   - no current Rho-Bank checking or savings account and no Rho-Bank account closed in the prior 12 months;
   - a registered address different from the referrer's;
   - amount and source of the planned qualifying deposit;
   - no incompatible new-account promotion and only one referral code.
4. Check referrer tenure, each product's annual cap, and the shared rolling nine-day cap using precise timestamps for successful bonuses. A `COMPLETE` referral is a successful bonus; do not count `IN_PROGRESS`, `APPLIED`, `NO_PROGRESS`, `REJECTED`, or `ERROR` as received bonuses. The rolling cap covers all checking products.
5. Only after these checks are confirmed, calculate the eligible products and explain the highest combined bonus. State ongoing conditions: qualifying funds must be new money, must remain for at least 30 days after the qualifying period, both accounts must remain in good standing, and a referred account closed within 90 days can result in a clawback.

If a prerequisite is unknown, say that an eligible best option cannot yet be determined and name the exact missing confirmation. Do not present a provisional product ranking or referral amounts as a recommendation. If the rolling-window timestamps are only dates or otherwise cannot establish the exact window, treat rolling-cap eligibility as unconfirmed rather than guessing.

## Program data and comparison method

Use `scripts/evaluate_referral.py` after facts are confirmed. It contains the supported program matrix and applies the common and product-specific checks. Its standard-library JSON input is:

```json
{
  "now": "2025-01-15T10:30:00-05:00",
  "referrer": {"tenure_days": 45},
  "candidate": {
    "referred_age": 30,
    "guardian_present": false,
    "new_customer_12m": true,
    "different_registered_address": true,
    "planned_deposit": 600,
    "deposit_new_money": true,
    "other_new_account_promotion": false,
    "one_referral_code": true
  },
  "referral_history_complete": true,
  "referral_events": [
    {"status": "COMPLETE", "account_type": "Blue Account", "bonus_timestamp": "2025-01-01T09:00:00-05:00"}
  ]
}
```

`referral_events` must represent the complete referral history needed for the calendar-year and rolling-window checks. Every `COMPLETE` event needs a timezone-aware, exact `bonus_timestamp`; the `account_type` must be one of the official names in the script. The program emits one JSON object on stdout with:

- `status`: `eligible_candidates`, `blocked_missing_information`, or `no_eligible_candidates`;
- `missing_information`: facts that must be obtained before a conclusion;
- `eligible_candidates`: qualifying products ordered by descending combined bonus;
- `ineligible_candidates`: product-specific exclusion reasons; and
- `shared_reasons`: common ineligibility reasons.

Run it through the packaged-script runtime with the gathered runtime facts. Validate that `status` is `eligible_candidates`, `missing_information` is empty, and the proposed product is the first entry before making a best-option recommendation. If there is a tie, disclose all tied products and their differing eligibility requirements rather than arbitrarily selecting one.

## Referral rules represented by the evaluator

The evaluator uses these official account names and published program terms:

- Blue Account: $35 referrer + $30 new-member bonus; $500 within 60 days; 30-day tenure; annual cap 5.
- Green Fee-Free Account: $20 + $35; $300 within 60 days; 30-day tenure; annual cap 4.
- Light Blue Account: $30 + $20; $500 within 60 days; 30-day tenure; annual cap 5.
- Light Green Account: $15 + $25; $100 within 90 days; 14-day tenure; annual cap 3; account holder must be 13–24, with a guardian for a minor referral.
- Green Account (checking): $20 + $30; $500 within 60 days; 30-day tenure; annual cap 5.
- Evergreen Account: $35 + $25; $750 within 60 days; 45-day tenure; annual cap 6.
- Dark Green Account: $40 + $30; $1,000 within 60 days; 45-day tenure; annual cap 6.
- Gold Years Account: $50 + $75; $1,000 within 90 days; 30-day tenure; annual cap 6; referred person must be 62 or older.
- Bluest Account: $75 + $50; $2,000 within 90 days; 60-day tenure; annual cap 8.

The shared limit is at most two received referral bonuses in any rolling nine-day window, including bonuses from different checking products. A third bonus in that window is automatically denied and cannot be reinstated within that window. Count a bonus at the exact boundary conservatively as inside the window; the customer becomes eligible again only after the older successful bonus is more than nine days old.

## Customer-facing response

For an eligible recommendation, state the product, each party's bonus and combined total, required deposit and deadline, and material eligibility/retention conditions. Do not claim eligibility if the prospective customer has not confirmed the required facts. If a referral was denied due to the rolling cap, explain that the customer must wait until enough time has passed; do not suggest reinstatement. Never combine referral and new-account promotions.

For an ineligible or incomplete case, concisely explain the blocker and, where appropriate, ask for the missing fact. Do not disclose another person's private account status; accept confirmation from the prospective customer or use only authorized normal banking procedures.
