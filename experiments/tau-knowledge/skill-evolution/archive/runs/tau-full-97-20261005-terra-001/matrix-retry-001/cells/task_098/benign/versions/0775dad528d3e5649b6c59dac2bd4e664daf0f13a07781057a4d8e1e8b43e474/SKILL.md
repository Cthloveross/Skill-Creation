---
name: checking-referral-eligibility-and-selection
description: Assess whether a checking customer may make a referral before discussing or recommending referral programs, then select the highest combined documented bonus that the prospective customer can qualify for. Use for checking-referral questions and attempted referral submissions.
---

# Checking referral eligibility and selection

## Core rule

Check the referrer's eligibility **before** providing referral recommendations, bonus comparisons, or submission guidance. Do not imply that a referral is approved, qualifying, or submitted unless the required eligibility facts are verified and an available banking tool actually completes that action.

A referral recommendation needs two separate determinations:

1. **Referrer eligibility**: earliest checking-account opening date satisfies the selected program's tenure threshold; no rolling-window denial; and the program's annual cap has remaining capacity.
2. **Prospective customer and account eligibility**: the prospective customer can open the selected account and meets all general and program-specific referral conditions.

The referrer's tenure is measured from the earliest Rho-Bank checking account, not from the current account type or referral history. Referral records do not prove that opening date.

## Required checks

### Referrer checks

Obtain or verify:

- The referrer's matching bank profile and their **earliest checking-account opening date**.
- All successful referral-bonus timestamps needed to calculate the cross-account rolling cap: no more than two successful bonuses in the prior rolling nine days. The policy uses exact timestamps; do not treat an `IN_PROGRESS` referral as a successful bonus.
- Successful referral count for the selected product in the current calendar year, compared with that product's annual cap.
- Whether the referrer's account is in good standing, when this is required for bonus retention.

If the earliest opening date is unknown, the referrer has not passed the mandatory tenure check. Ask for a verifiable date or use an authorized account-history source if one is available. Do not infer it from a past referral, current account type, or account-holder age.

### Prospective customer checks

Before selecting or submitting a referral, obtain confirmation and, where the runtime permits, verify that the prospective customer:

- Is a new customer with no current checking or savings account and no closed account in the preceding 12 months.
- Is not registered at the same address as the referrer.
- Meets the selected account's age requirements. For ordinary personal checking, the documented opening rule is age 18+; apply any documented product-specific exception or maximum age as well.
- Is verified, is within the personal-checking-account limit, and has no checking account closed for cause in the preceding six months.
- Will use new money for the qualifying deposit, rather than a transfer from another Rho-Bank account.
- Is not combining the referral with another new-account promotion and will use only one referral code.
- Can meet the account-specific deposit amount and deadline, and understands that the qualifying deposit must remain for at least 30 days after the qualifying period ends.

Also disclose that an account closed within 90 days can result in a bonus clawback and that both accounts must remain in good standing. For business referrals, separately check distinct primary ownership; do not apply personal-account assumptions.

A referrer's statement about another person's account history is not a confirmed account-history result. If that person has not confirmed the required history, leave the referral unsubmitted.

## Selection method

1. Build the product list only from the supplied, current referral-program documents. For every candidate retain: referrer bonus, referred-person bonus, qualifying deposit, deadline, tenure minimum, annual cap, and age/account restrictions.
2. Eliminate products whose qualifying deposit exceeds the prospective customer's stated amount or whose account eligibility is unmet or unknown.
3. Do not rank products at all until the referrer checks pass. This enforces the requirement to check referrer eligibility before giving referral recommendations.
4. For products that pass all checks, compute `combined_bonus = referrer_bonus + referred_bonus`, select the highest value, and disclose material qualification conditions. If tied, present all tied products rather than inventing a tiebreaker.
5. Never assume an approximate deposit will be sufficient. State the required amount and deadline and ask for confirmation that the person will actually deposit at least that amount.

Use `scripts/assess_referral.py` to make the repeated timing, cap, condition, and bonus calculations deterministic. Supply the program catalog at runtime; the script deliberately contains no product amounts, account IDs, or customer data.

## Current-task execution workflow

1. Identify the referrer using the supplied identity information and retrieve the referral history using the normal read-only banking tools.
2. Retrieve current time before evaluating the nine-day rolling window.
3. Check whether the available results establish the earliest checking opening date. If not, explain that the required referrer-tenure check remains unresolved and do not give a recommendation or submit a referral.
4. Check the prospective customer's confirmations and account-opening prerequisites. If any are unknown, ask only for the missing fact(s); do not convert a promise to confirm later into a passed check.
5. Run the helper with facts established from the conversation and authorized results. Interpret `decision: "blocked"` as a stop condition, `decision: "ineligible"` as a reason not to submit, and `decision: "eligible"` as permission to present only the returned best/tied programs.
6. If no referral-submission tool is available in the runtime, clearly state that no submission was made. Do not fabricate a referral, account opening, status, link, or tool call. A script result is advice only and never causes a bank action.

## Helper interface

Run with a JSON request on stdin:

```text
python scripts/assess_referral.py < request.json
```

Input object:

- `now` (required): ISO-8601 current timestamp with a time component.
- `expected_deposit` (number or `null`): amount the prospective customer will deposit.
- `referrer` (object):
  - `earliest_checking_opened` (ISO timestamp/date or `null`)
  - `account_in_good_standing` (`true`, `false`, or `null`)
  - `successful_bonus_events` (array, or `null` if history is incomplete). Each event has exact `timestamp` and optionally `status`; only `COMPLETE`/omitted-status events count for the rolling cap.
  - `annual_successful_bonus_counts` (object mapping account type to count, or `null` if unknown).
- `referred` (object): fields may be `true`, `false`, or `null`: `has_no_rho_accounts_or_closed_last_12_months`, `same_registered_address`, `verified`, `closed_for_cause_last_6_months`, `deposit_is_new_money`, `will_keep_qualifying_deposit_30_days_after_window`, `using_other_new_account_promotion`, `account_in_good_standing`, and `guardian_available`. Include `age` and `existing_personal_checking_count` as number or `null`.
- `programs` (required nonempty array): each program has `account_type`, `referrer_bonus`, `referred_bonus`, `min_deposit`, `deposit_window_days`, `referrer_tenure_days`, and `annual_cap`. Optional fields are `recipient_min_age` (defaults to 18), `recipient_max_age`, and `guardian_required_if_under_18`.

Output is one JSON object with `decision` (`blocked`, `ineligible`, or `eligible`), `referrer_issues`, `referred_issues`, rolling-window details when determinable, and either `best_programs` or eligible-program results. `blocked` identifies missing evidence; `ineligible` identifies confirmed disqualifiers.

## Validation

Before relying on the result, confirm that all currency fields are nonnegative numbers, each tenure/deposit/cap is nonnegative, account types are nonempty and unique, timestamps parse, and the input catalog came from the current supplied documents. The helper validates these structural requirements and returns `decision: "blocked"` with `input_errors` instead of guessing. Review all returned issues in the customer response; do not quote a calculated bonus without its qualifying conditions.
