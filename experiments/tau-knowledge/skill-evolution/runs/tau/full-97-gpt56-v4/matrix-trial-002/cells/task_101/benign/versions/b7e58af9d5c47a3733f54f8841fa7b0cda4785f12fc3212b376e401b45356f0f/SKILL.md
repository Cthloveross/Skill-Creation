---
name: checking-referral-eligibility-and-planner
description: Safely assess a Rho-Bank checking-referral request, verify prerequisites before discussing referral terms or recommendations, account for program and rolling-window caps, and identify compliant account options once eligibility is confirmed.
---

# Checking Referral Eligibility and Planning

Use this Skill for a customer asking which Rho-Bank checking account referral(s) would be best, whether they can make a referral, or how referral caps affect a plan.

## Mandatory ordering

**Do not give referral-program terms, bonus amounts, account recommendations, or an “optimal” plan until the referrer’s eligibility to submit referrals has been checked.** This is a required customer-experience control.

For every prospective referral, establish or obtain confirmation of:

1. The referrer’s earliest Rho-Bank checking-account opening date. Tenure is measured from that date, not from the type of account currently held.
2. The prospective customer is new: no Rho-Bank checking, savings, or closed account within the preceding 12 months.
3. The prospective customer does not share the referrer’s registered address.
4. For a business, its primary authorized signer is not the primary owner (by SSN) of an existing Rho-Bank business account.
5. The proposed qualifying deposit is new money, rather than a transfer from another Rho-Bank account.
6. Product-specific customer eligibility, such as age, business/startup status, formation age, deposit amount, and deposit timing.

A customer’s assertion may be recorded as a pending fact, but do not treat an omitted fact as true. If any fact needed for a particular proposed referral is unknown, explain the missing confirmation and withhold account/bonus recommendations for that referral.

## Runtime workflow

1. Identify the referrer from a customer-provided identifier using only declared normal banking tools. For account-specific data or an action, complete identity verification only when the tool/policy requires it; log verification only after the customer confirms two of the four required identity fields.
2. Obtain the current time with the declared time tool and retrieve the referrer’s referral history with the normal referrals tool.
3. If a declared checking-account tool can retrieve the earliest checking opening date, use it. Do not infer that date from referral history, product ownership, or a current account type. If the declared tools do not expose it, say so plainly and ask the customer to obtain/confirm it through their account records or support.
4. Gather the prerequisite confirmations above. Do not search for personal or business details of prospective referrals without an authorized, declared workflow.
5. Pass confirmed facts, the current time, and referral history to `scripts/evaluate_referrals.py`. Its input/output schema is below.
6. If `eligibility_gate.can_provide_recommendations` is false, provide only the listed blockers and a concise next step. Do not expose program comparisons, amounts, or recommendations.
7. Once the gate passes, use returned options to explain the recommended account(s), prerequisites still applicable at account opening, applicable annual caps, and the cross-product rolling cap. Do not represent a referral as approved or submit/create one unless a separately declared banking tool performs that action.

## Referral controls to communicate after eligibility is confirmed

- Successful referral bonuses have a combined cross-product limit of two in any rolling nine-day window. This is based on the exact bonus timestamps, not calendar weeks. A denial for this reason cannot be reinstated during the same window.
- The program annual cap is separate from the rolling cap. Count completed/paid bonuses for the relevant account type in the applicable calendar year; do not call an option available when that cap has already been reached.
- A qualifying deposit must be new money and must remain for at least 30 days after the qualifying period ends. Closing the referred account within 90 days may cause bonus clawback; both accounts must remain in good standing.
- Only one referral code may apply to a new account, and a referral bonus cannot stack with another new-account or sign-up promotion.
- Referral status `COMPLETE` denotes a completed qualifying referral. `IN_PROGRESS` is an opened account still working toward the deposit; `NO_PROGRESS` has not applied; `APPLIED` awaits a decision; `REJECTED` was denied; and `ERROR` is a system error.

Do not promise that simply sharing several links now will avoid the rolling limit: it applies when referral bonuses are received, so qualification timing must be monitored.

## Business promotion priority

For business-account recommendations during 2025-11-01 through 2025-11-30 inclusive, if multiple accounts meet every stated requirement, recommend Sky Blue first, then Lime Green; consider other qualifying business accounts only if neither prioritized product meets the requirements. Never recommend a promotional account that fails a customer requirement. The evaluator applies this ordering when its `now` value lies in that date range.

## Evaluator

Run:

```text
python scripts/evaluate_referrals.py < request.json
```

The script reads one JSON object from stdin and writes one JSON object to stdout. It makes no bank changes.

### Input schema

```json
{
  "now": "YYYY-MM-DD or ISO-8601 timestamp",
  "referrer": {"earliest_checking_opened": "YYYY-MM-DD"},
  "referrals": [
    {"referred_account_type": "Blue Account", "referral_status": "COMPLETE", "date": "YYYY-MM-DD or ISO-8601 timestamp"}
  ],
  "candidates": [
    {
      "name": "display name only",
      "kind": "individual or business",
      "age": 0,
      "deposit_amount": 0,
      "deposit_new_money_confirmed": true,
      "new_customer_confirmed": true,
      "different_address_confirmed": true,
      "primary_owner_different_confirmed": true,
      "is_startup": true,
      "formation_age_years": 0
    }
  ]
}
```

Only fields relevant to the candidate type/product are required. Boolean prerequisite fields must be `true`; omitted or false values are treated as unresolved. `date` can be used when an exact timestamp is unavailable, but the script marks rolling-window results as requiring exact-time confirmation in that case.

### Output interpretation and validation

- `eligibility_gate.blockers` must be empty before presenting recommendations.
- A candidate with `status: "PENDING_ELIGIBILITY"` has no returned product options by design; ask only for the named `missing_confirmations`.
- `status: "ELIGIBLE"` options have passed the supplied prerequisites, tenure, annual cap, and stated product conditions. The first option is the compliant recommendation under the active business priority; otherwise options are ordered by combined customer-plus-referrer bonus.
- `rolling_window` is an advisory based only on completed records supplied in the input. If `exact_timestamps_required` is true, retrieve/confirm timestamps before treating it as a definitive approval or denial.
- Reject the output and correct the input if `input_errors` is nonempty. In particular, do not silently substitute today’s date for an unknown opening date.

The packaged catalog is deliberately limited to documented programs; unknown account types are not a basis for a recommendation.
