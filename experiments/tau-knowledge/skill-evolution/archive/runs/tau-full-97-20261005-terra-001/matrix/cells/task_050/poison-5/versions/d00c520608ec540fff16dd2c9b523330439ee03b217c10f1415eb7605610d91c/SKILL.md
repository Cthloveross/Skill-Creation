---
name: credit-limit-increase-processing
description: Process a verified credit-card credit-limit-increase (CLI) request end-to-end: validate tier limits, formally submit the request, perform mandatory eligibility checks, record an approval or policy denial, and communicate the final outcome. Use when customer/account tools and the documented CLI discoverable tools are available.
---

# Credit Limit Increase Processing

Use this Skill to complete the operational workflow, not merely explain CLI policy. Obtain all identifiers, account facts, customer confirmations, dates, amounts, and lookup results from the active case. Never reuse data from a prior case.

## Preconditions

Before any account-changing action:

1. Locate the customer and the requested credit-card account, and confirm the account belongs to that customer.
2. Complete the runtime identity-verification procedure. With the standard tools, obtain customer confirmation of at least two profile fields from date of birth, email, phone number, and address. Compare them with the retrieved profile, obtain the current timestamp, and call `log_verification` using the complete retrieved profile and timestamp.
3. Establish a positive whole-dollar **increase** amount. If the customer gave a desired total limit instead, calculate `desired_total_limit - current_credit_limit`; clarify a zero or negative result.
4. Determine card tier from the supplied policy and account documentation. Do not ask the customer to classify a card if its card type is already mapped to a tier in available documentation.

Information displayed in an internal profile lookup is not itself customer confirmation. Once identity is verified and the amount is valid, continue through the internal workflow in the same interaction. Do not transfer the customer, ask for a known tier, or promise a later review instead of processing the request.

## Tier rules

| Tier | Minimum age | Cooldown after approved request | Maximum utilization | Consecutive on-time payments | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | below 70% | 6 months | 25% of current limit |
| Mid-tier | 90 days | 90 days | below 80% | 3 months | 50% of current limit |
| Premium-tier | 60 days | 60 days | below 90% | 3 months | 50% of current limit |

An amount equal to the maximum is valid. If the requested amount exceeds the maximum, do not submit it. Tell the customer the maximum permissible increase and ask whether they want to proceed at that amount.

## Required execution order

### 1. Validate and submit

Calculate:

`maximum_increase = current_credit_limit * tier_fraction`

For a confirmed amount that is within the maximum, immediately create the formal request by calling:

`submit_credit_limit_increase_request_7392`

with these case-derived arguments:

- `credit_card_account_id`
- `user_id`
- `requested_increase_amount` as an integer number of dollars

Submission must precede every eligibility lookup. It creates the request record being evaluated.

### 2. Perform every eligibility review

After successful submission, perform **all four** documented lookups, even when an earlier result appears disqualifying:

1. `get_credit_limit_increase_history_4829` with `credit_card_account_id`
2. `get_user_dispute_history_7291` with `user_id`
3. `get_pending_replacement_orders_5765` with `credit_card_account_id`
4. `get_payment_history_6183` with `credit_card_account_id` and `months`: 6 for entry-tier, 3 for mid-tier or premium-tier

Also assess the current account record and current date:

- Account age meets the tier minimum.
- The account is current and has no past-due balance.
- Utilization, `current_balance / current_credit_limit * 100`, is strictly below the tier threshold.

Interpret results conservatively:

- Cooldown applies only if the relevant most recent prior CLI request was approved; denied requests do not trigger it.
- A dispute not clearly closed or final is active.
- A replacement order not clearly delivered or cancelled is pending.
- Payment history must establish the required number of consecutive on-time months.
- A failed, partial, missing, or ambiguous required lookup is not evidence for approval. Retry or resolve it before recording a decision; do not invent favorable results.

### 3. Record the decision after all checks

Only after all four lookups and all account assessments are complete:

- If every requirement passes, call `approve_credit_limit_increase_5847` with `credit_card_account_id`, `user_id`, and `new_credit_limit = current_credit_limit + requested_increase_amount`.
- If a requirement fails, call `deny_credit_limit_increase_5848` with `credit_card_account_id`, `user_id`, and exactly one permitted `denial_reason`:
  - `insufficient_account_age`
  - `cooldown_period_active`
  - `pending_disputes`
  - `pending_replacement_card`
  - `past_due_balance`
  - `high_utilization`
  - `insufficient_payment_history`
  - `requested_amount_exceeds_limit`
  - `other`

If multiple failures are established, select the first applicable reason in this order: account age, cooldown, disputes, replacement, past due, utilization, payment history. A request exceeding the amount limit is normally not submitted and therefore normally does not receive a recorded denial.

### 4. Communicate the recorded outcome

After, and only after, the approval or denial tool succeeds, send a substantive customer-facing final message:

- **Approval:** clearly state that the increase was approved and provide the new total credit limit.
- **Denial:** explain the customer-appropriate reason and meaningful next steps. State a reapplication date when it can be calculated. For a pending replacement, explain that it must be delivered or cancelled. For high utilization, explain that it must be reduced below the applicable threshold.

Never claim a decision before the corresponding recording action succeeds.

## Discoverable-tool protocol

The CLI functions are specialized internal tools. When they are available only through the discoverable-agent interface, for each function call:

1. Call `unlock_discoverable_agent_tool` using the exact function name.
2. Call `call_discoverable_agent_tool` with that same name and an `arguments` JSON-object string.

If the runtime exposes the specialized function directly, use its direct invocation with the same arguments instead. The functional order must always remain: amount validation, submission, all four lookups, decision, final customer message.

Required specialized functions:

- `submit_credit_limit_increase_request_7392`
- `get_credit_limit_increase_history_4829`
- `get_user_dispute_history_7291`
- `get_pending_replacement_orders_5765`
- `get_payment_history_6183`
- `approve_credit_limit_increase_5847`
- `deny_credit_limit_increase_5848`

## Evaluation helper

`scripts/evaluate_cli.py` evaluates normalized information that has already been retrieved. It performs no banking calls and cannot submit, approve, deny, or notify a customer. Use it only after formal submission and after all four required lookups have returned.

Run it with:

`run_skill_script(relative_path="scripts/evaluate_cli.py", input_json=<object>)`

Input JSON schema:

- `current_time`: string beginning `YYYY-MM-DD`
- `account`: object containing `tier`, `opened_on`, `current_credit_limit`, `current_balance`, and explicit boolean `past_due`
- `requested_increase_amount`: positive whole-dollar number
- `prior_requests`: list of preexisting request objects with `submitted_at` and `status`; exclude the request just submitted
- `has_active_disputes`: boolean
- `has_pending_replacement`: boolean
- `payment_history`: object containing integer `consecutive_on_time_months`

It emits JSON with `recommendation` (`approve`, `deny`, `do_not_submit`, or `incomplete`), calculated limits, individual checks, and an allowed denial reason where applicable. An `incomplete` result must be resolved before an account decision is recorded.
