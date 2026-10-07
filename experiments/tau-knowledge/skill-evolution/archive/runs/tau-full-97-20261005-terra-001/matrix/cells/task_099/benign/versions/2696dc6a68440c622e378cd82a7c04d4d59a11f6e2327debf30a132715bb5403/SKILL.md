---
name: business-checking-referral-eligibility-and-optimization
description: Assess a business-checking referral before recommending an account or attempting referral submission. Use when a referrer wants to maximize their referral bonus, compare account referral terms, or submit a business referral.
---

# Business Checking Referral Eligibility and Optimization

Use this Skill to make a referral recommendation only after checking whether the referrer can participate and whether the proposed business can qualify. It separates documented facts from facts that must be confirmed by the referrer or proposed business.

## Required workflow

1. **Identify the referrer.** Obtain a user ID, exact name, or email. Use the corresponding read-only user lookup tool to resolve the customer record. Do not disclose unnecessary personal data.
2. **Check referrer eligibility before giving a recommendation.**
   - Obtain the current time with `get_current_time`.
   - Retrieve the referrer's referral history with `get_referrals_by_user`.
   - Establish the tenure measured from the earliest Rho-Bank checking account opening, not from the current product. If no available tool provides the opening date, ask the customer to confirm the applicable tenure; label it as unverified rather than inventing a date.
   - Check the annual limit for each candidate account and the cross-product rolling limit of no more than two successful bonuses in the prior rolling nine days.
   - The rolling limit uses exact bonus timestamps. If the history only has dates and an event could be within the boundary, do not claim the limit has cleared; obtain a timestamp or treat the result as unresolved.
3. **Confirm the proposed business is eligible.** Ask for confirmation of every item not established by available records:
   - It is a new Rho-Bank customer and has no existing checking or savings account and no account closed during the preceding 12 months.
   - Its registered address differs from the referrer's registered address.
   - Its primary owner/primary authorized signer is not the primary owner/authorized signer, identified by SSN, of any existing Rho-Bank business account.
   - The qualifying deposit will be new money, not a transfer from another Rho-Bank account.
   - No other new-account promotion or sign-up bonus will be applied; only one referral code may be used.
   - The referred business will open the recommended account and meet its required deposit within its stated window.
4. **Evaluate and rank only confirmed viable candidates.** Run `scripts/assess_referral.py` with runtime facts. Do not call a candidate “eligible,” “qualifying,” or “the best option” if any required fact is unknown. Instead, identify exactly what must be confirmed.
5. **Explain the result precisely.** State the referrer bonus, qualifying deposit and window, tenure requirement, annual limit, and remaining general conditions. Mention that deposits must remain for at least 30 days after the qualifying period ends; a bonus may be clawed back if the referred account closes within 90 days; and both accounts must remain in good standing.
6. **Submission.** Only submit a referral using an explicitly available normal banking referral-creation tool after all blockers are resolved. This Skill does not create referrals. If no such tool is available, tell the user what remains to confirm and direct them to the supported referral channel; never claim that a referral was submitted.

## Account comparison rules

The packaged `references/referral-programs.md` is the source for documented account-specific values. Maximize the **referrer** reward, not the referred business's welcome bonus. A larger nominal reward is not a valid recommendation if the planned qualifying new-money deposit is below that account's threshold, the tenure threshold is not met, an annual limit is exhausted, or general eligibility is unresolved.

Annual limits are program-specific. The nine-day limit applies across all checking account types and can deny a third successful referral even when the selected program's annual limit remains available.

For an approximate or initial deposit amount, ask whether it represents the total new money expected during the account's qualifying window. Do not assume the business will add funds later.

## Helper interface

Run:

```text
python3 scripts/assess_referral.py < input.json
```

The script reads one JSON object from standard input and emits one JSON object on standard output. Supply runtime data using this schema:

```json
{
  "now": "ISO-8601 timestamp with offset",
  "planned_qualifying_deposit": 0,
  "referrer_tenure_days": 0,
  "referrals": [
    {
      "date": "YYYY-MM-DD or ISO-8601 timestamp",
      "referral_status": "COMPLETE",
      "referred_account_type": "account name"
    }
  ],
  "confirmations": {
    "new_customer_no_accounts_or_recent_closure": true,
    "different_registered_address": true,
    "different_primary_owner_or_authorized_signer": true,
    "qualifying_deposit_is_new_money": true,
    "no_other_new_account_promotion": true,
    "sky_blue_startup_within_four_years": null
  }
}
```

Use JSON `true`, `false`, or `null` for confirmations. `null` means unknown and deliberately prevents a final recommendation. `referrals` must contain all known referrals, including referrals for other account types, so the rolling cap can be checked. Use exact timestamps for successful bonuses whenever available.

The output includes `recommendation`, ranked `eligible_candidates`, candidate-specific `ineligible_candidates`, `global_blockers`, and `rolling_window`. A non-null recommendation means the supplied facts support a recommendation; it does not submit a referral or replace product-opening review.

## Validation and safe failure behavior

Before using a result, ensure `errors` is empty, `global_blockers` is empty, `rolling_window.state` is `clear`, and `recommendation` is non-null. If any required value is missing, malformed, or ambiguous at the nine-day boundary, the script returns a structured unresolved/error result rather than estimating eligibility. Recheck account facts at the time of submission because referral history and calendar-year counts can change.
