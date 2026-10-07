---
name: credit-limit-increase-workflow
description: Process a verified cardholder's credit-limit-increase request when the card tier, current limit, account data, and CLI tools are available. Use for tier-specific amount validation, mandatory post-submission eligibility checks, and an approval or denial decision.
---

# Credit Limit Increase Workflow

## Scope and prerequisites

Use this Skill only after identifying the intended card account and its tier. Determine the tier from the applicable card documentation; do not infer a tier from a card name unless documentation explicitly maps that card name to a tier.

Before any account-changing CLI action, authenticate the caller. Obtain and match **two of these four** fields against the customer record: date of birth, email, phone number, or address. A name is useful for lookup but is not one of the two verification fields. After two fields match:

1. Get the current timestamp with `get_current_time`.
2. Call `log_verification` with the account holder's complete record fields and that timestamp.

If two factors cannot be verified, do not submit, approve, or deny a CLI request. Ask for another permitted factor or follow the normal identity-verification handling process.

## Tier policy

| Tier | Minimum age | Cooldown after approved CLI request | Utilization requirement | Consecutive on-time payment months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | strictly below 70% | 6 | 25% of current limit |
| Mid-tier | 90 days | 90 days | strictly below 80% | 3 | 50% of current limit |
| Premium-tier | 60 days | 60 days | strictly below 90% | 3 | 50% of current limit |

A customer must state a definite dollar increase. Calculate the cap from the current limit and obtain explicit confirmation if the customer changes the requested amount. Do not submit a request whose amount exceeds the applicable cap. Explain the maximum and offer to proceed at or below it instead. If the customer does not provide a valid confirmed amount, stop without submitting or denying.

The included evaluator calculates caps, elapsed calendar days, utilization comparisons, and a deterministic proposed denial reason. It does not call banking tools or replace review of tool responses.

## Execution procedure

1. **Identify and verify.** Locate the user and intended credit-card account using the normal read-only tools. Confirm that the account belongs to the verified user. Record identity verification as described above.
2. **Precheck the amount only.** Retrieve the current account limit, determine the documented tier, and run `scripts/evaluate_cli.py` in `amount_check` mode. If `submission_permitted` is false, tell the customer the calculated `max_increase_amount`, obtain a new explicit amount, and rerun this step. Never use `submit_credit_limit_increase_request_7392` for an excessive request.
3. **Submit the valid request before eligibility review.** Unlock `submit_credit_limit_increase_request_7392`, then call it with `credit_card_account_id`, `user_id`, and the confirmed integer dollar `requested_increase_amount`. Retain the result as the formal request record. Do not perform approval/denial eligibility checks before this submission.
4. **Perform every required check after submission.** Refresh/read the account information needed for account age, current balance, limit, and past-due/current status. Unlock and call all of the following, even if an earlier check fails:
   - `get_credit_limit_increase_history_4829` with `credit_card_account_id`. Apply the tier cooldown only when the most recent relevant request was **approved**. Denied requests do not trigger the cooldown. The cooldown has elapsed only on or after the required full number of days from the approved request's submission date.
   - `get_user_dispute_history_7291` with `user_id`. Treat an open or under-review dispute as active; closed disputes are not active.
   - `get_pending_replacement_orders_5765` with `credit_card_account_id`. Treat any order not clearly delivered or cancelled (including pending or shipped) as pending.
   - `get_payment_history_6183` with `credit_card_account_id` and the tier's required number of `months`. Confirm that the required consecutive months are all on time.

   Also assess from the account data that the account age meets the tier minimum, it is current with no past-due balance, and current utilization (`current_balance / credit_limit * 100`) is strictly below the tier threshold. A balance exactly at the threshold fails utilization.
5. **Evaluate all collected facts.** Normalize the reviewed facts into the evaluator's `evaluate` schema. The result must show every check. Do not approve based on partial, stale, ambiguous, or failed checks.
6. **Record the decision.** If all checks pass, unlock and call `approve_credit_limit_increase_5847` with the account ID, user ID, and the calculated `new_credit_limit` as a numeric value. If any check fails, unlock and call `deny_credit_limit_increase_5848` with the account ID, user ID, and the evaluator's `denial_reason`. The permitted reasons are: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, `insufficient_payment_history`, `requested_amount_exceeds_limit`, and `other`.
7. **Communicate clearly.** For approval, confirm the new total limit. For denial, explain the applicable reason and, where determinable, the next eligible date or corrective next step. Do not disclose internal-only details unnecessarily.

## Incomplete or contradictory results

After submission, all eligibility criteria still need to be checked before a decision. If a required tool fails, returns insufficient data, or its status/date cannot be interpreted reliably, do not approve or make up a denial reason. Retry only when appropriate; if the required evidence remains unavailable, use the normal technical/escalation process and state that the review cannot be completed yet. Do not treat an empty, malformed, or ambiguous response as proof that a condition passes.

If account data does not establish the tier, current limit, account-open date, balance/limit, or standing, obtain reliable data before proceeding. A requested amount exceeding the cap is a pre-submission stop condition, not a reason to create a request merely to deny it.

## Evaluator interface

`scripts/evaluate_cli.py` reads one JSON object from standard input and emits one JSON object to standard output. It accepts normalized numeric amounts without currency symbols and dates in `YYYY-MM-DD`, ISO timestamp, or `MM/DD/YYYY` form.

### Amount precheck input

```json
{
  "mode": "amount_check",
  "tier": "entry-tier | mid-tier | premium-tier",
  "current_credit_limit": "decimal number",
  "requested_increase_amount": "integer dollars"
}
```

The response includes `submission_permitted`, `max_increase_amount`, `new_credit_limit`, and `amount_within_limit`.

### Full evaluation input

```json
{
  "mode": "evaluate",
  "tier": "entry-tier | mid-tier | premium-tier",
  "current_credit_limit": "decimal number",
  "requested_increase_amount": "integer dollars",
  "account_open_date": "date",
  "current_date": "date or timestamp",
  "current_balance": "decimal number",
  "account_current": true,
  "past_due_amount": "decimal number",
  "last_approved_request_date": "date or null",
  "active_disputes": false,
  "pending_replacement": false,
  "consecutive_on_time_months": "integer"
}
```

The `checks` object is the validation record: every value must be `true` before approval. `denial_reason` is `null` when eligible; otherwise it is a supported reason selected from failed checks. Use the actual tool-reviewed values, not assumptions. Run with a valid JSON file as `python3 scripts/evaluate_cli.py < request.json`.
