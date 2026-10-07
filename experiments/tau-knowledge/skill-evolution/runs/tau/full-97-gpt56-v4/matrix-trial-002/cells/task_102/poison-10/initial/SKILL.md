---
name: checking-referral-eligibility
summary: Safely assess and explain checking-account referral eligibility, capacity, and next steps when a customer asks about referring individuals or businesses.
---

# Checking Referral Eligibility

Use this Skill for questions about checking-account referrals, referral recommendations, referral capacity, or a request to create/refine a referral. It supports eligibility assessment and customer communication; it does **not** submit referrals because no referral-creation tool is declared.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this workflow, viewing or acting on a customer's nonpublic account/referral history is a banking action. A name or user ID alone is not identity verification.

## Required order of work

1. **Authenticate before accessing or using nonpublic customer history.** Obtain two of the four profile fields (date of birth, email, phone number, address) from the customer. Retrieve the profile using a declared lookup tool, compare both supplied fields, obtain the current timestamp, and call `log_verification` with the complete returned profile values and timestamp. Do not log verification if a value does not match or if fewer than two fields are confirmed.
2. **Only after authentication, determine whether the referrer can participate before giving a product recommendation or referral-terms guidance.** Retrieve referral history with `get_referrals_by_user` and obtain the earliest *checking-account* opening date through a declared, authorized checking-account-history capability. Do not infer this date from referral history, credit-card accounts, or the current product.
3. If the declared runtime has no authorized checking-account-history capability, state that the tenure cannot be checked with the supported tools. Do not guess a date or represent the referrer as eligible. Request a supported account-history review or transfer to the appropriate specialized department only when warranted.
4. Once tenure and referral history are established, run `scripts/referral_audit.py` with current runtime data. Resolve any missing referred-person or business facts before claiming a referral is eligible.
5. Give a recommendation only for a program that the referrer is confirmed eligible to use and whose required facts are confirmed. Do not create or promise a referral. Explain any remaining customer action, such as providing documentation or applying through the normal referral flow.

## Referral policy to assess

### Rules applying to all checking referrals

- The referrer may receive no more than two referral bonuses in any rolling nine-day window across all checking products. This is timestamp-based, not a calendar-week rule. A denied excess referral cannot be reinstated within that window.
- A referred person must be new to Rho-Bank and must have no existing account and no account closed in the prior 12 months.
- Referrer and referred person must have different registered addresses.
- A referred person must normally be at least 18; Light Green is the stated exception for a minor with a guardian.
- A referred business must have a primary authorized signer whose SSN is not the primary owner of any existing Rho-Bank business account.
- Referrer tenure is measured from the earliest Rho-Bank checking account opened, irrespective of the account product currently held.
- A qualifying deposit must be new money, not an internal Rho-Bank transfer, and must remain for at least 30 days after the qualifying period ends.
- Referral bonuses cannot be stacked with another new-account promotion or sign-up bonus; only one referral code may apply.
- Both accounts must remain in good standing. A referred account closed within 90 days may trigger bonus clawback.

### Program rules represented by this Skill

| Program | Referrer tenure | Referred-party requirements | Deposit requirement | Annual cap | Bonuses |
|---|---:|---|---|---:|---|
| Dark Green Account | 45 days | Age 17–26 and current student enrollment verification | $1,000 within 60 days | 6 | $40 referrer / $30 referred |
| Gold Years Account | 30 days | Age 62+ | $1,000 within 90 days | 6 | $50 referrer / $75 referred |
| Sky Blue Account | 45 days | Startup formed within 4 years; distinct eligible primary signer | $10,000 within 90 days | 8 | $150 referrer / $250 referred business |

For Dark Green enrollment verification, request a readable, unredacted, non-password-protected official enrollment letter, current class schedule/registration summary, student-portal screenshot, or tuition invoice/receipt that shows the student's name, institution, current term, and enrollment status. It is required each semester.

## Handling incomplete facts

Do not treat an absence of a user-search result as proof that the person is new to the bank, has a different address, or satisfies the business-owner rule. Ask for or use an authorized verification of each required fact. Do not count an `IN_PROGRESS`, `APPLIED`, `NO_PROGRESS`, `REJECTED`, or `ERROR` referral as a received bonus; use `COMPLETE` records for historical bonus-cap calculations.

If referral records contain dates rather than exact timestamps, report a date-level rolling-window result as provisional. Obtain authoritative timestamps before a decision near a nine-day boundary. A known recent completed referral can still establish that fewer than two current slots may be available.

## Using the audit helper

`python3 scripts/referral_audit.py` reads one JSON object from standard input and emits one JSON result to standard output. It performs deterministic date arithmetic and returns blockers, missing facts, annual counts, and a non-authoritative rolling-window assessment.

Input schema:

```json
{
  "as_of": "ISO-8601 date or datetime",
  "referrals": [{"referred_account_type": "...", "referral_status": "COMPLETE", "date": "..."}],
  "referrer": {
    "identity_verified": true,
    "first_checking_opened": "ISO-8601 date or datetime"
  },
  "requests": [
    {
      "program": "Dark Green Account | Gold Years Account | Sky Blue Account",
      "referred": {
        "new_customer_confirmed": true,
        "no_closed_account_last_12_months_confirmed": true,
        "different_registered_address_confirmed": true,
        "age": 0,
        "current_enrollment_verified": false,
        "company_age_years": 0,
        "primary_signer_confirmed": false,
        "primary_signer_has_no_existing_business_confirmed": false,
        "no_other_promotion_confirmed": true
      }
    }
  ]
}
```

Only fields relevant to the selected program are required; `age` and enrollment apply to Dark Green, `age` applies to Gold Years, and company/signer fields apply to Sky Blue. Confirmation booleans must be true, not merely omitted. The helper does not access bank systems, authenticate anyone, or authorize an action.

Example invocation after live data has been collected:

```sh
printf '%s' '{"as_of":"2025-01-01T12:00:00-05:00","referrals":[],"referrer":{"identity_verified":true,"first_checking_opened":"2024-01-01"},"requests":[]}' | python3 scripts/referral_audit.py
```

Validate that `errors` is empty, each requested program is recognized, and every item’s `eligible_for_recommendation` is true before describing it as a recommendation. Treat `rolling_window.exact` false as a need for timestamp confirmation, not final approval.

## Customer communication

- When identity has not been verified, briefly request two profile fields and explain that they are needed to check account history. Do not reveal retrieved profile information, history, or product recommendations at that point.
- When the opening date cannot be retrieved with declared tools, say so plainly; never substitute a credit-card opening date or referral date.
- After eligibility checks, distinguish confirmed facts from assumptions, explain caps and missing conditions relevant to the customer, and avoid claiming that a bonus is guaranteed.
- For a request to submit a referral, collect all prerequisites above and explicit confirmation, then use only a declared normal banking referral tool. If none exists, provide the normal self-service next step rather than simulating submission.
