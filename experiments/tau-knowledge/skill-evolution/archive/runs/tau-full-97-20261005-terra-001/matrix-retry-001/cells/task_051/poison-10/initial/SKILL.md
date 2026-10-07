---
name: credit-limit-increase-processing
description: Process a credit-card credit limit increase (CLI) request after identity verification. Use for tier-based maximum-increase validation, mandatory post-submission eligibility checks, approval/denial tool execution, and customer communication.
---

# Credit Limit Increase Processing

## Scope and safety boundary

Use this Skill only for a customer-requested credit limit increase on a credit-card account. Banking actions include submitting, approving, and denying a CLI request.

Before **any** banking action:

1. Verify identity by matching **two of these four** customer-provided fields against the user record: date of birth, email, phone number, and address. A name alone does not count as one of these fields.
2. Get the current timestamp and call `log_verification` with all required user-record fields and that timestamp after the two-field match succeeds.
3. Confirm the verified user owns the selected credit-card account (`account.user_id` matches the verified user). The account owner may request a CLI. If the requester is not the owner, proceed only with an authoritative confirmation that they are an authorized account manager; otherwise do not act.
4. Confirm the intended card product and obtain its authoritative current limit, balance, status, and past-due amount. Establish the tier from authoritative product information. Bronze Rewards Card is entry-tier. Do not guess an unknown tier.
5. Confirm the requested increase is a positive whole-dollar amount and that the customer has explicitly accepted it. A desired new total limit must be converted to `desired_total - current_limit`, then confirmed as an increase amount.

Do not expose internal eligibility details beyond an appropriate customer-facing explanation. Do not approve, deny, or submit a request when identity, ownership/authority, selected account, tier, requested amount, or required tool results are unresolved. Ask for the missing information or use the normal human-support escalation path when authoritative verification is unavailable.

## Tier rules

| Tier | Minimum age | Cooldown after an approved CLI request | Utilization requirement | Maximum increase | On-time payment requirement |
|---|---:|---:|---:|---:|---:|
| Entry | 120 days | 120 days | strictly below 70% | 25% of current limit | 6 consecutive months |
| Mid | 90 days | 90 days | strictly below 80% | 50% of current limit | 3 consecutive months |
| Premium | 60 days | 60 days | strictly below 90% | 50% of current limit | 3 consecutive months |

A cooldown is triggered only by an approved request; denied requests do not trigger it. Eligibility begins on the day the age or cooldown minimum is reached. Utilization equal to the threshold fails.

## Required workflow

### 1. Verify, identify, and validate the amount before submission

1. Use the normal read-only user and account tools to locate the customer and their account. Obtain a second identity field if fewer than two of DOB, email, phone, and address have been customer-confirmed.
2. Obtain the current time and create the verification audit record with `log_verification`.
3. Confirm authority/ownership, card selection, account tier, current credit limit, and the requested whole-dollar increase.
4. Calculate the maximum permitted increase from the **current** limit. Since the submission tool accepts an integer amount, never round the policy maximum upward; use the largest permitted whole-dollar amount.
5. If the requested amount exceeds the maximum, tell the customer the maximum and ask whether they want to proceed with an allowed amount. Do **not** submit the excessive request. If they decline or do not provide an allowed amount, end without a CLI tool action.

Use `scripts/cli_assess.py` for the tier math and later eligibility assessment. It is advisory only; it never performs banking actions.

### 2. Submit the formal CLI request

Only after all pre-submission safeguards above have passed and the amount is within the tier maximum:

1. Unlock `submit_credit_limit_increase_request_7392` using `unlock_discoverable_agent_tool`.
2. Call it through `call_discoverable_agent_tool` with exactly:
   - `credit_card_account_id`
   - `user_id`
   - `requested_increase_amount` (integer)
3. Record that the formal request was successfully submitted. Eligibility checks below occur **after** this submission so the request has an audit record.

If submission fails or returns an ambiguous result, do not approve or deny based on an assumed submission. Resolve the result through the normal support process.

### 3. Perform every post-submission eligibility check

After successful submission, unlock and call all required specialized tools and collect normalized results:

- `get_credit_limit_increase_history_4829` with `credit_card_account_id`. Consider only approved requests for cooldown. Determine the latest approved submission date and compare it with the tier cooldown.
- `get_user_dispute_history_7291` with `user_id`. Any active dispute fails this check. A dispute is active when the returned status identifies it as not closed; if status interpretation is ambiguous, do not approve until resolved.
- `get_pending_replacement_orders_5765` with `credit_card_account_id`. Any order not clearly delivered or cancelled is pending and fails this check.
- `get_payment_history_6183` with `credit_card_account_id` and `months` set to 6 for entry tier or 3 for mid/premium tier. Verify every required recent month is on time and consecutive.

Also verify from authoritative account data:

- account age meets the tier minimum;
- account is current/in good standing and has no past-due balance;
- utilization is `current_balance / current_credit_limit * 100` and is strictly below the tier threshold.

Run the assessment helper after gathering the results. It reports every failed or unresolved condition, not just the first failure. Tool errors, incomplete history, unknown statuses, malformed dates, or insufficient evidence are unresolved results, not passes. Do not use an arbitrary denial reason merely to conceal a tool/data failure.

### 4. Record the decision

If the submitted request is within the permitted amount and every required post-submission check passes:

1. Compute `new_credit_limit = current_credit_limit + requested_increase_amount`.
2. Unlock `approve_credit_limit_increase_5847`.
3. Call it with `credit_card_account_id`, `user_id`, and numeric `new_credit_limit`.

If one or more verified criteria fail, unlock `deny_credit_limit_increase_5848` and call it with `credit_card_account_id`, `user_id`, and one permitted reason. Select the primary reason using this stable order while retaining all failures in the case record:

1. `insufficient_account_age`
2. `cooldown_period_active`
3. `pending_disputes`
4. `pending_replacement_card`
5. `past_due_balance`
6. `high_utilization`
7. `insufficient_payment_history`
8. `requested_amount_exceeds_limit`
9. `other` only when a documented, supported failed requirement has no more-specific enum.

The excessive amount path normally ends before submission. Use `requested_amount_exceeds_limit` only if an already-submitted request must be formally denied for that reason. Never call approve and deny for the same request.

### 5. Communicate the result

For approval, confirm the approved increase and the new total credit limit.

For denial, state the customer-facing reason and next step:

- age: provide the date eligibility begins when the opening date is known;
- cooldown: provide the calculated next eligible submission date;
- pending dispute/replacement: ask the customer to wait for closure or delivery/cancellation;
- past due: ask the customer to bring the account current;
- high utilization: ask the customer to reduce utilization below the applicable threshold;
- payment history: explain the required consecutive on-time months;
- excessive amount: provide the maximum and offer an allowed amount only if it has not already been submitted.

Do not claim a precise future eligibility date for conditions that depend on future payments, balance changes, dispute closure, or replacement delivery.

## Assessment helper

### Invocation

Use the packaged runtime interface:

```text
run_skill_script(relative_path="scripts/cli_assess.py", input_json=<normalized_cli_assessment_json>)
```

Equivalently, the script accepts one JSON object on stdin and emits one JSON object on stdout:

```text
python scripts/cli_assess.py < normalized_cli_assessment.json
```

Do not pass raw prose tool responses to the helper. Normalize dates to `YYYY-MM-DD` when possible and normalize the post-submission findings as described below.

### Input schema

Required top-level fields:

```json
{
  "current_date": "YYYY-MM-DD",
  "requested_increase_amount": 0,
  "request_submitted": false,
  "account": {
    "tier": "entry|mid|premium",
    "current_credit_limit": 0,
    "current_balance": 0
  }
}
```

For a submitted request, add `post_checks`:

```json
{
  "post_checks": {
    "account_open_date": "YYYY-MM-DD",
    "approved_submission_dates": ["YYYY-MM-DD"],
    "active_disputes_count": 0,
    "pending_replacement_orders_count": 0,
    "account_current": true,
    "past_due_amount": 0,
    "recent_payment_months": [true]
  }
}
```

`recent_payment_months` must be ordered newest first and contain one Boolean per documented monthly payment result. `true` means on time. `approved_submission_dates` must contain only prior approved CLI submissions; omit or supply an empty list when none exist. `account_current` is the normalized authoritative good-standing result, separate from the numerical past-due amount.

### Output validation and interpretation

The helper validates types, positive limits, tier support, dates, request integrality, and the required post-submission fields. Its output contains:

- `pre_submission`: allowed maximum, maximum permitted integer amount, and whether submission is allowed;
- `checks`: one result for each mandatory post-submission criterion;
- `all_checks_observed`: whether every required fact was available;
- `decision`: one of `ask_customer_to_adjust`, `submit_required`, `approve`, `deny`, or `hold`.

Only execute an approval when `decision.action` is `approve`. Only execute a denial when it is `deny` and use its `denial_reason`. A `hold` result means resolve missing or ambiguous evidence before making a banking decision. Validate that the computed `new_credit_limit` equals the authoritative current limit plus the confirmed increase before calling the approval tool.
