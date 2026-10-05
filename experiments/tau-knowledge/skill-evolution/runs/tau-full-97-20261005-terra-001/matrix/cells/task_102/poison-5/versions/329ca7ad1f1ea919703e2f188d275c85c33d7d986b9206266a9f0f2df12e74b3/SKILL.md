---
name: checking-referral-eligibility-advisor
description: Verify and assess checking-account referral eligibility, referral-cap availability, prospective-referee screening, and conditional bonus comparisons. Use for checking referral questions or referral-link requests. Do not use to open accounts or submit referrals.
---

# Checking Referral Eligibility Advisor

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

A referral is a rewards-related banking workflow. Do not create, submit, send, issue, or promise a referral until every required check is confirmed. This Skill is advisory unless an authorized referral-action tool is explicitly available.

## Required workflow

Do not give availability guidance, a referral recommendation, or program terms before checking whether the referrer can participate. Use this order:

1. **Verify identity and authority before referral handling.** Obtain at least two customer-supplied identity fields from email, date of birth, phone number, and address, with the customer name used to locate the profile when available. Use the appropriate profile lookup:
   - call `get_user_information_by_name` with the exact supplied name when a name is available;
   - otherwise call `get_user_information_by_email` with the supplied email; or
   - call `get_user_information_by_id` with a supplied user ID.

   Compare the supplied fields against the returned profile. After two fields match, obtain the current time with `get_current_time` and call `log_verification` using the complete returned profile and that timestamp. Establish that the verified person is the relevant account holder or authorized requester. Do not treat past referrals, a name alone, or an unverified lookup as identity or authority verification.

2. **Check referrer eligibility from authoritative sources.** Determine whether the referrer has current eligible checking status and the opening date of the earliest Rho-Bank checking account. Tenure is based on that earliest checking opening, not the current product or the product being referred. Never infer current checking status or earliest opening date from referral records, credit-card records, or the absence of a record.

3. **Retrieve referral history before discussing capacity.** After verification, call `get_referrals_by_user` using the verified user ID. Count `COMPLETE` referrals only, unless an authoritative program source says otherwise. Evaluate the following with `scripts/referral_assessor.py`:
   - across all checking programs, no more than two successful bonuses in the rolling nine-day period based on exact timestamps;
   - the intended product's calendar-year cap; and
   - the intended product's referrer-tenure requirement.

4. **Perform every available named-customer lookup before declaring customer history unavailable.** For each person or business named as a possible referee, call `get_user_information_by_name` with that exact supplied name after retrieving referral history. Do this for all named candidates, not only the currently preferred candidate. A no-record result is only an inconclusive screening attempt: it is not proof that the person or business is a new customer, has no closed account in the last 12 months, or is eligible. Keep the lookup result private.

5. **Confirm each prospective-referee condition.** Before recommending or initiating a referral, confirm from authoritative sources that the prospective referee:
   - has no existing checking or savings account and no account closed in the preceding 12 months;
   - is registered at a different address than the referrer;
   - meets the target product's age or formation requirements; and
   - for a business, has a primary authorized signer's SSN different from the primary owner of every existing Rho-Bank business account.

   Customer uncertainty and a no-record name lookup leave these conditions unknown. Do not expose another customer's account, address, SSN, or ownership information.

6. **Compare only fully confirmed options.** If no option is fully confirmed, say that you cannot approve or recommend a referral yet. You may identify the largest *conditional* stated bonus only if you clearly label it conditional and list the unresolved checks. Do not select between otherwise equal candidates based on invented facts. During 2025-11-01 through 2025-11-30, if multiple business accounts meet every stated requirement, prioritize Sky Blue, then Lime Green; promotional priority never overrides eligibility.

7. **Handle unavailable sources safely.** State each specific blocker, such as missing authoritative checking status/earliest opening date, former-account history, address comparison, or business-owner screening. Do not create a referral, manufacture a referral link, make an unconditional recommendation, or assert eligibility. Do not transfer merely because a source is unavailable; offer or make a human transfer only when the customer asks for one or specialized review is needed.

## Supported referral terms

Apply these terms only after the referrer eligibility check. All checking referrals also require new money rather than an internal Rho-Bank transfer, retention of the qualifying deposit for at least 30 days after the qualifying period, both accounts in good standing, and no stacking with another new-account promotion or a second referral code. Closure of the referred account within 90 days may cause a clawback.

| Program | Referrer bonus | Referred bonus | Annual cap | Referrer tenure | Target and deposit condition |
|---|---:|---:|---:|---:|---|
| Gold Years | $50 | $75 | 6 | 30 days | Referred customer must be age 62+ and deposit $1,000 within 90 days. |
| Light Green | $15 | $25 | 3 | 14 days | Primary holder must be age 13–24; deposit $100 within 90 days. A minor requires the applicable guardian arrangement. |
| Sky Blue | $150 | $250 | 8 | 45 days | Referred startup must be within four years of formation and deposit $10,000 within 90 days. |
| Light Blue | $30 | $20 | 5 | 30 days | Deposit $500 within 60 days. |

Do not invent terms for unsupported products. A Gold Years personalized referral link is available in account settings only after eligibility is confirmed. For other products, use only a documented and available link process.

## Calculator

Run `scripts/referral_assessor.py` after collecting structured history and authoritative screening results. The script reads one JSON object from standard input and emits one JSON object on standard output. It performs no banking action.

Input fields:

- `as_of`: required ISO-8601 date or timestamp.
- `referrals`: required array of objects with `date`, `status`, and `account_type`.
- `programs`: required array with `account_type`, numeric `referrer_bonus`, integer `annual_cap`, and integer `min_referrer_tenure_days`.
- `referrer`: optional object containing `identity_verified`, `authority_confirmed`, `current_checking_confirmed`, and `earliest_checking_opened_at`. Use `true`, `false`, or `null`; `null` means unknown.
- `candidates`: optional array with `name`, `account_type`, and `requirements`. Each requirement has `key`, `label`, and `status` of `true`, `false`, or `null`.

Runnable invocation:

```sh
python3 scripts/referral_assessor.py < referral_input.json
```

Validate that `rolling_window.successful_complete_count`, included dates, and program annual counts match the retrieved history. A candidate is `ready_to_recommend` only when all referrer checks, caps, tenure, and listed candidate requirements are confirmed. `conditional_candidates` are not approved referrals. The calculator treats date-only records as midnight UTC; use authoritative timestamps where exact rolling-window timing is material.

## Communication

Separate confirmed facts, failed conditions, and unknown conditions. Explain that a third successful referral within a rolling nine-day window is automatically denied and cannot be reinstated during that window. If the cap is full, do not promise later eligibility because all other requirements still apply. Accurately describe statuses: `COMPLETE` met bonus criteria; `IN_PROGRESS` is working toward deposit; `NO_PROGRESS` has not applied; `APPLIED` awaits a decision; `REJECTED` was denied; and `ERROR` is a system error.
