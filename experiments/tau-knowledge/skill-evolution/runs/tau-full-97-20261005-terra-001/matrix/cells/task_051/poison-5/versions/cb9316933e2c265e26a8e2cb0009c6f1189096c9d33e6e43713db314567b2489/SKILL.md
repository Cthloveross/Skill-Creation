---
name: credit-limit-increase-workflow
description: Execute a verified cardholder's credit-limit-increase request using documented tier limits, mandatory post-submission eligibility reviews, and the required approval or denial record. Use when a credit-card account, a confirmed CLI amount, and internal CLI tools are available.
---

# Credit Limit Increase Workflow

This is an execution workflow, not an advisory workflow. Follow this order exactly:

1. validate the amount;
2. submit the valid confirmed request;
3. complete every required review;
4. record the approval or denial; and
5. communicate the recorded decision.

Do not transfer a customer or solicit a new amount when the current case already contains a verified customer, account, and an explicit customer confirmation of a valid amount.

## Use current-case facts

Treat completed clarification answers and supplied read-only observations as current-case evidence. Use the customer's latest explicit, definite amount confirmation; it supersedes an earlier approximate, percentage-based, or over-limit request. Do not repeat a question that the case already answers.

Before any account-changing action, use the active case's normal verification state and verify that the selected account belongs to the verified customer. Obtain the account ID, user ID, card type/tier, current limit, balance, opening date, status, and past-due amount from reliable current account data. Do not invent missing values.

Determine the tier only from applicable card documentation. Do not infer a tier solely from a card name unless the documentation provides that mapping.

## Policy table

| Tier | Minimum account age | Approved-request cooldown | Required utilization | Consecutive on-time payments | Maximum request increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | strictly below 70% | 6 months | 25% of current limit |
| Mid-tier | 90 days | 90 days | strictly below 80% | 3 months | 50% of current limit |
| Premium-tier | 60 days | 60 days | strictly below 90% | 3 months | 50% of current limit |

A denied prior CLI does not create a cooldown. Utilization equal to a threshold fails because the requirement is strictly below the threshold.

## Mandatory tool-call sequence

### 1. Validate the amount before submission

Calculate the maximum increase as current credit limit times the tier fraction. `scripts/evaluate_cli.py` in `amount_check` mode can perform this calculation.

The request amount must be a confirmed whole-dollar increase no greater than that maximum. If the customer requests more than the cap, state the permitted cap and obtain a clear confirmation of an amount at or below it. Never submit the excessive amount. Once a valid adjusted amount is confirmed in the case, proceed directly to submission; do not ask for a different amount.

### 2. Submit before eligibility tools

After the amount is valid and confirmed, unlock and call `submit_credit_limit_increase_request_7392` before any eligibility-review tool. Pass exactly the current case's:

```json
{
  "credit_card_account_id": "<verified account ID>",
  "user_id": "<verified user ID>",
  "requested_increase_amount": "<confirmed whole-dollar integer>"
}
```

`requested_increase_amount` must be sent as an integer, not a percentage, total credit limit, or formatted currency string. Submission creates the required formal record and must not be skipped merely because account data suggests a likely denial.

### 3. Complete all eligibility reviews after submission

After submission, unlock and call **all four** tools below. Perform every call even if one prior review, age, standing, or utilization already fails. Use the verified IDs exactly.

1. `get_credit_limit_increase_history_4829`
   ```json
   {"credit_card_account_id":"<verified account ID>"}
   ```
   Review the most recent relevant approved request and apply the tier cooldown.

2. `get_user_dispute_history_7291`
   ```json
   {"user_id":"<verified user ID>"}
   ```
   Treat open or under-review disputes as active; closed disputes are not active.

3. `get_pending_replacement_orders_5765`
   ```json
   {"credit_card_account_id":"<verified account ID>"}
   ```
   Treat any order not clearly delivered or cancelled, including pending or shipped, as pending.

4. `get_payment_history_6183`
   ```json
   {"credit_card_account_id":"<verified account ID>","months":"<tier-required integer>"}
   ```
   Confirm that every required consecutive month is on time.

Also review the retrieved account data after submission for all of the following:

- account age meets the tier minimum;
- the account is current and has no past-due balance; and
- utilization, calculated as `current_balance / current_credit_limit * 100`, is strictly below the tier threshold.

Do not approve or deny until the four external checks and these account-data checks are complete.

### 4. Record the decision

Use the collected, current facts. `scripts/evaluate_cli.py` in `evaluate` mode may calculate the policy checks, but it has no banking side effects and never replaces the required tool calls.

- If every requirement passes, unlock and call `approve_credit_limit_increase_5847` with the verified account ID, verified user ID, and numeric new total credit limit.
- If any requirement fails, unlock and call `deny_credit_limit_increase_5848` with the verified account ID, verified user ID, and the supported reason established by the completed review.

Supported denial reasons are:

- `insufficient_account_age`
- `cooldown_period_active`
- `pending_disputes`
- `pending_replacement_card`
- `past_due_balance`
- `high_utilization`
- `insufficient_payment_history`
- `requested_amount_exceeds_limit`
- `other`

Use `high_utilization` whenever the account's calculated utilization fails the tier's strictly-below threshold. The denial call must occur only after all four external review calls.

### 5. Communicate after recording the result

For an approval, confirm that the request was approved and state the new total limit.

For a denial, clearly state that the submitted request was denied, explain the reviewed reason, and give a practical next step. For high utilization, state that utilization must be below the applicable tier threshold and advise paying down the balance before reapplying. Provide a reapplication date when the failed condition makes one determinable.

## Missing or ambiguous review data

After a valid request has been submitted, an earlier failed condition does not permit skipping remaining required reviews. If a required tool result is malformed, unavailable, or ambiguous, do not assume it passes and do not approve. Apply normal retry or escalation handling for unavailable evidence; never invent tool results, approval status, or a denial reason unsupported by reviewed facts.

## Read-only evaluator interface

`scripts/evaluate_cli.py` reads one JSON object from stdin and writes one JSON object to stdout. It makes no banking-tool calls and has no banking side effects.

For amount validation, supply:

```json
{
  "mode": "amount_check",
  "tier": "entry-tier|mid-tier|premium-tier",
  "current_credit_limit": "non-negative number",
  "requested_increase_amount": "non-negative integer"
}
```

For a complete review, supply:

```json
{
  "mode": "evaluate",
  "tier": "entry-tier|mid-tier|premium-tier",
  "current_credit_limit": "positive number",
  "requested_increase_amount": "non-negative integer",
  "account_open_date": "YYYY-MM-DD, MM/DD/YYYY, or ISO timestamp",
  "current_date": "YYYY-MM-DD, MM/DD/YYYY, or ISO timestamp",
  "current_balance": "non-negative number",
  "account_current": "boolean",
  "past_due_amount": "non-negative number",
  "last_approved_request_date": "date string or null",
  "active_disputes": "boolean",
  "pending_replacement": "boolean",
  "consecutive_on_time_months": "non-negative integer"
}
```

The evaluator returns the amount cap, proposed total limit, utilization, individual checks, eligibility, and a supported denial reason. Validate that every input was derived from the current account and completed post-submission reviews before using the output.
