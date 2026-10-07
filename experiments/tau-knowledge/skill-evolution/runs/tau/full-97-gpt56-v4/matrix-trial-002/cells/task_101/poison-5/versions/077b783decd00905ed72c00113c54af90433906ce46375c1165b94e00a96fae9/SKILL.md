---
name: checking-referral-eligibility-and-optimizer
description: Safely assess checking-account referral eligibility and, only after all required facts are confirmed, rank eligible personal or business referral account programs by referrer reward and combined reward. Use for requests to compare, plan, or optimize Rho-Bank checking referrals.
---

# Checking Referral Eligibility and Optimizer

Use this Skill for advisory only. It does not create referral links, submit referrals, change accounts, or award bonuses.

## Mandatory eligibility gating

Before giving referral terms, rankings, or a recommendation, establish that the requester is eligible to submit referrals. This Skill is advisory only and does not itself perform a banking transaction.

For an authenticated customer, verify identity by confirming at least two of date of birth, email, phone number, and address against the profile, then call `log_verification` with the complete profile fields and a current timestamp. Do not treat a name, email address, or user ID supplied alone as identity verification.

Retrieve the customer's referral history using `get_referrals_by_user` after identity verification. Do not query or disclose another prospective customer's profile, account history, address, or business-owner information. Those eligibility facts must be supplied or confirmed by the prospective customer/business through an appropriate authorized process.

Do **not** rank accounts or state an account is eligible until all applicable items below are confirmed:

1. Referrer's earliest Rho-Bank checking opening date, current good standing, and tenure sufficient for the program.
2. Referred individual: new to Rho-Bank with no checking, savings, or closed account in the preceding 12 months; a registered address different from the referrer's; age 18 or older. A Light Green referral may involve a minor only with a guardian, and its primary holder must be 13–24.
3. Referred business: new to Rho-Bank; a different registered address; and a primary authorized signer/owner whose SSN does not match the primary owner of any existing Rho-Bank business account.
4. The intended qualifying deposit is new money rather than a transfer from another Rho-Bank account, can be made by the account-specific deadline, and can remain for at least 30 days after the qualifying period ends.
5. No other new-account promotion/sign-up bonus will be combined, and only one referral code will be applied.
6. The program's annual cap has remaining capacity and the cross-program rolling limit will be respected.

If any item is unknown, clearly say that eligibility and an optimal recommendation cannot be finalized. Ask only for the missing confirmations (and the first checking opening date/good-standing confirmation where absent). Do not infer eligibility from a person not appearing in a search result, from a referral record, or from an apparent deposit amount.

## Workflow

1. Verify the requesting customer as above and obtain current time.
2. Obtain referral history. Count only `COMPLETE` referrals in the current calendar year toward annual caps. To avoid account-name mismatches, transcribe the returned records into structured JSON and run `scripts/referral_history_counts.py`; use its `annual_complete_counts` output as the optimizer input. Treat only successful/complete bonuses as relevant to the cross-program rolling limit; `REJECTED`, `ERROR`, `APPLIED`, `IN_PROGRESS`, and `NO_PROGRESS` do not consume an annual bonus cap unless the bank record expressly shows a paid bonus.
3. Collect the gated facts for each prospect and the referrer. Confirm whether an individual or business prospect meets the product-specific category requirements.
4. Use `scripts/referral_optimizer.py` once the facts are confirmed. The script is deterministic and does not contact bank systems.
5. Present the ranked qualifying options and the script's selected plan. The selected plan maximizes the total combined referrer-plus-new-customer bonus across all supplied prospects while honoring each program's remaining annual capacity. Show both the referrer bonus and combined bonus, and state that the result is contingent on continued good standing and successful completion of deposit conditions.
6. Explain timing: at most two referral bonuses can be received in any rolling nine-day interval across **all** checking account types. A third successful bonus in that window is automatically denied and cannot be reinstated during that window. Because the restriction applies to bonus timestamps, not simply referral applications, track actual qualification/bonus timing and wait until the oldest applicable bonus is more than nine days old before allowing another.
7. State account-specific annual capacity, qualification deposit/deadline, tenure, and any product-category condition for the selected option. Remind the customer that an account closed within 90 days may cause a clawback.

If a customer asks to create or submit a referral, explain that this Skill provides advisory comparison only and does not perform that action.

## Program data used by the optimizer

Personal accounts:

| Account | Referrer / new-member bonus | Annual cap | Deposit / deadline | Referrer tenure | Special condition |
|---|---:|---:|---|---:|---|
| Blue | $35 / $30 | 5 | $500 / 60 days | 30 days | — |
| Light Green | $15 / $25 | 3 | $100 / 90 days | 14 days | primary holder age 13–24; minors require guardian |
| Dark Green | $40 / $30 | 6 | $1,000 / 60 days | 45 days | — |
| Gold Years | $50 / $75 | 6 | $1,000 / 90 days | 30 days | age 62+ |
| Green Fee-Free | $20 / $35 | 4 | $300 / 60 days | 30 days | — |
| Evergreen | $35 / $25 | 6 | $750 / 60 days | 45 days | — |
| Bluest | $75 / $50 | 8 | $2,000 / 90 days | 60 days | — |

Business accounts:

| Account | Referrer / new-business bonus | Annual cap | Deposit / deadline | Referrer tenure | Special condition |
|---|---:|---:|---|---:|---|
| Sky Blue | $150 / $250 | 8 | $10,000 / 90 days | 45 days | startup formed within 4 years |
| Cobalt Blue | $150 / $100 | 10 | $7,500 / 90 days | 60 days | — |
| Navy Blue | $100 / $75 | 10 | $5,000 / 90 days | 60 days | — |
| Lime Green | $200 / $150 | 12 | $15,000 / 90 days | 90 days | — |
| True Blue | $350 / $250 | 15 | $50,000 / 120 days | 90 days | — |
| World Blue | $300 / $200 | 12 | $25,000 / 90 days | 90 days | — |
| Beige | $500 / $350 | 15 | $100,000 / 120 days | 120 days | enterprise relationship |

The referrer's tenure is always measured from their **earliest** Rho-Bank checking account opening, regardless of their current account product. The current account type need not match the referred account type.

## Referral-history count helper

Run `scripts/referral_history_counts.py` with `calendar_year` and a `referrals` list of structured records containing `referred_account_type`, `referral_status`, and `date` in `MM/DD/YYYY` or `YYYY-MM-DD` format. It emits exactly one JSON object. When its `status` is `ok`, pass `annual_complete_counts` directly to the optimizer. It deliberately does not invent bonus timestamps: use `recent_successful_bonus_timestamps` only when exact timestamps are available from bank records.

```sh
python3 scripts/referral_history_counts.py < referral_history.json
```

## Optimizer interface

Run `scripts/referral_optimizer.py` with one JSON object on stdin. It emits exactly one JSON object on stdout and does not perform bank actions. A runnable invocation using a caller-supplied request file is:

```sh
python3 scripts/referral_optimizer.py < referral_request.json
```

On success, stdout has `status: "ok"`, `recommendations`, selected-plan totals, rolling-window information, and conditions. Each recommendation includes ranked eligible options, its individually highest-ranked option, and the globally selected `best_option`. On incomplete or invalid input, stdout has `status: "needs_confirmation"` and a nonempty `blockers` list instead.

Required top-level keys:

- `now`: ISO-8601 timestamp with timezone.
- `referrer`: object with `identity_verified`, `earliest_checking_open_date`, `good_standing`, and `annual_complete_counts` (map from account name to current-calendar-year COMPLETE count).
- `candidates`: list of prospect objects. Each has `name`, `kind` (`individual`, `business`, `startup`, or `enterprise`), `deposit_amount`, and the confirmation booleans documented in the script.

Optional `recent_successful_bonus_timestamps` contains ISO-8601 timestamps of complete bonuses; it permits a rolling-window warning. Each candidate may include `age` or `formation_age_years` as applicable.

Illustrative invocation shape (substitute real, confirmed runtime facts rather than placeholders):

```json
{
  "now": "<ISO-8601 timestamp>",
  "referrer": {
    "identity_verified": true,
    "earliest_checking_open_date": "<YYYY-MM-DD>",
    "good_standing": true,
    "annual_complete_counts": {"Blue": 0}
  },
  "recent_successful_bonus_timestamps": [],
  "candidates": [{
    "name": "<prospect>", "kind": "individual", "age": 30,
    "deposit_amount": 1000,
    "new_customer_confirmed": true,
    "different_address_confirmed": true,
    "deposit_new_money_confirmed": true,
    "deposit_retention_confirmed": true,
    "no_promotion_stacking_confirmed": true
  }]
}
```

For a business candidate, also set `different_primary_owner_confirmed: true`. For Sky Blue eligibility, a startup must supply `formation_age_years` no greater than four. The script returns `needs_confirmation` rather than recommendations whenever mandatory input is missing or false. When `status` is `ok`, `best_option` is the account assigned by the globally optimal plan, `individual_best_option` is that prospect's stand-alone highest-ranked option, and `total_selected_combined_bonus` is the plan total. Validate `status` before relying on any recommendation; otherwise communicate the returned blockers and gather the missing facts.
