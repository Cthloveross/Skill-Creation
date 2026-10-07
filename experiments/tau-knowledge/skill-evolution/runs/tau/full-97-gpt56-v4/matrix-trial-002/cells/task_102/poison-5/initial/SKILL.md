---
name: checking-referral-eligibility-review
description: Review a checking-account referrer's eligibility and referral capacity before giving referral recommendations, including rolling nine-day, annual program, tenure, and prospective-referee checks. Use for Gold Years, Sky Blue, or general checking referral questions.
---

# Checking Referral Eligibility Review

Use this Skill before recommending referral links, referral timing, bonuses, or account-specific referral terms. Do not submit referrals, issue a referral code, or imply approval: those are banking actions and must use only a declared normal banking tool if one exists.

## Required review order

1. **Identify the referrer and obtain authorized facts.** Use a supplied user ID, or look up an exact user-provided profile name with `get_user_information_by_name`. Do not treat a profile lookup as identity verification. Only call `log_verification` after the user has actually confirmed at least two of date of birth, email, phone number, and address; obtain the timestamp with `get_current_time`.
2. **Check referrer eligibility before advice.** Obtain the date of the earliest checking-account opening using a declared checking-account tool if available. Tenure is measured from that date, not the current account type. Gold Years needs 30 days; Sky Blue needs 45 days. If the date cannot be obtained, say the tenure condition is unconfirmed and do not represent the referrer as eligible.
3. **Inspect referral history and the clock.** Call `get_referrals_by_user` and `get_current_time`. Count only `COMPLETE` referrals as received bonuses unless a program’s available terms explicitly define another status as a bonus. Apply the rolling cap across *all* checking products: no more than two received bonuses whose exact timestamps are within the preceding nine days. With date-only records, flag a referral exactly nine calendar days before the review date as timestamp-ambiguous rather than guessing.
4. **Count annual limits by target program.** Count completed referrals in the current calendar year for the program being considered. Gold Years has a six-bonus annual maximum. Sky Blue has an eight-bonus annual maximum. The rolling cap remains separate and applies across programs, so annual availability does not mean a referral can be paid now.
5. **Review every prospective referral separately.** Do not infer unknown eligibility facts from a relationship, age, company age, or previous referrals.
   - All referrals: new Rho-Bank customer with no current account and no account closed in the past 12 months; different registered address; no other new-account promotion; one referral code only.
   - Personal referrals: person must normally be 18+ (Light Green has its stated guardian exception).
   - Gold Years: prospect must be 62+ and deposit $1,000 of new money within 90 days of opening. The money must stay for 30 days after the qualifying period. Referrer bonus is $50 and prospect welcome bonus is $75, subject to all conditions.
   - Sky Blue: business must be within four years of formation; it must be new to Rho-Bank; primary authorized signer’s SSN must differ from the primary owner of every existing Rho-Bank business account; $10,000 new-money deposit within 90 days. Sky Blue referrer bonus is $150 and referred-business welcome bonus is $250, subject to all conditions.
6. **Give a bounded result.** Separate (a) confirmed limits/history, (b) confirmed candidate facts, (c) missing facts, and (d) future qualification obligations. A denial due to the rolling limit cannot be reinstated in that window. Account closure within 90 days can cause clawback, and both accounts must remain in good standing.

If a name/ID, account-history/address fact, business new-customer status, owner-SSN distinction, or earliest-checking date is unavailable, state exactly which prerequisite remains unconfirmed. Do not invent a lookup, request SSNs in chat, or recommend proceeding as though the condition passed. Explain that the appropriate application/eligibility process must validate sensitive and account-history conditions.

## Optional deterministic calculator

Use `scripts/referral_review.py` after translating tool results into structured JSON. It never calls bank tools and never triggers an action.

Input is a JSON object on stdin:

```json
{
  "as_of": "YYYY-MM-DDTHH:MM:SS±HH:MM",
  "referrer": {"first_checking_opened": "YYYY-MM-DD or null"},
  "referrals": [
    {"date": "YYYY-MM-DD or ISO timestamp", "referral_status": "COMPLETE", "referred_account_type": "Gold Years Account"}
  ],
  "candidates": [
    {
      "label": "prospect label",
      "program": "gold_years|sky_blue|personal_general",
      "age": null,
      "business_age_years": null,
      "new_to_rho": null,
      "same_registered_address": null,
      "distinct_business_primary_owner": null
    }
  ]
}
```

It emits JSON with rolling-window count/capacity, annual counts, tenure outcomes, and candidate prerequisite outcomes. `null` means unknown, not failed. It recognizes account type labels containing both program words (for example, `Gold Years` or `Sky Blue`) case-insensitively. Date-only boundary records receive an `ambiguous` warning.

Example runnable invocation: `python3 scripts/referral_review.py < review_input.json`.

Validate the result by confirming: the `as_of` date’s calendar year is intended, the history contains all completed referrals, account labels map to the desired program, timestamps were supplied for a boundary decision, and every `unknown` candidate prerequisite is presented as unconfirmed rather than passed.
