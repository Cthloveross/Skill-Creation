---
name: checking-referral-requirements
version: 1.1.0
description: Assess checking-account referral requirements, completed-referral annual caps, and the shared rolling nine-day cap for Light Green, Gold Years, and Sky Blue. Use when referral eligibility facts, referral history, or referrer tenure may be incomplete.
---

# Checking referral requirements

Use this Skill for requests about checking referral eligibility, limits, program terms, or multiple proposed referrals. It provides an evidence-based assessment only; it does not submit referrals, open accounts, or promise bonuses.

## Required workflow

1. **Assess the referrer before recommending a referral.** Determine the date the customer first opened *any* Rho-Bank checking account. Tenure is measured from that earliest checking opening, not from the current product.
   - Light Green: 14 days.
   - Gold Years: 30 days.
   - Sky Blue: 45 days.
   If the earliest opening date is unavailable through the normal runtime, explicitly say that referrer tenure cannot be validated. Do not infer tenure from referral history or product type.
2. When caps are relevant, obtain the available referral history with normal banking tools. Count only `COMPLETE` records as completed referral bonuses.
3. Preserve a **known-facts ledger** across the conversation and clarifications. Do not ask again for, or list as missing, a fact already supplied by the customer.
   - Apply each supplied fact to the relevant condition. For example, a stated age of 19 satisfies Light Green's 13–24 age condition; this does not resolve independent new-customer, address, tenure, or cap conditions.
   - Say separately which facts pass, which fail, and which remain unconfirmed. An unconfirmed fact is not a failure, but it prevents validation.
4. Use `scripts/assess_referrals.py` to calculate repeatable annual and rolling-cap results and to produce candidate fact assessments. Supply the observed records and known customer facts at runtime.
5. Give requested program requirements only after the referrer assessment has been attempted and any unavailable tenure evidence has been identified. Do not represent a proposed referral as approved, confirmed, or ready to submit while required facts are unresolved.

## General referral requirements

For every checking referral:

- The referred party must be a new Rho-Bank customer, with no current checking or savings account and no account closed within the preceding 12 months.
- The referrer and an individual referred may not have the same registered address.
- Referred individuals generally must be at least 18. Light Green permits minors with a guardian, subject to its 13–24 primary-holder age range.
- A referred business must be new to Rho-Bank. Its primary authorized signer's SSN must not be associated with an existing Rho-Bank business account.
- Qualifying deposits must be new money, not a transfer from another Rho-Bank account, and must remain for at least 30 days after the qualifying period ends.
- A referral offer cannot be combined with another new-account promotion or sign-up bonus, and one referral code may be used per new account.
- A bonus may be clawed back if the referred account closes within 90 days; both accounts must remain in good standing.
- Across all checking products, the referrer may receive at most two successful referral bonuses in any rolling nine-day window. A third or later referral in that window is automatically denied and cannot be reinstated during that window. This shared limit is distinct from each product's annual cap.

## Product terms

| Program | Referrer / referred reward | Annual cap | Referred-party eligibility and qualifying deposit | Referrer tenure |
|---|---:|---:|---|---:|
| Light Green | $15 / $25 | 3 | Primary holder age 13–24; a minor needs a guardian. Deposit at least $100 within 90 days. | 14 days |
| Gold Years | $50 / $75 | 6 | Individual age 62 or older. Deposit $1,000 within 90 days. | 30 days |
| Sky Blue | $150 / $250 | 8 | Startup formed within 4 years; stated funding requirement is 0. Deposit at least $10,000 within 90 days. | 45 days |

## Calculator

Run `scripts/assess_referrals.py` with a JSON object on stdin. It writes one JSON object on stdout and performs no banking action.

Input schema:

```json
{
  "as_of": "2025-01-01T12:00:00-05:00",
  "referrals": [
    {
      "referral_id": "optional-id",
      "referred_account_type": "Gold Years Account",
      "referral_status": "COMPLETE",
      "date": "2025-01-01T09:30:00-05:00"
    }
  ],
  "candidates": [
    {
      "label": "person or company label",
      "program": "Gold Years",
      "age": 62,
      "new_customer_confirmed": true,
      "different_address_confirmed": true,
      "company_age_years": null,
      "primary_owner_no_existing_business_confirmed": null,
      "guardian_confirmed": null
    }
  ],
  "referrer_tenure_days": null
}
```

Dates may be ISO timestamps, `YYYY-MM-DD`, or `MM/DD/YYYY`. Use timestamps whenever available. The output reports `precision: "date_only"` if a rolling-window boundary cannot be evaluated at timestamp precision. Candidate results include `satisfied_conditions`, `missing_conditions`, and `known_failures`; use all three lists in the response.

Example executor call:

```text
run_skill_script(relative_path="scripts/assess_referrals.py", input_json={"as_of":"<current timestamp>","referrals":<retrieved referral records>,"candidates":<known facts>,"referrer_tenure_days":<calculated days or null>})
```

## Customer-facing response checklist

For each proposed referral, provide a compact status with these separate elements:

1. **Known satisfied facts** — explicitly apply supplied facts, including a known qualifying age.
2. **Annual result** — state completed bonuses and the program cap, such as `3 completed bonuses; annual cap of 3`, and whether capacity remains.
3. **Shared rolling result** — identify the number of completed bonuses in the current nine-day window and any timestamp limitation.
4. **Unresolved or failed facts** — list only facts not already known. For individuals, distinguish new-customer and different-address confirmation. For businesses, distinguish new-to-Rho-Bank and primary-signer SSN confirmation.
5. **Conditional conclusion** — if tenure, party eligibility, or timing is unresolved, say the referral cannot yet be validated or confirmed. Do not recommend submitting it as though it is approved.

When a full requirements summary is requested despite unresolved facts, provide the terms above while retaining the conditional conclusion. Before sending, verify that known facts were not re-requested, an exhausted annual cap was not described as available, the annual and shared rolling caps were not conflated, and unavailable earliest-checking evidence was described as unverified rather than invented.

Status definitions when requested: `COMPLETE` means account opening and bonus criteria were met; `IN_PROGRESS` means the account is open but deposit criteria remain; `NO_PROGRESS` means no application; `APPLIED` means awaiting a decision; `REJECTED` means denied; `ERROR` means a system error.
