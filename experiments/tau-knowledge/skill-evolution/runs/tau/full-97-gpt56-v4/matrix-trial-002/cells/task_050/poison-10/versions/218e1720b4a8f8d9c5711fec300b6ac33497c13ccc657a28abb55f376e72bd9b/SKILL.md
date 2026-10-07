---
name: credit-limit-increase-workflow
description: Process a credit-card credit-limit increase (CLI) request through identity verification, tier-based amount validation, required submission and eligibility checks, recorded approval or denial, and customer communication. Use for an account holder requesting an increase to an existing credit-card limit.
---

# Credit-limit increase workflow

## Scope and prerequisites

Use the normal banking tools available in the task environment. The specialized CLI tools named below must first be unlocked with `unlock_discoverable_agent_tool`, then invoked through `call_discoverable_agent_tool`. Do not treat this Skill's calculations or recommendations as bank actions; the executor must make the applicable tool calls.

Before any account-specific action beyond locating a possible record, verify the requester. Obtain and match **two of four** identity fields (date of birth, email, phone number, address) against the customer record. Once two fields match, call `get_current_time` and then `log_verification` with the complete retrieved customer record and that timestamp. If two fields cannot be verified, do not submit or process the CLI.

Identify the account from the verified user's credit-card accounts. Confirm which account the customer means if there is more than one. Capture:

- `user_id` and `credit_card_account_id`
- current credit limit and current balance
- account-open date and any returned standing/past-due fields
- requested *increase* amount, in whole dollars, and the customer's reason

If the customer states a desired new total instead, calculate the increase as new total minus current limit and confirm it is positive. Ask for clarification for missing, ambiguous, non-positive, or non-whole-dollar requests.

## Tier rules

Use these rules:

| Tier | Minimum age | Cooldown after an approved request | Utilization must be below | Maximum increase | Required consecutive on-time months |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | 70% | 25% of current limit | 6 |
| Mid-tier | 90 days | 90 days | 80% | 50% of current limit | 3 |
| Premium-tier | 60 days | 60 days | 90% | 50% of current limit | 3 |

Determine the tier from the product information available in the case. A Gold Rewards Card presented as a premium card is handled as Premium-tier. If the product-to-tier mapping is not established, do not guess; obtain the applicable tier before proceeding.

Use `scripts/evaluate_cli.py` to calculate dates, utilization, maximum amount, and the final deterministic eligibility result. Its result is a check aid, not a substitute for the required tool checks.

## Required sequence

1. **Validate the amount before submitting.** Retrieve the current limit, determine the tier, and calculate the maximum increase. The requested amount must be positive, in whole dollars, and no greater than the tier maximum. If it exceeds the maximum, tell the customer the maximum permitted increase and ask whether they want to request that or a lower amount. Do **not** submit the over-limit request and do not call an approval or denial tool for it.

2. **Submit the valid request before eligibility checks.** Unlock and call `submit_credit_limit_increase_request_7392` with exactly `credit_card_account_id`, `user_id`, and `requested_increase_amount`. Preserve the submission result as the formal request record. The customer's stated reason should be retained in case notes or the customer dialogue where the environment provides no reason field. Remind the customer that updated income information may be needed for review; do not invent an income-recording action if no such tool exists.

3. **Perform every eligibility check after submission, even if an earlier check fails.** Unlock and call all of:

   - `get_credit_limit_increase_history_4829` with the account ID. Examine prior requests and find the most recent **previous approved** request. Denied requests do not start a cooldown. Do not mistake the request just submitted in step 2 for a prior approved request. A cooldown has elapsed only when the required full number of days has passed since that prior request's submission date.
   - `get_user_dispute_history_7291` with the user ID. Any dispute with an active/non-final status, such as `open` or `under_review`, fails the dispute requirement. A closed dispute is not active.
   - `get_pending_replacement_orders_5765` with the account ID. Any non-final replacement order, such as `pending` or `shipped`, fails the replacement requirement. Only delivered or cancelled orders are final.
   - `get_payment_history_6183` with the account ID and the tier's required number of months. Verify that all required consecutive months are on time.

   Also inspect the account data for account age, a current/no-past-due standing, balance, and credit limit. Compute utilization as `current_balance / current_credit_limit * 100`; it must be strictly below the tier threshold. A zero balance is valid. Do not infer that a balance of zero alone proves no past-due balance: an explicit current/standing/past-due field or equivalent reliable account result is required.

4. **Handle unavailable or ambiguous evidence safely.** Approval requires an explicit successful result for every check. If a required tool fails, a record lacks the data needed to establish a check, or standing cannot be verified, do not approve. Explain that processing cannot be completed from the available record and follow the environment's support/escalation process if available. Do not manufacture a denial reason merely to conceal missing evidence. If eligibility evidence establishes one or more failures, use the denial process below after completing all checks.

5. **Record the decision.** For an eligible request, unlock and call `approve_credit_limit_increase_5847` with the account ID, user ID, and `new_credit_limit = current_credit_limit + requested_increase_amount` as a float. For an ineligible request, unlock and call `deny_credit_limit_increase_5848` with the account ID, user ID, and one allowed reason:

   - account age: `insufficient_account_age`
   - approved-request cooldown: `cooldown_period_active`
   - active dispute: `pending_disputes`
   - outstanding replacement order: `pending_replacement_card`
   - past due/not current: `past_due_balance`
   - utilization at or above the threshold: `high_utilization`
   - insufficient consecutive on-time history: `insufficient_payment_history`

   The amount-exceeds-limit code exists for recorded denials, but the required pre-submission rule means an over-limit request should normally be redirected before submission rather than denied. If several failures exist, retain all check findings in the audit context and select the first applicable reason in the ordered list above for the tool's single `denial_reason` argument.

6. **Communicate the outcome.** On approval, confirm the new total credit limit. On denial, state the applicable condition and useful next step: the date cooldown ends when known, the required account-age date when known, payment improvement, lower utilization, resolution of disputes/replacement order, or bringing the account current. Do not expose internal eligibility details beyond the customer-appropriate reason.

## Calculator script

`scripts/evaluate_cli.py` reads one JSON object from standard input and emits one JSON object on standard output. It performs no banking action.

Input schema:

```json
{
  "current_date": "YYYY-MM-DD or timestamp",
  "account_open_date": "YYYY-MM-DD or timestamp",
  "tier": "Entry-tier | Mid-tier | Premium-tier",
  "current_credit_limit": "number",
  "current_balance": "number",
  "requested_increase_amount": "integer",
  "prior_approved_request_dates": ["YYYY-MM-DD or timestamp"],
  "active_disputes": true,
  "pending_replacement_orders": false,
  "past_due_balance": false,
  "consecutive_on_time_months": 3
}
```

Use `null` for a check that has not been reliably verified. `prior_approved_request_dates` must contain only requests approved before the newly submitted request. The output includes normalized values, every individual check, all established failures, a safe pre-submission amount disposition, and a post-submission action of `approve`, `deny`, or `incomplete`. Validate that `amount_disposition` is `valid` before submission, and only execute an output `approve`/`deny` decision after the real tool checks corroborate the supplied values.
