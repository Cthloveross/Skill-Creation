---
name: business-referral-maximizer
description: Assess checking-account referral eligibility and recommend the documented business account with the largest referrer bonus that the referred business's planned deposit can meet. Use for referral-bonus comparison requests, especially when tenure, annual caps, rolling limits, or referred-party eligibility must be checked.
---

# Business referral maximizer

Use this Skill to give a grounded, conditional recommendation for a business checking referral. It is designed for advisory conversations only: it does not submit a referral, change an account, or make a promise that a bonus will be paid.

## Required order of work

1. **Check the referrer's eligibility before recommending terms.** Obtain a user identifier (a supplied exact name or email can be used with the available user lookup tool), inspect referral history, and establish the referrer's checking tenure from an authoritative source or a clear customer statement. Do not treat the current account type as the tenure date.
2. Check the target program's tenure threshold, annual cap, and the cross-product rolling cap of two successful bonuses in the preceding nine days. Count only `COMPLETE` referrals as successful bonuses. Use exact completion timestamps when available. If only a date is available and it is close to the nine-day boundary, say the rolling-limit result cannot be confirmed without the timestamp.
3. Capture the proposed initial/qualifying deposit and compare it with each documented qualifying-deposit threshold and deadline. A deposit that is merely an initial balance is only sufficient if it will be new money, made in the stated window, and retained for the required period.
4. Before saying the referral *will qualify*, check or explicitly identify as unresolved all referred-party restrictions: new customer/no existing or closed Rho-Bank account within 12 months, different registered address, and (for a business) a primary authorized signer SSN not used as the primary owner of an existing Rho-Bank business account.
5. Run `scripts/assess_referral.py` after normalizing the gathered facts. It produces the highest stated referrer bonus among programs whose known quantitative requirements pass. If a prerequisite is unknown, its result is explicitly conditional rather than confirmed.
6. Give a short user-facing answer naming the recommended account and the **referrer's** bonus, then explain why higher-paying alternatives fail the proposed-deposit constraint. State unresolved qualification conditions and material general terms. Do not reveal account data or referral history beyond what is necessary to advise the authenticated/requesting customer.

## Interpretation rules

- Referral tenure is based on the earliest Rho-Bank checking relationship, even if the referral is to a product different from the product the referrer holds now.
- The two-bonuses-in-nine-days limit is across checking account types. It is separate from each program's annual cap.
- Annual limits are evaluated against completed bonuses for the relevant target program, unless an authoritative program source explicitly says otherwise.
- The November 2025 promotion ordering (Sky Blue then Lime Green) applies only when multiple accounts satisfy **all** customer requirements. A request to maximize the referrer's dollar bonus means a lower-paying promotional account does not meet that stated objective.
- Do not infer that a partner is a new customer, has no recent closed account, or has an eligible primary signer merely because they formed a new LLC or work at a different office.
- If a customer cannot provide facts needed to establish referred-party eligibility, provide a conditional recommendation and identify exactly what must be confirmed; do not claim qualification or submit a referral.

## General conditions to include when relevant

A qualifying deposit must be new money, not transferred from another Rho-Bank account, and must remain in the referred account for at least 30 days after the qualifying period ends. The bonus cannot combine with another new-account promotion or sign-up bonus, only one referral code may be used, and a bonus may be clawed back if the referred account closes within 90 days. Both accounts must remain in good standing.

## Script interface

Run `scripts/assess_referral.py` with JSON on stdin. It emits one JSON object on stdout.

Input schema:

```json
{
  "as_of": "YYYY-MM-DDTHH:MM:SS±HH:MM",
  "planned_deposit": 30000,
  "referrer_tenure_days": 730,
  "referrals": [
    {
      "referred_account_type": "World Blue Account",
      "referral_status": "COMPLETE",
      "date": "YYYY-MM-DD"
    }
  ],
  "referred_party": {
    "new_customer_no_account_past_12_months": "unknown",
    "different_registered_address": "true",
    "different_business_primary_owner_ssn": "unknown"
  }
}
```

`referrer_tenure_days` may be `null` if it has not been established. Each referred-party field must be `true`, `false`, or `unknown`. Referral timestamps may be supplied in `timestamp`; date-only records are supported but can make a boundary rolling-window result indeterminate. Values from the current conversation and normal banking tools must be supplied at runtime; never embed a customer ID, referral records, or a current-instance result in the Skill.

Output includes `recommendation`, `ranked_eligible_programs`, `ineligible_programs`, `referrer_checks`, and `referred_party_checks`. Treat an `unknown` referred-party field as a condition to disclose, not an affirmative check.

## Validation before responding

- Confirm the selected program has the largest referrer bonus among programs that pass the deposit, tenure, annual-cap, and non-blocked rolling checks.
- Confirm every higher-bonus program is either shown with its failed requirement or not represented as available.
- If the referrer is not eligible or eligibility is not established, ask for/obtain what is needed before giving program recommendations.
- If any referred-party prerequisite remains unknown, use conditional wording such as “the best option, provided these eligibility checks pass,” rather than “this referral qualifies.”
- Do not call account-changing, referral-submission, or identity-verification logging tools for this informational request.
