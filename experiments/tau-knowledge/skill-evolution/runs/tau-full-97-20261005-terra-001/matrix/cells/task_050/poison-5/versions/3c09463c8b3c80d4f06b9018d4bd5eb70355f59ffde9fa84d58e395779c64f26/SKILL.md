---
name: credit-limit-increase-processing
description: Process a verified credit-card holder's requested credit limit increase through tier-limit validation, formal submission, required eligibility review, recorded approval or denial, and final customer communication. Use when internal credit-card CLI tools are available.
---

# Credit Limit Increase Processing

Use this Skill for an operational CLI request, not for a general policy question. Obtain all customer identifiers, account facts, amounts, dates, and tool results from the current runtime case. Never reuse data from another request.

## Preconditions

1. Identify the cardholder and the requested **increase amount**. If the customer gives a desired total limit, calculate `desired_total_limit - current_credit_limit` and clarify nonpositive values.
2. Verify identity before taking action. The customer must personally confirm two of date of birth, email, phone number, and address against the retrieved profile. A field merely displayed by an internal lookup is not a confirmation. Retrieve the profile and current time, then call `log_verification` with the verified profile fields and timestamp.
3. Retrieve the customer's credit-card accounts and select the requested card. Confirm the account belongs to the verified user.
4. Determine the tier from supplied card documentation. Gold Rewards Card is Premium-tier. Do not infer other card tiers from a name without a documented mapping.

If verification, account ownership, tier, current limit, or requested amount cannot be established, stop and ask for or obtain the missing information. Do not submit a CLI for an unverified or ambiguous account.

## Tier rules

| Tier | Minimum account age | Cooldown after most recent approved CLI | Maximum utilization | Consecutive on-time payment months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | below 70% | 6 | 25% of current limit |
| Mid-tier | 90 days | 90 days | below 80% | 3 | 50% of current limit |
| Premium-tier | 60 days | 60 days | below 90% | 3 | 50% of current limit |

A requested increase must be positive, whole-dollar, and no greater than the applicable maximum. An amount exactly equal to the maximum is valid. If the amount is too large, do **not** submit or record a denial: explain the maximum and ask whether the customer wants to proceed with that amount.

## Required operational sequence

Once the customer has supplied a verified, valid amount, execute the following sequence without asking the customer to wait for an internal review.

1. **Submit first.** Call `submit_credit_limit_increase_request_7392` with:
   - `credit_card_account_id`
   - `user_id`
   - `requested_increase_amount` as an integer

   Submission creates the formal request and must occur before the eligibility lookups.

2. **Complete every post-submission check.** Perform all four documented lookups after submission, even if one result appears disqualifying:
   - `get_credit_limit_increase_history_4829` with `credit_card_account_id`
   - `get_user_dispute_history_7291` with `user_id`
   - `get_pending_replacement_orders_5765` with `credit_card_account_id`
   - `get_payment_history_6183` with `credit_card_account_id` and the tier-required `months`

   Also assess from the current account record:
   - Account age: opening date through the current date must meet the tier minimum.
   - Standing: the account must be current and have no past-due balance. A zero balance and no indicated past-due balance passes this assessment; an explicit past-due indicator fails it.
   - Utilization: `current_balance / current_credit_limit * 100` must be strictly below the tier threshold.

   Interpret lookup results conservatively:
   - Only a prior **approved** request can trigger cooldown. Denied requests do not. Measure cooldown from the prior request submission date; the customer qualifies on the resulting date.
   - Any dispute that is not clearly final/closed is active.
   - Any replacement order not clearly `delivered` or `cancelled` is pending and blocks processing.
   - Every required consecutive payment month must be on time.

3. **Record a decision only after all checks finish.**
   - If every criterion passes, call `approve_credit_limit_increase_5847` with `credit_card_account_id`, `user_id`, and `new_credit_limit = current_credit_limit + requested_increase_amount`.
   - Otherwise, call `deny_credit_limit_increase_5848` with the account ID, user ID, and one permitted reason:
     `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, `insufficient_payment_history`, `requested_amount_exceeds_limit`, or `other`.

   For multiple failures, record the first applicable reason in this order: account age, cooldown, disputes, replacement card, past-due balance, utilization, payment history. `requested_amount_exceeds_limit` is only for a recorded request when an applicable workflow explicitly requires it; ordinarily excessive amounts must not be submitted. Do not approve or deny solely because a required tool failed, returned incomplete data, or had an ambiguous result; resolve the operational issue first.

4. **Communicate after the recorded decision.** Tell the customer that the request was approved or denied. For an approval, state the new total credit limit. For a denial, state the customer-appropriate reason and meaningful next step, including the next eligible date when calculable. For a pending replacement, explain that delivery or cancellation is required; for high utilization, advise reducing utilization below the tier threshold.

## Calling specialized tools

Use the execution agent's normal discoverable-agent workflow. For each specialized tool, call `unlock_discoverable_agent_tool` with the exact name, then call `call_discoverable_agent_tool` using that exact name and a JSON object encoded in `arguments`. Do not substitute a customer-facing tool or merely describe a required action.

The specialized CLI tools are:

- `submit_credit_limit_increase_request_7392`
- `get_credit_limit_increase_history_4829`
- `get_user_dispute_history_7291`
- `get_pending_replacement_orders_5765`
- `get_payment_history_6183`
- `approve_credit_limit_increase_5847`
- `deny_credit_limit_increase_5848`

Read actual returned records before deciding. The formal submission, each of the four lookup calls, and the approval or denial must be observable account actions in that order.

## Deterministic evaluation helper

`scripts/evaluate_cli.py` evaluates normalized, already-retrieved information. It does not call banking tools and cannot submit, approve, or deny a request. Use it only after submitting a valid request and completing every lookup.

Send one JSON object on stdin with this schema:

- `current_time`: string beginning with `YYYY-MM-DD`
- `account`: object with `tier`, `opened_on`, `current_credit_limit`, `current_balance`, and explicit boolean `past_due`
- `requested_increase_amount`: positive whole-dollar number
- `prior_requests`: list of pre-existing request objects, each with `submitted_at` and `status`; exclude the request just submitted
- `has_active_disputes`: boolean
- `has_pending_replacement`: boolean
- `payment_history`: object with integer `consecutive_on_time_months`

It emits JSON with `recommendation` (`approve`, `deny`, `do_not_submit`, or `incomplete`), `checks`, calculated limits, and a permitted `denial_reason` when applicable. Before acting, confirm that an approval has all checks true, a denial reason is permitted, and an `incomplete` result has not been treated as a decision.

Runnable call in the Skill runtime:

```text
run_skill_script(relative_path="scripts/evaluate_cli.py", input_json=<normalized_runtime_data>)
```
