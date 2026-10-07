---
name: checking-referral-eligibility-review
description: Review a checking-account referrer's eligibility and referral capacity before giving a referral recommendation. Use for Gold Years, Sky Blue, or general checking-referral questions involving timing, annual limits, bonuses, or prospective referees.
---

# Checking Referral Eligibility Review

Use this Skill before recommending a referral, a referral link, referral timing, bonus maximization, or program-specific terms. Do not submit a referral, issue a referral code, or imply approval. Those are banking actions and require a declared normal banking tool.

## Eligibility-first rule

Before giving any referral recommendation or information on referral terms, perform the referrer-tenure check first. A completed check may establish that tenure passes, fails, or cannot be confirmed because the earliest checking-opening date is unavailable. If it is unavailable, state that result prominently and do not characterize the referrer or any candidate as eligible, approved, or ready to submit. You may still give a clearly conditional, factual explanation of history, limits, and terms so the user understands why a recommendation cannot yet be confirmed.

## Review in this order

1. **Identify the referrer from authorized inputs.** Use a supplied user ID, or look up an exact user-provided profile name with `get_user_information_by_name`. A lookup is not identity verification. Call `log_verification` only after the user has actually confirmed at least two of date of birth, email, phone number, and address; use `get_current_time` for its timestamp. Once a user ID is available, use it for the one needed referral-history lookup; do not repeat equivalent profile/history lookups or use email lookup unless the user supplied email as the identifier.
2. **Establish referrer tenure before a recommendation.** Tenure is measured from the earliest Rho-Bank *checking* account opening—not the current product, a referral date, or a credit-card opening. Gold Years requires 30 days and Sky Blue requires 45 days. Use a declared checking-account-opening tool if one exists. Credit-card account or transaction tools do not establish checking tenure and must not be used for this purpose. If no checking-opening tool exists or it returns no date, say the condition is unconfirmed; do not infer it from referral history or claim the referrer is eligible.
3. **Obtain history and current time.** Call `get_referrals_by_user` and `get_current_time`. Count only `COMPLETE` referrals as received bonuses unless available terms explicitly say otherwise. The maximum is two bonuses across all checking products in a rolling nine-day window. Exact timestamps control the boundary. With date-only records, mark a referral exactly nine calendar days before the review as ambiguous rather than guessing.
4. **Apply program annual limits separately.** Count completed referrals in the current calendar year for the target program. Gold Years: six bonuses per calendar year. Sky Blue: eight. Annual availability and rolling availability are separate; neither establishes eligibility or approval.
5. **Assess each prospective referee independently.** Never infer missing eligibility from a relationship, age, company age, or a prior referral.
   - Every referral: new Rho-Bank customer with no current account and no account closed in the preceding 12 months; different registered address; no other new-account promotion; one referral code only.
   - Personal referrals: age 18+ unless the target account's terms state an exception.
   - Gold Years: age 62+; $1,000 new-money deposit within 90 days of opening. The money must remain for 30 days after the qualifying period. Bonuses are $50 for the referrer and $75 for the referee, subject to all conditions.
   - Sky Blue: business formed within four years; new to Rho-Bank; primary authorized signer's SSN differs from the primary owner of every existing Rho-Bank business account; $10,000 new-money deposit within 90 days. Bonuses are $150 for the referrer and $250 for the business, subject to all conditions.
6. **Give a bounded conclusion.** Clearly distinguish confirmed history/limits, candidate facts, unconfirmed prerequisites, and future qualification obligations. If tenure is unconfirmed or fails, do not represent the referrer as eligible or claim any candidate is approved. A rolling-limit denial cannot be reinstated in the same window. Closing the referred account within 90 days can lead to clawback; both accounts must remain in good standing.

Do not request SSNs in chat. If a name/ID, account-history or address fact, business new-customer status, owner distinction, or earliest checking-opening date is unavailable, state that exact prerequisite as unconfirmed and direct the user to the appropriate application/eligibility process. Do not recommend submission as though the condition passed.

## Answering common decision questions

- **“Can I do one more now?”** State the remaining *bonus capacity*, not approval. It is shared across programs. If a recent complete referral leaves one of two rolling slots, there is one additional capacity slot, provided the target program has annual room and all eligibility conditions pass. A date-only recent record safely counts when it is plainly inside the nine-day period; reserve ambiguity for a boundary-date record. If tenure is unknown, explicitly say capacity does not establish eligibility.
- **“Which maximizes my bonus?”** First eliminate programs at their annual cap and candidates that are known ineligible. Compare only available programs' referrer bonuses. If viable candidates have equal bonus amounts and only unknown prerequisites distinguish them, do not invent a preference: say either is conditional on validation and choose whichever can be validly confirmed first. If required prerequisites are unconfirmed for every candidate, do not recommend submitting any candidate now.
- **“When will capacity return?”** Say the oldest successful referral must be more than nine days old. Do not give an exact time from a date-only history record.

## Optional deterministic calculator

Run `scripts/referral_review.py` only after translating tool results into structured JSON. It is pure computation: it does not call bank tools, verify identity, or trigger banking actions.

Input JSON on stdin:

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
      "distinct_business_primary_owner": null,
      "has_other_new_account_promotion": null,
      "one_referral_code": null
    }
  ]
}
```

It emits JSON containing rolling-window capacity, annual counts, tenure status, candidate prerequisite statuses, and deposit obligations. `null` means unknown, never pass. It recognizes account labels containing Gold/Years or Sky/Blue case-insensitively. It does not decide whether to submit.

Example: `python3 scripts/referral_review.py < review_input.json`.

Validate that the `as_of` year and timezone are correct, all completed history is present, program labels map correctly, timestamps are available for boundary decisions, and every `unknown` prerequisite is communicated as unconfirmed rather than approved.
