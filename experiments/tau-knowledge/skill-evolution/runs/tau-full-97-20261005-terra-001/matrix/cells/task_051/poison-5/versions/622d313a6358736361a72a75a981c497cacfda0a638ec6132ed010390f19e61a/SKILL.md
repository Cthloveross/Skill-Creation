---
name: credit-limit-increase-workflow
description: Process a verified cardholder's credit-limit-increase request using tier-specific amount limits, mandatory post-submission CLI eligibility reviews, and the required approve/deny record. Use when a credit-card account, verified customer, and CLI tools are available.
---

# Credit Limit Increase Workflow

Use this workflow for a confirmed credit-limit increase (CLI) request. Follow its order exactly: validate the amount, **submit the valid request**, perform every review, record the decision, then communicate it.

## Prerequisites and tier policy

Use the normal customer-verification state and procedures available in the active case before making an account-changing action. Do not add an unsupported verification requirement or transfer the customer merely because the CLI request requires internal review. Confirm that the intended account belongs to the verified customer.

Determine the tier only from applicable card documentation. Do not infer it from a card name without a documented mapping.

| Tier | Minimum account age | Approved-request cooldown | Utilization | On-time payment history | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | strictly below 70% | 6 consecutive months | 25% of current limit |
| Mid-tier | 90 days | 90 days | strictly below 80% | 3 consecutive months | 50% of current limit |
| Premium-tier | 60 days | 60 days | strictly below 90% | 3 consecutive months | 50% of current limit |

A denied prior CLI does not create a cooldown. A utilization percentage equal to the threshold fails because the requirement is strictly below it.

## Required execution sequence

1. **Locate the account and validate the requested amount.** Obtain the account ID, user ID, current limit, balance, account-open date, standing, and past-due amount from reliable account data. Calculate the tier cap using `scripts/evaluate_cli.py` in `amount_check` mode.

   The customer must explicitly confirm a definite whole-dollar increase. If the initial amount exceeds the cap, explain the permitted maximum and ask whether they want to proceed with an amount at or below it. Do not submit an excessive request. Once the customer confirms a valid adjusted amount, continue immediately; do not restart discovery or transfer the request.

2. **Formally submit before any eligibility-review tools.** Unlock `submit_credit_limit_increase_request_7392`, then call it with exactly:
   - `credit_card_account_id`
   - `user_id`
   - `requested_increase_amount` as the confirmed integer dollar amount

   Submission creates the formal request. It must occur before the four external eligibility checks below.

3. **Complete every eligibility review after submission.** Unlock and call all four tools even when account data already reveals a likely denial. Use the verified identifiers and retain the results:
   - `get_credit_limit_increase_history_4829` with `{"credit_card_account_id": account_id}` to review the tier cooldown. Apply it only to the latest relevant **approved** request.
   - `get_user_dispute_history_7291` with `{"user_id": user_id}`. Open or under-review disputes are active; closed disputes are not active.
   - `get_pending_replacement_orders_5765` with `{"credit_card_account_id": account_id}`. Any order not clearly delivered or cancelled, including pending or shipped, is pending.
   - `get_payment_history_6183` with `{"credit_card_account_id": account_id, "months": required_months}`. Confirm every required consecutive month is on time.

   Also evaluate the account data for minimum age, current/good standing with no past-due balance, and utilization (`current_balance / credit_limit * 100`). Do not make an approval or denial decision until all four external calls and all account-data checks are complete.

4. **Evaluate and record the decision.** Supply the collected facts to the helper in `evaluate` mode, or apply the same policy directly if the helper cannot be run. The helper is read-only and does not replace banking-tool calls.
   - If all checks pass, unlock and call `approve_credit_limit_increase_5847` with account ID, user ID, and numeric `new_credit_limit`.
   - If any check fails, unlock and call `deny_credit_limit_increase_5848` with account ID, user ID, and the documented denial reason. Use `high_utilization` when the utilization check fails. Other supported reasons are `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `insufficient_payment_history`, `requested_amount_exceeds_limit`, and `other`.

5. **Communicate after the record action.** For approval, state the new total limit. For denial, state that the request was denied, give the applicable reason, and provide a practical next step. For high utilization, explain that utilization must be below the tier threshold and advise paying down the balance before reapplying. Give a reapplication date when it can be determined from the failed condition.

## Missing or ambiguous review data

After a valid request is submitted, do not skip required reviews due to an earlier failed condition. If a required tool response is malformed, unavailable, or ambiguous, do not assume it passes and do not approve. Use normal retry/escalation handling when the required evidence cannot be obtained. Do not invent a result or a denial reason unsupported by reviewed data.

## Evaluator interface

`scripts/evaluate_cli.py` reads one JSON object from stdin and writes one JSON object to stdout. It has no banking side effects. Run it with a valid JSON input through the supplied Skill-script runtime.

Amount validation input:

```json
{
  "mode": "amount_check",
  "tier": "entry-tier",
  "current_credit_limit": 4000,
  "requested_increase_amount": 1000
}
```

Full review input:

```json
{
  "mode": "evaluate",
  "tier": "entry-tier",
  "current_credit_limit": 4000,
  "requested_increase_amount": 1000,
  "account_open_date": "YYYY-MM-DD",
  "current_date": "YYYY-MM-DD or ISO timestamp",
  "current_balance": 0,
  "account_current": true,
  "past_due_amount": 0,
  "last_approved_request_date": null,
  "active_disputes": false,
  "pending_replacement": false,
  "consecutive_on_time_months": 6
}
```

The output includes the amount cap, proposed new limit, utilization, each required check, eligibility, and a supported `denial_reason`. Validate that all source fields came from the current account and post-submission tool reviews before using the result.
