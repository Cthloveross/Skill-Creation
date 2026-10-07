---
name: business-checking-referral-recommendation
description: Assess a checking customer's eligibility before discussing business referral terms, then recommend the highest referrer bonus that the proposed new-business deposit can qualify for. Use for questions about which business checking account to refer a business to or what referral bonus the referrer can earn.
---

# Business checking referral recommendation

## Required sequence

1. **Confirm the referrer is eligible before giving referral recommendations or terms.** Obtain an exact name, user ID, or email; use the corresponding read-only customer lookup; obtain their referral history; and ask when they first opened *any* Rho-Bank checking account if that fact is not available. The tenure is measured from the oldest checking account, not the currently held account type.
2. Check the referrer's stated or documented tenure against every potentially suitable product's tenure threshold. Check completed bonuses in the rolling nine-day window across all checking products. Use exact bonus timestamps when available. Also check the program-specific calendar-year cap for the proposed product.
3. Compare the proposed external/new-money deposit with each supported product's required deposit and deposit window. Run `scripts/evaluate_referral.py` for a reproducible comparison when the relevant structured facts are available.
4. Recommend only a product that is deposit-qualified, tenure-qualified, not at its annual cap, and not blocked by the rolling cap. State the largest eligible **referrer** bonus, not the referred business's welcome bonus.
5. State unresolved conditions rather than assuming them: the referred business must be new to Rho-Bank (no existing checking, savings, or account closed in the past 12 months), have a different primary owner/primary authorized signer SSN from every existing Rho-Bank business account, and not share the referrer's registered address. The deposit must be new money rather than an internal Rho-Bank transfer and remain for at least 30 days after the qualifying period ends. A referral cannot stack with another new-account/sign-up promotion, and only one referral code can be applied.

A business need not be referred to the same account type that the referrer holds. Do not perform account changes, create referrals, or imply that a bonus is guaranteed.

## Handling incomplete or conflicting facts

- If the identity lookup does not uniquely identify the requester, request a different identifier before looking up referral history.
- If referrer tenure is unknown, request the earliest checking opening date (or an unambiguous duration) before discussing specific referral amounts.
- If there are two completed bonuses within the last nine days, explain that another completed bonus will be auto-denied until an older bonus is outside the rolling window. With date-only referral records at a nine-day boundary, do not claim the cap has cleared; exact timestamps are needed.
- If the planned deposit is below every supported threshold, say no listed program qualifies at that amount and explain the next threshold(s), rather than recommending an unqualified product.
- If a product is at its annual cap, exclude it even if its bonus would otherwise be highest.
- If the partner's new-customer, ownership, address, promotion, or new-money status is not known, give the conditional recommendation but plainly list the confirmation required before submitting a referral.

## Product facts used by the helper

The packaged helper covers Navy Blue, Lime Green, True Blue, and Beige business referral programs. Its defaults are documented in `references/business_referral_programs.md`. Supply `programs` in its JSON input only when the current task supplies authoritative additional or changed programs; do not invent missing product terms.

## Helper invocation

Run `scripts/evaluate_referral.py` with a JSON object on stdin. It emits one JSON object on stdout.

Input schema:

```json
{
  "now": "ISO-8601 timestamp or YYYY-MM-DD",
  "planned_deposit": 30000,
  "referrer_tenure_days": 730,
  "referrals": [
    {"referred_account_type": "Lime Green Account", "referral_status": "COMPLETE", "date": "YYYY-MM-DD or ISO-8601 timestamp"}
  ],
  "new_money_confirmed": true,
  "referred_business_new_confirmed": false,
  "different_primary_owner_confirmed": false,
  "different_address_confirmed": false,
  "no_other_promotion_confirmed": false
}
```

`now`, `planned_deposit`, `referrer_tenure_days`, and `referrals` are required. The boolean confirmation fields are optional and default to `false`. An optional `programs` array may override the defaults; each item needs `name`, `referrer_bonus`, `required_deposit`, `deposit_window_days`, `tenure_days`, and `annual_cap`.

Interpret `recommendation` as the best program meeting known numerical/cap requirements. Interpret `unresolved_requirements` as conditions that still must be confirmed; do not omit them from the customer response. A `rolling_window.status` other than `clear` means do not promise that a new bonus can be accepted.

## Response composition

After successful referrer checks, answer plainly: confirm the customer's tenure/cap status, name the recommendation and referrer bonus, explain why higher-bonus options do not fit the stated deposit, and give the relevant deposit window. Then list the outstanding eligibility and general bonus conditions. Keep the response focused on the referrer's reward; mention the referred business's offer only if asked.

Validate helper output before using it: `recommendation` must be either `null` or one of `evaluations[*].name`; a non-null recommendation must have `numerically_qualified: true`, `annual_cap_available: true`, and a rolling-window status of `clear`. If parsing fails or essential numeric facts are missing, do the comparison manually from the authoritative program facts and disclose the missing information.
