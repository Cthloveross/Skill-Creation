---
name: checking-referral-eligibility
summary: Assess and explain checking-account referral eligibility, program fit, annual capacity, timing, and outstanding requirements for individual and business referrals.
---

# Checking Referral Eligibility

Use this Skill when a customer asks about checking-account referral eligibility, product fit, referral capacity, timing, or next steps. It provides an assessment only: no declared tool creates a referral, so never claim to submit, reserve, or promise one.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Viewing or using a customer's nonpublic profile or referral history is a banking action. A name or user ID by itself is not identity verification.

## Safe workflow

1. **Verify before looking up nonpublic history or giving a personalized referral assessment.** Ask the customer for two of date of birth, profile email, phone number, or registered address. Look up their profile with a declared lookup tool, compare both supplied values, get the current time, then call `log_verification` using the complete returned profile and timestamp. Do not log or proceed on a mismatch or fewer than two confirmed values.
2. **Check the referrer before recommending terms or a product.** After verification, retrieve `get_referrals_by_user`. Determine tenure from the earliest checking opening using an authorized checking-history capability if one exists. Do not use a credit-card opening date or the current account product as a substitute.
3. **When opening history is unavailable, distinguish the unavailable fact from what can be safely determined.** Do not invent the first checking-opening date. An authorized historical `COMPLETE` referral in a known program can establish that the referrer had already met *that same program's* tenure rule as of that historical completion date; because tenure only grows, it can confirm current tenure for that program. Otherwise request the first checking date or a supported account-history review. Transfer only when a supported review is needed and cannot otherwise be completed.
4. Use `scripts/referral_audit.py` with the verified facts, current time, and retrieved records. The helper can conservatively derive present tenure from authorized historical `COMPLETE` records in packaged programs; do not add inferred dates to the input. Resolve missing referred-party facts before saying a referral is eligible.
5. Explain determinate capacity separately from unresolved eligibility. A full annual cap is a blocker even when other facts remain unknown. Date-only referral records make a rolling-window result provisional; obtain timestamps before a boundary-sensitive final approval. Do not create or promise a referral.

## Referral rules

### All checking referral programs

- At most **two referral bonuses** may be received in a rolling nine-day window across all checking products. It is based on exact timestamps, not calendar weeks; an excess referral is automatically denied and cannot be reinstated in that window.
- The referred party must be a new Rho-Bank customer, with no existing account and no account closed during the last 12 months; the referred party must have a different registered address than the referrer.
- A referred person must generally be 18 or older; Light Green is the stated minor-with-guardian exception.
- A referred business needs a primary authorized signer whose SSN is not the primary owner of an existing Rho-Bank business account.
- Tenure is based on the referrer's earliest Rho-Bank checking opening, regardless of account type.
- The qualifying deposit must be new money (not an internal Rho-Bank transfer), remain for 30 days after the qualifying period, and both accounts must remain in good standing. A closure within 90 days can cause clawback.
- The bonus cannot be combined with another new-account promotion or signup bonus; only one referral code applies.

| Program | Referrer tenure | Referred-party criteria | Qualifying deposit | Annual cap | Bonuses |
|---|---:|---|---|---:|---|
| Dark Green Account | 45 days | Age 17–26; current student enrollment verification | $1,000 in 60 days | 6 | $40 / $30 |
| Gold Years Account | 30 days | Age 62+ | $1,000 in 90 days | 6 | $50 / $75 |
| Sky Blue Account | 45 days | Company formed within 4 years; eligible distinct primary signer | $10,000 in 90 days | 8 | $150 / $250 |

For Dark Green, current-semester proof must be readable, unredacted, and not password-protected: an official enrollment letter, current schedule/registration summary, student-portal screenshot, or tuition invoice/receipt. It must show the student's name, institution, current term, and enrollment status.

Do not treat a failed/no-result customer search as proof of newness, address difference, or business-owner eligibility. Treat approximate company age as a lead requiring confirmation from formation documentation. For annual and rolling counts, only `COMPLETE` referrals count as bonuses received.

## Audit script

Run `python3 scripts/referral_audit.py` with JSON on stdin. It emits JSON on stdout and makes no bank calls.

```json
{
  "as_of": "ISO-8601 date or datetime",
  "referrals": [{"referred_account_type":"Gold Years Account","referral_status":"COMPLETE","date":"2025-01-02T10:00:00-05:00"}],
  "referrer": {
    "identity_verified": true,
    "first_checking_opened": "ISO-8601 date or datetime, optional when historical COMPLETE evidence is sufficient"
  },
  "requests": [{
    "program": "Dark Green Account | Gold Years Account | Sky Blue Account",
    "referred": {
      "new_customer_confirmed": true,
      "no_closed_account_last_12_months_confirmed": true,
      "different_registered_address_confirmed": true,
      "no_other_promotion_confirmed": true,
      "age": 19,
      "current_enrollment_verified": true,
      "company_age_years": 3,
      "primary_signer_confirmed": true,
      "primary_signer_has_no_existing_business_confirmed": true
    }
  }]
}
```

Only relevant fields are needed: age and enrollment for Dark Green; age for Gold Years; company age and signer confirmations for Sky Blue. If the checking-opening date is absent, the helper independently considers authorized historical `COMPLETE` records in the packaged programs and uses only a conservative tenure lower bound. The output has `errors`, `rolling_window`, and one assessment per request. Validate that `errors` is empty; report `rolling_window.exact: false` as provisional; and call an item eligible only if `eligible_for_recommendation` is true.

## Communication

Before verification, request the two profile fields without revealing account history. After verification, give a concise program-by-program result: known annual use and slots, rolling-window qualification/provisional status, clear blockers, and missing facts. If a customer asks for their exact first checking-open date but no authorized tool exposes it, say that the date cannot be retrieved with the supported tools; still provide any conservative tenure conclusion supported by historical completed referrals. Do not disclose or imply that a referred person is new, at a different address, or business-owner eligible unless that fact was actually confirmed.
