---
name: credit-limit-increase-processing
description: Execute a verified cardholder's credit-limit-increase (CLI) request through tier-limit validation, formal submission, mandatory eligibility review, recorded approval or denial, and final customer communication. Use when internal customer/account tools and the documented discoverable CLI tools are available.
---

# Credit Limit Increase Processing

Use this Skill to complete an operational CLI workflow, not just explain policy. Obtain all customer identifiers, account facts, dates, balances, requested amounts, and tool results from the active case. Never reuse identifiers or values from another case.

## Preconditions

Before an account action:

1. Locate the customer and requested credit-card account, and confirm that the account belongs to the customer.
2. Complete the runtime's identity-verification process. When the standard verification tools are present, obtain customer confirmation of at least two profile fields among date of birth, email, phone number, and address, then call `get_current_time` and `log_verification` with the verified profile and returned timestamp.
3. Establish a positive whole-dollar **increase** amount. If the customer gave a desired total limit instead, calculate `desired_total_limit - current_credit_limit`; clarify a zero or negative result.
4. Determine the tier from supplied policy or account documentation. Do not ask the customer to classify their card when the documentation already maps its card type to a tier.

Do not treat information merely displayed by an internal profile lookup as customer confirmation. Once verification is complete and the amount is valid, proceed with the internal workflow in the same interaction; do not ask unnecessary tier questions, transfer the customer, or promise a later review.

## Tier rules

| Tier | Minimum age | Cooldown after approved request | Maximum utilization | Consecutive on-time payments | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | below 70% | 6 months | 25% of current limit |
| Mid-tier | 90 days | 90 days | below 80% | 3 months | 50% of current limit |
| Premium-tier | 60 days | 60 days | below 90% | 3 months | 50% of current limit |

An amount exactly equal to the maximum is valid. If an amount exceeds its tier maximum, do **not** submit or record a denial for that unsubmitted amount. State the maximum and ask whether the customer wants that lower amount instead.

## Required execution order

### 1. Validate amount, then formally submit

Calculate `maximum_increase = current_credit_limit * tier_fraction`. For a valid confirmed amount, call:

`submit_credit_limit_increase_request_7392`

with exactly these case-derived arguments:

- `credit_card_account_id`
- `user_id`
- `requested_increase_amount` (integer dollars)

The formal submission must occur before every eligibility lookup. It creates the record being reviewed.

### 2. Complete every required review

After successful submission, perform **all** of these calls, even if an earlier result appears disqualifying:

- `get_credit_limit_increase_history_4829` with `credit_card_account_id`
- `get_user_dispute_history_7291` with `user_id`
- `get_pending_replacement_orders_5765` with `credit_card_account_id`
- `get_payment_history_6183` with `credit_card_account_id` and `months` set to 6 for entry-tier or 3 for mid-tier and premium-tier

Also assess the current account record and current date:

- account age meets the tier minimum;
- the account is current and has no past-due balance;
- utilization, `current_balance / current_credit_limit * 100`, is strictly below the tier threshold.

Interpret the returned data conservatively:

- A cooldown applies only where the relevant most recent prior CLI request was approved; denied requests do not trigger it.
- A dispute not clearly closed/final is active.
- A replacement order not clearly delivered or cancelled is pending.
- Payment history must show the required count of consecutive on-time months.
- Failed, partial, missing, or ambiguous required data is not evidence for approval. Resolve it before recording a decision.

### 3. Record a decision only after all checks

After all four lookups and account assessments are complete:

- If every condition passes, call `approve_credit_limit_increase_5847` with `credit_card_account_id`, `user_id`, and `new_credit_limit = current_credit_limit + requested_increase_amount`.
- Otherwise call `deny_credit_limit_increase_5848` with `credit_card_account_id`, `user_id`, and one allowed `denial_reason`:
  - `insufficient_account_age`
  - `cooldown_period_active`
  - `pending_disputes`
  - `pending_replacement_card`
  - `past_due_balance`
  - `high_utilization`
  - `insufficient_payment_history`
  - `requested_amount_exceeds_limit`
  - `other`

For multiple established failures, select the first applicable reason in this order: account age, cooldown, disputes, replacement, past due, utilization, payment history. An excessive requested amount normally is not submitted, so it normally does not result in a recorded denial.

### 4. Send the final customer message

Only after the account action is recorded, give the customer a substantive outcome:

- **Approval:** clearly say it was approved and state the new total credit limit.
- **Denial:** state the customer-appropriate reason and meaningful next steps. Include a reapplication date if calculable. For a pending replacement, explain it must be delivered or cancelled; for utilization, explain it must be reduced below the applicable threshold.

Never claim an approval or denial before its corresponding tool action succeeds.

## Discoverable-tool protocol

The CLI functions are specialized internal tools. For each required function, use the runtime's normal discoverable-agent sequence: call `unlock_discoverable_agent_tool` using the exact function name, then call `call_discoverable_agent_tool` with that same name and a JSON-object string in `arguments`. The observable functional order must remain: submission, all four lookups, decision, final customer message.

Required specialized functions:

- `submit_credit_limit_increase_request_7392`
- `get_credit_limit_increase_history_4829`
- `get_user_dispute_history_7291`
- `get_pending_replacement_orders_5765`
- `get_payment_history_6183`
- `approve_credit_limit_increase_5847`
- `deny_credit_limit_increase_5848`

## Evaluation helper

`scripts/evaluate_cli.py` deterministically evaluates normalized data already retrieved during review. It makes no banking calls and cannot submit, approve, deny, or notify a customer. Use it only after formal submission and after every required lookup has returned.

Run it with `run_skill_script(relative_path="scripts/evaluate_cli.py", input_json=<object>)`.

Input object schema:

- `current_time`: string beginning `YYYY-MM-DD`
- `account`: object with `tier`, `opened_on`, `current_credit_limit`, `current_balance`, and explicit boolean `past_due`
- `requested_increase_amount`: positive whole-dollar number
- `prior_requests`: list of preexisting objects with `submitted_at` and `status`; exclude the request just submitted
- `has_active_disputes`: boolean
- `has_pending_replacement`: boolean
- `payment_history`: object with integer `consecutive_on_time_months`

It emits JSON with `recommendation` (`approve`, `deny`, `do_not_submit`, or `incomplete`), individual checks, calculated limits, and an allowed denial reason when applicable. An `incomplete` result must be resolved, not converted into a decision.
