---
name: checking-referral-eligibility-and-world-blue-guidance
description: Handle a Rho-Bank checking-account referral question, including a request to maximize the documented World Blue business-referral reward. Use before providing referral terms, product guidance, or attempting any banking action.
---

# Checking referral and World Blue guidance

## Scope and safety boundary
This Skill gives documented referral information and assesses stated facts. It never creates a referral, opens an account, verifies an identity, or promises a bonus. Use normal declared banking tools only when available and when their own prerequisites are satisfied.

The required ordering is important: **before giving a recommendation or referral terms, first establish that the referrer is eligible to submit referrals.** Referrer eligibility is not the same as proving that the prospective customer and business will ultimately qualify. Once the referrer is eligible, give the documented offer information while clearly separating it from the remaining prospective-customer conditions.

## 1. Check the referrer first
Collect the referrer's user ID and the date of their earliest Rho-Bank checking account. Do not use their current product type to calculate tenure.

1. If a user ID is available, call `get_referrals_by_user` and examine successful referral-bonus timestamps. Count bonuses in the nine-day interval ending now. At two or more, another referral is automatically denied in that rolling window; wait until the count falls below two. A customer statement that this is their first referral is not a substitute for the history check.
2. For World Blue, confirm at least 90 days of checking tenure from the first checking-account opening. If exact dates are available, calculate against the current date; if only an approximate date is provided, describe the result as based on that statement rather than as a system-verified fact.
3. Also account for World Blue's 12-referral calendar-year limit. Referral-history records can support this check when they contain enough information. If the data do not establish it, disclose that it remains to be confirmed.
4. If the ID/history or tenure is missing, ask for it and do not yet quote or recommend a referral offer. If the referrer fails a threshold, say they cannot use that program now. Never claim that an absent or malformed tool result proves eligibility.

## 2. Give the documented World Blue guidance after referrer eligibility passes
For a business seeking a documented referral reward and planning a qualifying deposit of at least $25,000, World Blue is the documented option to present:

- The referrer receives **$300** for each successful World Blue referral; the new business receives a **$200** welcome bonus.
- The referred business must open **World Blue** and deposit at least **$25,000 within 90 days** of opening.
- A stated $31,000 deposit exceeds the dollar threshold, but only potentially meets that amount condition. It must be new money, not a transfer from another Rho-Bank account, be made on time, and remain in the account for at least 30 days after the qualifying period ends.
- Bonuses are typically credited 7–10 business days after qualification. Both accounts must remain in good standing. A referred account closed within 90 days may result in a clawback.
- A referral cannot be combined with another new-account promotion or sign-up bonus, and only one referral code may be used for the new account.

Say “the documented World Blue referrer reward is $300,” rather than asserting it is the greatest offer anywhere unless the available evidence documents all competing offers. If the customer means “largest documented reward in the supplied terms,” say that World Blue is the documented option and explain the limitation.

World Blue account operational facts, when useful to the prospect, are a $50 monthly maintenance fee, a $10,000 minimum balance requirement, up to 35 currencies, and payments in 140 supported regions. Do not imply these facts make it suitable for a business whose needs have not been assessed.

## 3. Assess whether the eventual referral can qualify
After (or while) providing the eligible referrer with the offer terms, collect these prospective-customer facts. Treat unanswered, ambiguous, or `OUT-OF-SCOPE` responses as unknown—not as passing:

- The referred person is 18 or older and is a new Rho-Bank customer with no current checking or savings account and no account closed in the last 12 months.
- The referrer and referred person have different registered addresses.
- For a business, its primary authorized signer has a different SSN from the primary owner of every existing Rho-Bank business account. Confirm who will be the signer and whether a conflict exists.
- Funding is external new money, the business will meet the $25,000/90-day condition, the money will be retained as required, and no other new-account promotion will be used.

If any condition fails, explain the referral does not qualify and do not suggest evasion or changing records. If facts are unknown, say the **outcome** cannot be confirmed; do not retract accurate terms or a conditional product recommendation made after referrer eligibility was checked.

## Conversation pattern
1. Ask briefly for the referrer ID and first-checking date, and state that these are needed before referral terms can be discussed.
2. Use the referral-history tool once an ID is supplied. Report only what it establishes (for example, no records means no observed rolling-window referrals), not unrelated eligibility claims.
3. Once the referrer clears history and tenure checks, answer a maximum-bonus question with the documented World Blue $300 referrer reward and its $25,000/90-day requirements. State precisely which other qualification facts remain unknown.
4. Do not create referrals or open accounts. If the requester separately asks to open a business checking account, first meet that separate procedure: identity verification; an existing OPEN personal checking account with at least $500; no CLOSED accounts; at most six business checking accounts; and selected account class. The documented opening action is `open_bank_account_4821`, only if actually available.

## Conservative helper
`scripts/assess_referral.py` is a local, no-action checklist for World Blue. It does not query bank records and cannot replace `get_referrals_by_user`.

Run it with one JSON object on stdin. Booleans can be `true`, `false`, or `null`/omitted for unknown; numeric counts must be nonnegative. Example schema (example values are illustrative only):
```json
{
  "program": "world_blue",
  "referrer_user_id_present": true,
  "referral_history_checked": true,
  "rolling_9_day_bonus_count": 0,
  "first_checking_tenure_days": 100,
  "world_blue_referrals_this_calendar_year": 0,
  "prospect_age_18_or_over": null,
  "prospect_new_customer_no_recent_closed_account": null,
  "different_registered_address": true,
  "business_primary_signer_no_existing_business_account": null,
  "deposit_amount": 0,
  "deposit_new_money": null,
  "deposit_within_window_days": null,
  "deposit_retention_confirmed": null,
  "other_promotion_planned": null
}
```
It emits JSON with `referrer_offer_status` (`eligible_for_documented_terms`, `ineligible`, or `needs_information`), `referral_outcome_status` (`eligible_on_stated_facts`, `ineligible`, or `needs_information`), known blockers, and unknown facts. Interpret `eligible_on_stated_facts` as an assessment only, never a bank approval or payout guarantee.
