---
name: credit-limit-increase-processing
description: Process a credit-card credit limit increase (CLI) request when the customer, card account, and requested increase must be verified, submitted, eligibility-checked, and either approved or denied with the prescribed banking tools.
---

# Credit Limit Increase Processing

Use this Skill for a customer request to increase a credit-card limit. It implements the required ordering: validate amount first, submit a valid request, perform **every** required check, then approve or deny. Do not treat a customer assertion as a substitute for a required internal check.

## Required data and assumptions

Obtain at runtime:

- verified `user_id` and the selected `credit_card_account_id`;
- card tier (`Entry-tier`, `Mid-tier`, or `Premium-tier`), current limit, current balance, opening date, account status, and past-due amount;
- current timestamp;
- a definite dollar increase amount; and
- results from the required CLI, payment-history, dispute, and replacement-order tools.

A product/card name is not by itself a CLI tier unless an authoritative account record or policy explicitly maps it to a tier. Do **not** infer a tier from product branding (for example, a metal/color/rewards name). Ask for or obtain the authoritative tier classification before determining limits or submitting a request. If it cannot be obtained, explain that the request cannot yet be processed and use the applicable support/escalation path rather than guessing.

The customer must be authenticated under the normal identity-verification process before disclosing account details or making an account change. Confirm two of the four identity fields (date of birth, email, phone number, address) against the user record, obtain the current time, and call `log_verification` with all required record fields and that timestamp. A name alone is not two-factor identity verification.

## Tier rules

| Tier | Minimum age | Cooldown after an **approved** request | Utilization must be below | Consecutive on-time months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | 70% | 6 | 25% of current limit |
| Mid-tier | 90 days | 90 days | 80% | 3 | 50% of current limit |
| Premium-tier | 60 days | 60 days | 90% | 3 | 50% of current limit |

Age and cooldown pass at `days_elapsed >= required_days`. Utilization is `current_balance / current_credit_limit * 100` and passes only when strictly less than the threshold; equality fails. The cooldown is triggered only by the most recent **approved** CLI request and is counted from its submission date. Denied requests do not trigger it.

Run `scripts/evaluate_cli.py` for deterministic calculations and a checklist after collecting normalized runtime facts. It recommends no banking action; the executor remains responsible for all tool calls and the final decision.

## Procedure

1. **Clarify and authenticate.** Identify the customer and intended account. If the request is expressed as a percentage, calculate the exact dollar increase from the current limit, explain it, and obtain confirmation of that definite amount. The submission tool accepts an integer dollar amount, so request a whole-dollar amount if the calculation is not a whole dollar. Complete identity verification and log it before account-specific disclosure/action.

2. **Determine the authoritative tier and load account facts.** Retrieve the user and account records. Select only the account the authenticated customer requested. Obtain the current time and use the account opening date, balance, limit, status, and past-due amount. Do not use a general product limit range as a CLI-tier mapping or as the amount limit.

3. **Validate the requested amount before submission.** Compute the tier maximum from the *current* limit. A requested increase must be positive and no greater than that maximum. If it exceeds the maximum, do not submit. Tell the customer the maximum dollar increase and ask whether they want to proceed at that amount. If they revise/confirm a compliant amount, restart this validation with the new amount.

4. **Submit the compliant request first.** Unlock and call `submit_credit_limit_increase_request_7392` with:
   - `credit_card_account_id`
   - `user_id`
   - `requested_increase_amount` (integer dollars)

   This creates the formal record before eligibility checks. Preserve the submitted amount and do not silently substitute another amount.

5. **Perform and record every required eligibility check after submission.** Unlock and use these tools as needed:
   - `get_credit_limit_increase_history_4829` with `credit_card_account_id`. Inspect approved requests and their submission dates for cooldown.
   - `get_user_dispute_history_7291` with `user_id`. Treat an open/active/under-review dispute as pending; closed disputes alone do not block the request.
   - `get_pending_replacement_orders_5765` with `credit_card_account_id`. Treat any order not clearly `delivered` or `cancelled` as pending.
   - `get_payment_history_6183` with `credit_card_account_id` and the tier-required month count. Confirm every required consecutive month is on time.

   Also check all of the following from current account facts: minimum account age, good standing/current status with no past-due balance, and strict utilization threshold. Do not skip the payment-history check merely because the customer says they always pay on time; do not skip dispute/replacement checks based on a customer statement. If an internal tool fails or returns ambiguous/incomplete data, do not approve on that basis; retry or escalate according to normal support procedure.

6. **Decide and apply exactly one outcome.** If the amount is compliant and all checks pass, unlock and call `approve_credit_limit_increase_5847` with `credit_card_account_id`, `user_id`, and `new_credit_limit = current_credit_limit + submitted_increase` as a float.

   If any post-submission requirement fails, unlock and call `deny_credit_limit_increase_5848` with the account ID, user ID, and the applicable allowed reason:
   - account age: `insufficient_account_age`
   - approved-request cooldown: `cooldown_period_active`
   - active dispute: `pending_disputes`
   - replacement order pending: `pending_replacement_card`
   - past due/not current: `past_due_balance`
   - utilization at or over the tier threshold: `high_utilization`
   - insufficient consecutive on-time payments: `insufficient_payment_history`
   - invalid amount caught before submission: `requested_amount_exceeds_limit` (normally no request is submitted, per Step 3)
   - a documented condition with no more specific code: `other`

   When more than one check fails, still complete all checks for the audit record, then use the most specific applicable denial reason and communicate all material blockers where appropriate.

7. **Communicate the result.** For approval, state that the request was approved and give the new total limit. For a denial, give the customer-safe reason and the next actionable step (for example, the date after cooldown, lower utilization, wait for replacement delivery/cancellation, or establish the required payment history). Do not expose internal-only details unnecessarily.

## Calculator input and output

`evaluate_cli.py` receives one JSON object on stdin and emits one JSON object on stdout. It accepts:

```json
{
  "tier": "Entry-tier",
  "current_limit": 4000,
  "current_balance": 1500,
  "account_open_date": "2023-05-10",
  "as_of": "2025-11-14T03:40:00-05:00",
  "requested_increase_amount": 400,
  "last_approved_request_date": "2025-09-14",
  "account_current": true,
  "past_due_amount": 0,
  "has_active_dispute": false,
  "has_pending_replacement": false,
  "consecutive_on_time_months": 6
}
```

Dates may be ISO date strings or ISO timestamps. `last_approved_request_date` may be `null` when there has never been an approved CLI. The output contains computed limits, utilization, check results, blockers, and either `approve` or `deny`; it intentionally cannot submit, approve, or deny a request. Validate that its `tier`, amounts, and normalized tool-derived facts match the live records before relying on it.
