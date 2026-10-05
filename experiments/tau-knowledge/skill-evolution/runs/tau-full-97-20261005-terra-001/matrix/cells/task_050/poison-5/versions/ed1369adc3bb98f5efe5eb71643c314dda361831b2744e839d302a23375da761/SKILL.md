---
name: credit-limit-increase-processing
description: Process a verified credit-card holder's requested credit-limit increase through amount validation, formal submission, mandatory eligibility checks, recorded decision, and customer notification. Use for operational CLI requests when the internal discoverable CLI tools are available.
---

# Credit Limit Increase Processing

Use this Skill to execute an eligible customer's CLI workflow, not merely to explain CLI policy. Read all names, IDs, balances, dates, amounts, identity details, and tool results from the current case. Do not reuse values from a prior case.

## Preconditions

Before an account action:

1. Locate the customer and the requested card account, and verify that the account belongs to that customer.
2. Verify identity by having the customer confirm at least two profile fields among date of birth, email, phone number, and address. Do not count a field merely displayed by an internal lookup as customer confirmation.
3. Call `get_current_time` and then `log_verification` with the complete verified profile and returned timestamp.
4. Establish a positive whole-dollar **increase amount**. If the customer instead supplies a desired total limit, calculate `desired_total_limit - current_credit_limit`; clarify a nonpositive result.
5. Establish the card tier from current supplied documentation. Do not infer a tier from a card name unless the documentation maps that card to a tier.

If identity, ownership, account facts, tier, or amount is ambiguous, obtain the missing information before processing. Do not submit a CLI request for an unverified customer or account.

## Tier rules

| Tier | Minimum account age | Cooldown after an approved request | Maximum utilization | Consecutive on-time months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | below 70% | 6 | 25% of current limit |
| Mid-tier | 90 days | 90 days | below 80% | 3 | 50% of current limit |
| Premium-tier | 60 days | 60 days | below 90% | 3 | 50% of current limit |

An increase exactly equal to the tier maximum is valid. If the requested amount is over the maximum, do not submit it and do not record a denial for that unsubmitted request. Tell the customer the maximum and ask whether they want to continue with that amount.

## Required execution sequence

Once the customer has confirmed identity and a valid amount, begin the internal workflow immediately. Do not stop after acknowledging the request or tell the customer that a review will occur later.

### 1. Submit the formal request first

Call `submit_credit_limit_increase_request_7392` with:

- `credit_card_account_id`
- `user_id`
- `requested_increase_amount` as an integer dollar amount

This submission must precede every eligibility lookup. It creates the formal record required for review.

### 2. Perform every required eligibility lookup

After submission, complete all four calls, even when an earlier result appears disqualifying:

- `get_credit_limit_increase_history_4829` with `credit_card_account_id`
- `get_user_dispute_history_7291` with `user_id`
- `get_pending_replacement_orders_5765` with `credit_card_account_id`
- `get_payment_history_6183` with `credit_card_account_id` and `months` equal to the tier-required number of payment months

Also assess from the retrieved account record and current date:

- **Account age:** account open date meets the tier minimum.
- **Good standing:** account is current and has no past-due balance.
- **Utilization:** `current_balance / current_credit_limit * 100` is strictly below the tier threshold.

Interpret results as follows:

- A cooldown is triggered only by a prior approved CLI request. Denied requests do not trigger it. Calculate from the approved request's submission date.
- Any dispute not clearly final or closed is active.
- Any replacement order not clearly delivered or cancelled is pending.
- Required payment months must be consecutive and on time.
- Missing, failed, partial, or ambiguous lookup results are not approval evidence. Resolve the data issue before recording a decision.

### 3. Record the decision after all checks

Only after all four lookups and the account assessments are complete:

- If every requirement passes, call `approve_credit_limit_increase_5847` with `credit_card_account_id`, `user_id`, and `new_credit_limit`, calculated as `current_credit_limit + requested_increase_amount`.
- Otherwise, call `deny_credit_limit_increase_5848` with `credit_card_account_id`, `user_id`, and exactly one allowed `denial_reason`:
  - `insufficient_account_age`
  - `cooldown_period_active`
  - `pending_disputes`
  - `pending_replacement_card`
  - `past_due_balance`
  - `high_utilization`
  - `insufficient_payment_history`
  - `requested_amount_exceeds_limit`
  - `other`

When multiple reviewed criteria fail, use the first applicable reason in this order: account age, cooldown, disputes, replacement, past due, utilization, payment history. `requested_amount_exceeds_limit` ordinarily does not apply because an excessive request must not be submitted.

### 4. Communicate the recorded outcome

After the approval or denial is recorded, send a substantive customer-facing message:

- **Approval:** state that the request was approved and state the new total credit limit.
- **Denial:** state the applicable customer-appropriate reason and meaningful next steps. State a reapplication date when it can be calculated. For a pending replacement, explain that delivery or cancellation is required; for high utilization, explain that it must be reduced below the applicable threshold.

Never claim approval or denial before the corresponding account action has been recorded.

## Discoverable internal-tool protocol

The specialized CLI functions must be executed through the runtime's normal discoverable-agent mechanism. For each function, first call `unlock_discoverable_agent_tool` with its exact name, then call `call_discoverable_agent_tool` with the same `agent_tool_name` and a JSON object encoded in `arguments`. Use the exact names and argument keys listed above; do not substitute a customer-facing tool or merely describe the action.

The required specialized functions are:

- `submit_credit_limit_increase_request_7392`
- `get_credit_limit_increase_history_4829`
- `get_user_dispute_history_7291`
- `get_pending_replacement_orders_5765`
- `get_payment_history_6183`
- `approve_credit_limit_increase_5847`
- `deny_credit_limit_increase_5848`

Ensure the observable account-action order is submission, all four lookups, decision, then customer communication.

## Deterministic evaluation helper

`scripts/evaluate_cli.py` evaluates normalized information that has already been retrieved. It makes no banking calls and cannot submit, approve, or deny a request. Use it after formal submission and after all required lookups are complete.

Run it with `run_skill_script(relative_path="scripts/evaluate_cli.py", input_json=<data>)`. It accepts one JSON object with:

- `current_time`: string beginning `YYYY-MM-DD`
- `account`: object with `tier`, `opened_on`, `current_credit_limit`, `current_balance`, and explicit boolean `past_due`
- `requested_increase_amount`: positive whole-dollar number
- `prior_requests`: list of preexisting objects with `submitted_at` and `status`; exclude the request just submitted
- `has_active_disputes`: boolean
- `has_pending_replacement`: boolean
- `payment_history`: object containing integer `consecutive_on_time_months`

It emits JSON containing `recommendation` (`approve`, `deny`, `do_not_submit`, or `incomplete`), individual `checks`, calculated limits, and an allowed `denial_reason` when applicable. Do not treat an `incomplete` result as a decision.
