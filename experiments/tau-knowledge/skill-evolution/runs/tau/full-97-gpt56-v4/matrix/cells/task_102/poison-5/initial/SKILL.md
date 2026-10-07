---
name: checking-referral-eligibility-advisor
description: Assess and explain checking-account referral eligibility, annual program capacity, and the cross-product rolling referral limit. Use for requests to prioritize, check, or explain personal or business checking referrals; do not use it to submit a referral or open an account.
---

# Checking Referral Eligibility Advisor

Use this Skill to provide a cautious, evidence-based referral assessment. It is advisory only: do not create referrals, open accounts, reveal referral links, or imply that a bonus is guaranteed.

## Required facts and policy rules

Apply the current product-specific terms supplied to the executor together with these cross-program rules:

- Before giving referral terms or a recommendation, check that the **referrer** is eligible to participate. Tenure is measured from the earliest Rho-Bank checking-account opening, not the current product type.
- Count only `COMPLETE` referrals toward a product's calendar-year cap.
- A referrer can receive at most two referral bonuses in a rolling nine-day period across every checking account type. The calculation is timestamp-based, not a calendar-week count. A third referral in that window is denied and cannot be reinstated during that window.
- A referred individual must be a new customer with no existing checking, savings, or closed Rho-Bank account in the preceding 12 months, and must not share the referrer's registered address.
- For a business referral, the business must have a different primary owner from any existing Rho-Bank business account, based on the primary authorized signer's SSN.
- Qualifying deposits must be new money, cannot come from another Rho-Bank account, and must remain for at least 30 days after the product's qualifying period ends. A bonus may be clawed back if the referred account closes within 90 days.
- Referral bonuses cannot be combined with another new-account promotion or sign-up bonus, and only one referral code can be applied per new account.

Product-specific age, business-age, tenure, deposit, deadline, bonus, and annual-cap requirements must come from the applicable current product terms. Do not extrapolate a term from one account product to another.

## Workflow

### 1. Classify the request

Determine whether the customer wants information, an eligibility assessment, a recommendation, or an actual account/referral action. This Skill supports only information and assessment. If the request would create or change anything, first complete every required banking-action verification and use only the declared normal banking tools; this Skill itself does not authorize an action.

### 2. Establish the referrer and verify authority where account data is accessed

Use an existing authenticated customer context only when the runtime explicitly provides one. Otherwise, obtain a user ID or exact account-holder name, locate the record with the declared user-information tool, and verify two of the four identity fields (date of birth, email, phone number, address) without disclosing the stored values. Obtain the current time and call `log_verification` with the complete returned record only after the two fields match.

If the supplied public context contains already-authorized, read-only observations, treat them as evidence for this assessment but do not claim an additional verification that did not occur. Do not request third-party SSNs, full account histories, or other sensitive information from the customer when a normal authorized eligibility check at application time is sufficient.

### 3. Verify referrer eligibility before recommendation

Check the earliest checking-account opening date using a supported normal banking tool or authorized account record, then compare it with the target product's tenure threshold. If that date is unavailable, a prior `COMPLETE` referral can support a conservative inference only when its completion necessarily proves the referrer had already met an equal-or-greater applicable tenure threshold and enough time has elapsed; state that this is an inference.

If tenure cannot be verified, do not give referral-program details or prioritize candidates. Explain that a recommendation must wait for a tenure check. Do not invent an account-opening date.

### 4. Retrieve and assess actual referral history

Call `get_referrals_by_user` for the verified referrer. Do not rely on the customer's estimates when a record is available.

For each target product:

1. Count `COMPLETE` records for that exact referred account type in the current calendar year.
2. Compare that count with the product's annual cap.
3. Evaluate all `COMPLETE` referral-bonus timestamps across account types for the rolling nine-day limit.
4. Flag a cap that is already reached as a firm blocker. Treat an incomplete, rejected, applied, or in-progress record as not consuming the completed-bonus cap unless current product terms explicitly say otherwise.

Use `scripts/analyze_referrals.py` for deterministic counting. Supply the current timestamp, the retrieved records, and a `programs` mapping built from the applicable product terms. The script does not establish tenure, person eligibility, or approval.

### 5. Assess each proposed recipient conditionally

For every proposed referral, distinguish verified facts from unresolved requirements.

- **Individual:** identify the target product; compare any provided age with that product's age requirement; require confirmation through normal checks that the person is new to Rho-Bank within the required lookback, does not share the registered address, and can meet the product deposit condition. Do not treat a first name, relationship, or an "as far as I know" statement as verification.
- **Business:** identify the target business product; compare a documented formation date with its company-age rule; require normal checks for no prior Rho-Bank relationship and a distinct primary owner/signer. Do not treat an approximate company age as a confirmed formation date.
- **Unknown target product:** ask which account is intended before applying product-specific rules or counting its product cap.

A candidate can be described as *potentially suitable if the listed checks pass*, but never as approved based on incomplete information.

### 6. Give a concise, bounded answer

After referrer eligibility is checked, present:

- the reference time and source of the referral-history result;
- actual completed counts and remaining annual capacity for each named target product, when its cap is known;
- rolling-limit status, including uncertainty caused by date-only records;
- each candidate's confirmed positives, blockers, and outstanding checks;
- a priority only among candidates that are not blocked by verified caps or the rolling rule. Make it conditional on all unresolved recipient checks; and
- the exact next information or normal verification needed if no safe priority can be given.

Do not expose another person's account status, address, signer SSN, or other private data. Do not suggest that the customer evade annual caps, rolling limits, address restrictions, or promotion-stacking rules.

## Running the helper

Invoke `scripts/analyze_referrals.py` with JSON on stdin through the packaged script runtime. Input schema:

```json
{
  "as_of": "ISO-8601 timestamp or date",
  "referrals": [
    {
      "referred_account_type": "string",
      "referral_status": "COMPLETE or another status",
      "date": "ISO-8601 timestamp or date"
    }
  ],
  "programs": {
    "Exact Account Type": {"annual_cap": 0}
  }
}
```

`annual_cap` is optional where current product terms do not provide one. The output reports current-calendar-year completed counts, known annual capacity, records certainly in the rolling window, boundary records needing timestamps, and data-quality issues. Validate that the output's `as_of_year` and product names match the assessment before using it. A date-only record exactly nine calendar days old is intentionally treated as indeterminate because the policy uses exact timestamps.

## Failure handling

- If identity or authorized account context is unavailable, provide only general, non-personal referral guidance and request the minimum needed verification.
- If the earliest checking opening date cannot be checked and no conservative evidence supports tenure, stop before recommendation.
- If referral history, target product terms, or exact account type is unavailable, do not calculate a cap or claim remaining capacity.
- If a rolling-window boundary cannot be resolved from date-only data, obtain timestamps or state a conservative result rather than claiming a slot is available.
- If a tool returns an error, do not retry an unknown action and do not infer the missing result. Explain the limitation or use the appropriate support path.
