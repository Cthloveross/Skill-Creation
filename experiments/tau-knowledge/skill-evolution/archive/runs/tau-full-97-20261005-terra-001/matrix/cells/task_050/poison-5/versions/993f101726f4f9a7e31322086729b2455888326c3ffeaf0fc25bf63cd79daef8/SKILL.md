---
name: credit-limit-increase-processing
description: Process a verified credit-card credit-limit-increase (CLI) request end-to-end. Use when a cardholder requests a limit increase and the agent can identify the card account, verify identity, and access the required banking actions or discoverable internal tools.
---

# Credit Limit Increase Processing

Process a valid CLI request to completion. Do not ask a customer to classify a card whose tier is documented, and do not transfer merely because internal eligibility checks are required. Use only identifiers, balances, dates, amounts, and tool results from the active case.

## Prerequisites

Before any account-changing action:

1. Locate the customer and the requested credit-card account. Confirm the account belongs to the customer.
2. Follow the runtime identity-verification process. Confirm at least two profile fields from date of birth, email, phone number, or address against the retrieved profile. Obtain the current time and call `log_verification` with the complete retrieved profile and timestamp.
3. Obtain a positive whole-dollar **increase** amount. If the customer gives a desired total limit, calculate `desired_total_limit - current_credit_limit`; clarify a non-positive or non-whole-dollar result.
4. Determine the card tier from the supplied account and policy material. A Gold Rewards Card is premium-tier under the available card operational policy.

A profile lookup alone is not identity verification. Once identity is verified and the amount is valid, continue the internal process during the same interaction.

## CLI tier rules

| Tier | Minimum age | Cooldown after approved request | Maximum utilization | Required consecutive on-time payments | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | below 70% | 6 months | 25% of current limit |
| Mid-tier | 90 days | 90 days | below 80% | 3 months | 50% of current limit |
| Premium-tier | 60 days | 60 days | below 90% | 3 months | 50% of current limit |

Calculate `maximum_increase = current_credit_limit × tier fraction`. An amount equal to the maximum is permitted. If the requested amount exceeds the maximum, do not submit it: tell the customer the permitted maximum and ask whether they want to proceed with that amount.

## Required execution order

For a verified, confirmed amount within the tier maximum, perform these steps in this exact order.

### 1. Submit before reviewing eligibility

Call `submit_credit_limit_increase_request_7392` with:

- `credit_card_account_id`: verified account ID
- `user_id`: verified customer ID
- `requested_increase_amount`: confirmed integer dollar increase

This formal submission must precede every CLI eligibility lookup.

### 2. Perform every required eligibility lookup

After the submission succeeds, run all four checks even if one result appears disqualifying:

1. `get_credit_limit_increase_history_4829` with `credit_card_account_id`
2. `get_user_dispute_history_7291` with `user_id`
3. `get_pending_replacement_orders_5765` with `credit_card_account_id`
4. `get_payment_history_6183` with `credit_card_account_id` and `months` set to `6` for entry-tier or `3` for mid-tier and premium-tier

Also assess the account record and current date:

- Account age satisfies the tier minimum.
- The account is current and has no past-due balance.
- Utilization is strictly below the tier maximum: `current_balance / current_credit_limit × 100`.

Interpret results conservatively:

- Only prior requests with an approved status trigger the tier cooldown.
- A dispute not clearly closed/final is active.
- A replacement order not clearly delivered or cancelled is pending.
- The returned payment history must establish the required number of consecutive on-time months.
- Missing, failed, partial, or ambiguous evidence is not favorable evidence. Retry or resolve a required lookup before recording a decision; never invent a result.

### 3. Record the outcome after all checks

Only after all four lookups and all account assessments are complete:

- If every criterion passes, call `approve_credit_limit_increase_5847` with `credit_card_account_id`, `user_id`, and `new_credit_limit = current_credit_limit + requested_increase_amount`.
- If a criterion fails, call `deny_credit_limit_increase_5848` with `credit_card_account_id`, `user_id`, and exactly one permitted `denial_reason`:
  - `insufficient_account_age`
  - `cooldown_period_active`
  - `pending_disputes`
  - `pending_replacement_card`
  - `past_due_balance`
  - `high_utilization`
  - `insufficient_payment_history`
  - `requested_amount_exceeds_limit`
  - `other`

If several criteria fail, select the first established reason in this order: account age, cooldown, disputes, replacement, past due, utilization, payment history. An over-limit amount ordinarily is not submitted, so it ordinarily is not recorded as a denial.

### 4. Communicate the recorded decision

After the approval or denial action succeeds, send a substantive customer-facing final message:

- **Approval:** say the increase was approved and state the new total credit limit.
- **Denial:** explain the applicable reason and meaningful next steps. State a reapplication date when it can be calculated. For a pending replacement, explain that it must be delivered or cancelled; for utilization, explain that utilization must be reduced below the applicable threshold.

Never claim an approval or denial before the corresponding action has succeeded. Do not end with only a transfer or internal-status message.

## Discoverable internal-tool protocol

The required CLI actions may be exposed directly or through the discoverable-agent interface.

- If a specialized function is directly available, call it directly using the arguments above.
- If it is discoverable, first call `unlock_discoverable_agent_tool` with its exact function name, then call `call_discoverable_agent_tool` with the same name and an `arguments` JSON-object string.

The specialized-function sequence remains unchanged when wrappers are used: submit, all four checks, approve or deny, then communicate. The required functions for a submitted request are:

- `submit_credit_limit_increase_request_7392`
- `get_credit_limit_increase_history_4829`
- `get_user_dispute_history_7291`
- `get_pending_replacement_orders_5765`
- `get_payment_history_6183`
- `approve_credit_limit_increase_5847` or `deny_credit_limit_increase_5848`

## Optional deterministic evaluation helper

`scripts/evaluate_cli.py` evaluates normalized facts already retrieved from the required calls. It makes no banking calls and cannot submit, approve, deny, or notify a customer. Use it only after submission and after all required results are available.

Run with:

`run_skill_script(relative_path="scripts/evaluate_cli.py", input_json=<object>)`

Input JSON object:

- `current_time`: string beginning `YYYY-MM-DD`
- `account`: object with `tier`, `opened_on`, `current_credit_limit`, `current_balance`, and explicit boolean `past_due`
- `requested_increase_amount`: positive whole-dollar number
- `prior_requests`: list of prior (not newly submitted) request objects with `submitted_at` and `status`
- `has_active_disputes`: boolean
- `has_pending_replacement`: boolean
- `payment_history`: object with integer `consecutive_on_time_months`

It emits a JSON object with `recommendation` (`approve`, `deny`, `do_not_submit`, or `incomplete`), calculated amounts, checks, and an allowed denial reason when applicable. Resolve `incomplete` output before recording a decision.
