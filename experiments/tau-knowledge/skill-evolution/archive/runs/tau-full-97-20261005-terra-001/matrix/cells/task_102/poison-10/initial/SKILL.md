---
name: checking-referral-requirements
version: 1.0.0
description: Provide accurate checking-account referral requirements and assess observable annual and rolling referral limits. Use for questions about Light Green, Gold Years, or Sky Blue referrals, especially when candidate eligibility details or referrer tenure are incomplete.
---

# Checking referral requirements

Use this Skill when a customer asks whether they can refer someone, asks for the requirements for a referral program, or has several proposed referrals. It supports informational replies and limit calculations; it does **not** submit referrals or make banking changes.

## Required order of work

1. **Check the referrer first, before giving a recommendation that they send a referral.** Establish the date the referrer first opened any Rho-Bank checking account. Tenure is based on that earliest checking-account opening, not the account product currently held.
   - Light Green requires 14 days of tenure.
   - Gold Years requires 30 days.
   - Sky Blue requires 45 days.
   - If the earliest-checking date cannot be obtained through the available runtime, explicitly say referrer tenure cannot be validated. Do not infer it from the current product type.
2. Retrieve the referrer's referral history using the normal banking tools when an annual-cap or rolling-window assessment is requested. Count only `COMPLETE` records as successful referral bonuses.
3. Use `scripts/assess_referrals.py` for repeatable counting. It is a calculator only; tool results and customer-provided candidate facts must be supplied as input.
4. Identify which conditions are known versus unconfirmed for every proposed referral. Unknown new-customer, address, or business-owner facts mean the referral cannot be validated, not that the person is ineligible.
5. Give the program requirements requested. Keep separate:
   - account-opening eligibility;
   - referrer eligibility and caps;
   - referred-person/company conditions;
   - bonus qualification and retention conditions.
6. Do not create or promise a referral, bonus, approval, or exception. The normal banking tools—not this Skill—would be required for any account or referral action.

## General requirements to include

For all checking referrals:

- A referred individual must be a new Rho-Bank customer, with no current account and no checking, savings, or closed account in the preceding 12 months.
- The referrer and individual referred cannot be registered at the same address.
- The referred person must generally be at least 18. Light Green is the exception: a minor may qualify with a guardian, subject to that product's 13–24 primary-holder age range.
- For a business referral, the referred business must be new to Rho-Bank and its primary authorized signer's SSN cannot be associated with an existing Rho-Bank business account.
- The qualifying deposit must be new money; a transfer from another Rho-Bank account does not qualify. It must remain in the new account for at least 30 days after the qualifying period ends.
- A referral bonus cannot be combined with another new-account promotion or sign-up bonus, and only one referral code can be used per new account.
- A referred account closed within 90 days may result in a bonus clawback. Both accounts must remain in good standing.
- Across **all** checking products, no more than two successful referral bonuses may occur in any rolling nine-day period. A third or later referral in that window is automatically denied and cannot be reinstated during that same window. This cap is not per account type.

## Product requirements

Use the following evidence-derived terms; do not substitute terms from an unrelated checking product.

| Program | Referrer bonus / referred welcome bonus | Annual cap | Referred account eligibility and qualifying deposit | Referrer tenure |
|---|---:|---:|---|---:|
| Light Green | $15 / $25 | 3 | Primary holder age 13–24; minors require a guardian. Deposit at least $100 within 90 days of opening. | 14 days |
| Gold Years | $50 / $75 | 6 | Person must be age 62 or older. Deposit $1,000 within 90 days of opening. | 30 days |
| Sky Blue | $150 / $250 | 8 | Startup/company must be within 4 years of formation; its stated funding requirement is 0. Deposit at least $10,000 within 90 days of opening. | 45 days |

The annual cap is specific to the program, while the nine-day cap is shared across every checking product.

## Running the calculator

`scripts/assess_referrals.py` accepts one JSON object on stdin and emits one JSON object on stdout.

Input schema:

```json
{
  "as_of": "2025-01-01T12:00:00-05:00",
  "referrals": [
    {
      "referral_id": "optional-record-id",
      "referred_account_type": "Gold Years Account",
      "referral_status": "COMPLETE",
      "date": "2025-01-01T09:30:00-05:00"
    }
  ],
  "candidates": [
    {
      "label": "optional descriptive label",
      "program": "Gold Years",
      "age": 62,
      "new_customer_confirmed": true,
      "different_address_confirmed": true,
      "primary_owner_no_existing_business_confirmed": null,
      "company_age_years": null
    }
  ],
  "referrer_tenure_days": null
}
```

`as_of` and referral `date` accept ISO timestamps or `MM/DD/YYYY` / `YYYY-MM-DD` dates. Supply timestamps whenever possible: the program cap is based on exact timestamps. The calculator marks a rolling-window result `precision: "date_only"` when only dates are available and warns that boundary cases require timestamps.

The output contains annual completed counts, each program's remaining annual capacity, the known number of completed bonuses inside the current nine-day window, proposed-candidate missing facts, and warnings. It never treats absent facts as passing eligibility.

Example invocation by the executor:

```text
run_skill_script(relative_path="scripts/assess_referrals.py", input_json={"as_of":"<current timestamp>","referrals":<normal-tool referral records>,"candidates":<facts supplied by customer>,"referrer_tenure_days":<earliest-account calculation or null>})
```

## Response construction and validation

A complete customer-facing answer should:

1. State that the information is program requirements rather than a confirmation if required candidate facts or earliest-checking tenure are unavailable.
2. List the applicable product's reward, annual cap, target eligibility, deposit amount/deadline, and referrer-tenure requirement.
3. State the shared new-customer/address or business-owner requirements and the shared rolling nine-day restriction.
4. If history was retrieved, report counts exactly as calculated, distinguishing the annual product cap from the shared rolling cap. Do not rely on the customer's estimate when records are available.
5. State outstanding items precisely—for example, confirmation that an individual is a new customer and has a different registered address, or confirmation that a business signer's SSN has no existing business-account association.
6. Mention the new-money, 30-day retention, non-stacking, good-standing, and possible 90-day closure-clawback terms where providing a full requirements summary.

Before sending, verify that no unknown requirement was presented as confirmed, that no annual cap was confused with the rolling cap, and that a date-only history was not described as an exact timestamp-level rolling determination.

Referral statuses, when asked: `COMPLETE` means the referred person opened an account and met bonus criteria; `IN_PROGRESS` means the account is open but deposit criteria are outstanding; `NO_PROGRESS` means no application; `APPLIED` means awaiting decision; `REJECTED` means denied; and `ERROR` means a system error.
