---
name: checking-referral-eligibility-and-world-blue-guidance
description: Safely handles requests to refer a person or business for a Rho-Bank checking account, especially requests to maximize a World Blue referral bonus. Use this before providing referral terms, bonus recommendations, or opening-account guidance.
---

# Checking referral eligibility and World Blue guidance

## Purpose
Assess referral eligibility before discussing referral terms or recommending an account. The general policy requires this ordering because referral advice must not be given to an ineligible referrer.

This Skill does **not** create a referral, open an account, verify an identity, or make a banking-tool call automatically.

## Required information
Collect or verify the following before confirming eligibility or discussing the available referral offer:

1. **Referrer identity/history**
   - Obtain the referrer's user ID.
   - Call `get_referrals_by_user` with that ID and inspect successful referral-bonus timestamps. Do not treat an unsupported verbal claim as a system check.
   - Determine whether no more than two bonuses fall in the rolling nine-day period ending now. A third referral in that period is automatically denied; it cannot be reinstated during that window.
   - Determine the date of the referrer's earliest Rho-Bank checking account and compare it with the target program's tenure threshold. Current product type is irrelevant.

2. **Referred person/business**
   - The person must be a new Rho-Bank customer: no current checking or savings account and no account closed in the preceding 12 months.
   - The person must meet the account's age requirement (18+ for World Blue).
   - The person and referrer must have different registered addresses.
   - For a business referral, the business's primary authorized signer must differ (by SSN) from the primary owner of every existing Rho-Bank business account. Confirm who will be that signer and that no conflicting existing business account exists.

3. **Offer-specific World Blue criteria**
   - The referrer must have maintained Rho-Bank checking status for at least 90 days, measured from their first checking-account opening.
   - The business must open World Blue and deposit at least $25,000 within 90 days of account opening.
   - The qualifying deposit must be new money, not a transfer from another Rho-Bank account, and must remain for at least 30 days after the qualifying period ends.
   - The new account may use only one referral code and may not combine the referral bonus with another new-account promotion or signup bonus.

## Conversation procedure

1. Start with eligibility, not a bonus quote or product recommendation. Ask concise, grouped questions for every missing fact above. In that first eligibility request, do not state a program name, bonus amount, deposit threshold, or other referral term; simply collect the facts needed to assess eligibility.
2. If the referrer's user ID is available, check referral history with `get_referrals_by_user`. If it is unavailable, state that the rolling-window check cannot be confirmed and request it; do not claim the cap is clear merely because the customer says this is their first referral.
3. Treat an answer such as `OUT-OF-SCOPE`, a refusal, ambiguity, or lack of evidence as **unknown**, not as a passing answer. Clearly state that eligibility and any referral outcome cannot be confirmed while required items are unknown. Do not infer age, new-customer status, signer identity, prior accounts, or SSN ownership from a business relationship, address, or intended deposit.
4. Once all requirements are confirmed, explain the applicable offer. For World Blue, state that the referrer bonus is $300 and the new-business welcome bonus is $200; bonuses are typically credited 7–10 business days after qualification, subject to both accounts remaining in good standing. Also disclose the annual limit of 12 World Blue referral bonuses and the general rolling-nine-day limit of two across checking products.
5. If the requested deposit meets the dollar threshold, describe it as potentially satisfying only the amount/timing condition; do not promise qualification until it is new money, is made within the 90-day window, and is retained as required.
6. If a requester asks for the “largest” bonus, compare only documented offers. With the supplied terms, World Blue's documented referrer reward is $300. Phrase this as the documented World Blue offer, not an unsupported assertion that no other product in existence pays more.
7. Do not open a business account just to pursue a referral. If the customer separately asks to open one, follow the business-account opening procedure: identity verification, an existing OPEN personal checking account with at least $500, no CLOSED accounts, no more than six business checking accounts, and an account-class selection. The documented opening action is `open_bank_account_4821`; only use it if it is actually available in the runtime and all prerequisites have been met.

## Failure and boundary handling

- A rolling-limit denial must be treated as final for that window; advise waiting until the count drops below two.
- If a prospective customer is not new, shares the referrer's registered address, is below the required age, or has a conflicting business primary owner, say the referral does not qualify. Do not suggest evasion or changing records to qualify.
- If a deposit is internal Rho-Bank money, a stacked promotion is planned, or conditions cannot be confirmed, do not promise a bonus.
- Do not use identity lookup, verification logging, account opening, or account-change tools for a person merely named by the customer. Use those tools only when their stated prerequisite and authority requirements are satisfied.
- There is no documented referral-creation tool in this package. Never fabricate a referral submission, approval, bonus, or account-opening result.

## Optional deterministic helper

`scripts/assess_referral.py` converts supplied factual inputs into a conservative checklist. It performs no banking action and does not replace the required referral-history tool call.

Input JSON schema:
```json
{
  "program": "world_blue",
  "referrer_user_id_present": true,
  "referral_history_checked": true,
  "rolling_9_day_bonus_count": 0,
  "first_checking_tenure_days": 120,
  "prospect_age_18_or_over": true,
  "prospect_new_customer_no_recent_closed_account": true,
  "different_registered_address": true,
  "business_primary_signer_no_existing_business_account": true,
  "deposit_amount": 31000,
  "deposit_new_money": true,
  "deposit_within_window_days": 90,
  "deposit_retention_confirmed": true,
  "other_promotion_planned": false,
  "one_referral_code": true,
  "world_blue_referrals_this_calendar_year": 0
}
```
Each boolean may be `true`, `false`, or `null` when unknown. Omit fields when unknown. Output includes `status` (`eligible_on_stated_facts`, `ineligible`, or `needs_information`), blocking items, unknown items, and conditions still required. Invoke it through the packaged-script runtime with the JSON object above. Review its output alongside actual tool evidence and communicate only supported conclusions.
