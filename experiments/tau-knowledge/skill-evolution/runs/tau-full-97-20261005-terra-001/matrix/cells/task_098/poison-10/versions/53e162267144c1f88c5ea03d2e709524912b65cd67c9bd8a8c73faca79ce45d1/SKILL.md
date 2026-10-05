---
name: checking-referral-recommendation
description: Assess whether a checking customer may submit a referral, then compare current checking referral programs to identify the highest combined bonus that is actually eligible or clearly conditional. Use for referral-bonus questions, referral eligibility, qualifying-deposit comparisons, and rolling-window/annual-cap checks. Do not use to create a referral, open an account, or make another banking change.
---

# Checking Referral Recommendation

Use this skill to give an evidence-based referral recommendation. A referral recommendation is not just a bonus comparison: **verify the referrer is eligible to submit referrals before giving referral terms or recommending an account.** Do not treat an unverified assertion as a confirmed eligibility fact.

## Required inputs

Obtain or request these facts before presenting a recommendation:

- Referrer identity and authority to discuss the profile. For account-specific records, obtain the customer record through the normal identity-verification workflow.
- Date/time the referrer's *earliest Rho-Bank checking account* was opened. Current account type and newly opened accounts do not reset tenure.
- Referral records, including status and the most precise available completion/bonus timestamps.
- Current time and time zone.
- Whether the prospective referred person is a brand-new Rho-Bank customer with no open account and no account closed in the prior 12 months.
- Whether the two people have different registered addresses.
- The prospective customer's age or date of birth and, for a minor program, guardian eligibility/arrangement where required.
- Expected qualifying-deposit amount, source, and timing.
- The current authoritative referral terms for every account under consideration, represented in the catalog schema below.

If an input is unknown, say precisely what must be confirmed. Do not infer adulthood, customer-newness, address difference, a qualifying deposit source, or a referral timestamp from silence.

## Workflow

1. **Identify and verify the referrer as needed for record access.** Use the normal banking tools to locate the profile and referral records. If identity verification is required before accessing or discussing account-specific data, verify two identity fields and log that verification before proceeding.
2. **Check referrer eligibility first.** For each possible program, evaluate tenure from the earliest checking-open date, its annual cap, and the shared rolling 9-day limit. Only `COMPLETE` referrals represent successful bonuses for the rolling bonus count. Do not count `IN_PROGRESS`, `APPLIED`, `NO_PROGRESS`, `REJECTED`, or `ERROR` as received bonuses.
3. **Apply the shared referral restrictions.** The prospective customer must be new, at a different registered address, and normally at least 18. A minor can only be considered where the selected product expressly permits it and the applicable guardian requirement is satisfied. For business referrals, also verify a different primary owner by the primary authorized signer's SSN.
4. **Compare only viable products.** For each program, test the customer-age rules, referrer tenure, annual cap, rolling cap, required deposit amount, deposit deadline, and known deposit plan. Rank confirmed eligible options by `referrer_bonus + referred_bonus`. A product whose age, tenure, customer-newness, address, cap, or timing cannot be confirmed is conditional, not eligible.
5. **Explain qualifying and retention conditions.** A qualifying deposit must be new money, not a transfer from another Rho-Bank account, made within the product's stated window, and retained for at least 30 days after the qualifying period ends. Referral bonuses cannot be combined with another new-account promotion or sign-up bonus; only one referral code may be applied per new account. A bonus may be clawed back if the referred account closes within 90 days, and both accounts must remain in good standing.
6. **Give a compact outcome.** State (a) the best confirmed option and combined amount, or that no option is yet confirmed; (b) the exact open condition(s); (c) deposit amount/deadline and new-money requirement; and (d) any applicable cap/waiting outcome. Never claim that a referral is approved or a bonus will be paid before the account and deposit qualify.

### Rolling-window interpretation

The cap is a maximum of two referral bonuses across all checking account types in a rolling nine-day interval, measured from successful-referral timestamps rather than calendar weeks. A third referral in that window is automatically denied and cannot be reinstated within that window. If timestamps are too imprecise to establish whether a prior completion falls in the window, classify the cap as `unknown`; do not assume it is available. The executor may give a conservative earliest retry time only when the oldest included completion timestamp is known.

### Annual caps

Apply an account program's annual referral limit to completed bonuses for that program in the relevant calendar year. If the exact referral program or completion date is missing, mark the annual-cap outcome as unknown and obtain the record rather than guessing.

## Program catalog schema

Build `programs` from the current authoritative account referral terms at runtime. Do not reuse stale bonus amounts or substitute a similarly named account. Each object supplied to the helper must contain:

```json
{
  "account_type": "Official Account Name",
  "referrer_bonus": 0,
  "referred_bonus": 0,
  "annual_cap": 0,
  "qualifying_deposit": 0,
  "deposit_window_days": 0,
  "referrer_tenure_days": 0,
  "candidate_age_min": 18,
  "candidate_age_max": null,
  "guardian_required_under_18": false
}
```

Amounts are numeric dollars. Use `null` only where the product truly has no stated maximum age. Preserve product-specific eligibility requirements in the executor's explanation even if they are not modeled in the helper.

## Helper

`scripts/evaluate_referrals.py` consumes JSON from stdin and emits JSON to stdout. It performs deterministic candidate evaluation and sorting; it does not access bank systems or initiate a referral.

Input schema:

```json
{
  "now": "ISO-8601 timestamp with timezone",
  "programs": ["program catalog objects"],
  "referrer": {
    "first_checking_opened_at": "ISO-8601 timestamp with timezone or null"
  },
  "candidate": {
    "is_new_customer": true,
    "different_registered_address": true,
    "age": 21,
    "guardian_confirmed": false,
    "planned_deposit_amount": 600,
    "planned_deposit_is_new_money": true,
    "planned_deposit_within_window": true
  },
  "referrals": [
    {
      "referral_status": "COMPLETE",
      "referred_account_type": "Official Account Name",
      "completed_at": "ISO-8601 timestamp with timezone"
    }
  ]
}
```

Use `null` for unknown facts. Date-only referral records are intentionally considered insufficient for a boundary rolling-window decision. The output contains `confirmed_ranked_options`, `conditional_options`, `ineligible_options`, shared `rolling_window`, and machine-readable reason codes. An empty confirmed list means the executor must not name a definitive winning product.

Example runnable call:

```sh
python3 scripts/evaluate_referrals.py <<'JSON'
{"now":"2025-01-15T12:00:00-05:00","programs":[],"referrer":{"first_checking_opened_at":null},"candidate":{"is_new_customer":null,"different_registered_address":null,"age":null,"guardian_confirmed":null,"planned_deposit_amount":null,"planned_deposit_is_new_money":null,"planned_deposit_within_window":null},"referrals":[]}
JSON
```

## Output validation

Before using the result, verify that every catalog program has a nonempty official account name, nonnegative numeric amounts/caps/windows, and a positive tenure requirement. Verify `now` and all non-null account/referral timestamps are timezone-aware ISO-8601 values. Reject malformed input instead of silently making it eligible. Confirm that the recommended option appears in `confirmed_ranked_options`, has no reason codes, and has a combined bonus equal to the sum of the two component bonuses.

## Boundaries and escalation

- This skill is informational. Do not create a referral, open an account, apply a promotion, alter a profile, or disclose another person's account information.
- If the customer asks to complete an account opening or another banking action, follow the applicable action procedure and complete all prerequisites first.
- If records conflict, the current product terms are unavailable, an eligibility result cannot be reconciled, or a system error prevents the required lookup, explain the limitation and use normal support escalation rather than inventing a result.
- A `REJECTED` referral due to the rolling limit requires waiting until the relevant successful bonus is more than nine days old; it cannot be reinstated in the same window.

## Banking-action control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.
