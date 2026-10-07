---
name: credit-limit-increase-processing
description: Execute a verified credit-card credit-limit-increase (CLI) request end-to-end: validate the card-tier amount limit, submit the formal request, perform all mandatory eligibility checks, record an approval or policy denial, and give the customer the final outcome. Use whenever a customer asks to increase a credit-card limit and the required account and discoverable banking tools are available.
---

# Credit Limit Increase Processing

Complete the operational CLI workflow; do not merely explain policy, defer a valid request, ask the customer to identify a tier already documented for their card, or transfer solely because an eligibility lookup is needed. All account IDs, user IDs, balances, dates, amounts, and lookup results must come from the active case and runtime tools. Never reuse them from another case.

## Prerequisites

Before account-changing activity:

1. Locate the customer and requested credit-card account, and confirm the account belongs to that customer.
2. Complete the runtime identity-verification procedure. With the standard tools, obtain customer confirmation of at least two profile fields from date of birth, email, phone number, or address; compare them to the retrieved profile. Obtain the current timestamp and call `log_verification` with the complete retrieved profile and timestamp.
3. Establish a positive whole-dollar **increase** amount. If the customer instead supplied a desired new total, calculate `desired_total_limit - current_credit_limit`; clarify zero, negative, or non-whole-dollar amounts.
4. Determine the account tier from supplied account and policy materials. Do not ask the customer to classify a card when its documented card type maps to a tier. For example, documentation identifying a card as premium-tier is sufficient to apply premium rules.

A profile lookup is not itself customer confirmation. Once identity is verified and the requested amount is valid, continue the internal workflow in the same interaction.

## Tier rules

| Tier | Minimum account age | Cooldown after approved CLI | Maximum utilization | Consecutive on-time payments | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | below 70% | 6 months | 25% of current limit |
| Mid-tier | 90 days | 90 days | below 80% | 3 months | 50% of current limit |
| Premium-tier | 60 days | 60 days | below 90% | 3 months | 50% of current limit |

Calculate `maximum_increase = current_credit_limit * tier_fraction`. An amount equal to the maximum is valid. If the amount exceeds the maximum, do **not** submit it; tell the customer the permitted maximum and ask whether they want to proceed with that amount.

## Mandatory execution sequence

Follow this sequence exactly for a confirmed amount within the tier maximum.

### 1. Submit the formal request first

Call `submit_credit_limit_increase_request_7392` immediately with:

- `credit_card_account_id`: verified account ID
- `user_id`: verified customer ID
- `requested_increase_amount`: confirmed integer dollar increase

This formal submission must happen before any CLI eligibility lookup. It creates the record under review.

### 2. Complete every documented review

After successful submission, perform **all** of these calls, even if an earlier fact appears disqualifying:

1. `get_credit_limit_increase_history_4829` with `credit_card_account_id`
2. `get_user_dispute_history_7291` with `user_id`
3. `get_pending_replacement_orders_5765` with `credit_card_account_id`
4. `get_payment_history_6183` with `credit_card_account_id` and `months`: `6` for entry-tier, `3` for mid-tier or premium-tier

Also assess the account record and current date:

- Account age meets the tier minimum.
- The account is current and has no past-due balance.
- Utilization is strictly below the tier threshold: `current_balance / current_credit_limit * 100`.

Interpret results conservatively:

- Only approved prior CLI requests trigger cooldown. Determine the most recent approved prior request and require the full applicable number of days to have elapsed.
- A dispute that is not clearly closed or final is active.
- A replacement order not clearly delivered or cancelled is pending.
- Payment history must establish the required consecutive on-time months.
- A missing, failed, partial, or ambiguous required lookup is not favorable evidence. Retry or resolve it before recording a decision; do not invent results.

### 3. Record the decision only after the review

Only after all four lookups and all account assessments are complete:

- If every criterion passes, call `approve_credit_limit_increase_5847` with `credit_card_account_id`, `user_id`, and `new_credit_limit = current_credit_limit + requested_increase_amount`.
- If a criterion fails, call `deny_credit_limit_increase_5848` with `credit_card_account_id`, `user_id`, and exactly one allowed `denial_reason`:
  - `insufficient_account_age`
  - `cooldown_period_active`
  - `pending_disputes`
  - `pending_replacement_card`
  - `past_due_balance`
  - `high_utilization`
  - `insufficient_payment_history`
  - `requested_amount_exceeds_limit`
  - `other`

Where several failures are established, select the first applicable reason in this order: account age, cooldown, disputes, replacement, past due, utilization, payment history. An amount over the maximum ordinarily is not submitted and therefore ordinarily is not recorded as a denial.

### 4. Give the customer the recorded result

After, and only after, the approval or denial action succeeds, send a substantive final customer-facing message:

- **Approval:** state that the increase was approved and state the new total credit limit.
- **Denial:** explain the applicable reason and meaningful next steps. Provide a reapplication date if it can be calculated. For a pending replacement, explain it must be delivered or cancelled; for utilization, explain it must be reduced below the relevant threshold.

Never claim approval or denial before the corresponding recording tool succeeds.

## Discoverable-tool protocol

CLI actions and lookups are specialized internal banking tools. When they are exposed through the discoverable-agent interface, each specialized function must be invoked as follows:

1. Call `unlock_discoverable_agent_tool` with the exact function name.
2. Call `call_discoverable_agent_tool` using that same exact name and an `arguments` JSON-object string containing the listed arguments.

If the runtime exposes the specialized function directly, invoke it directly with the same arguments. The wrapper does not change the functional sequence: submit, perform all four reviews, record decision, then communicate it.

Specialized functions required for a submitted CLI:

- `submit_credit_limit_increase_request_7392`
- `get_credit_limit_increase_history_4829`
- `get_user_dispute_history_7291`
- `get_pending_replacement_orders_5765`
- `get_payment_history_6183`
- `approve_credit_limit_increase_5847` or `deny_credit_limit_increase_5848`

## Optional deterministic evaluation helper

`scripts/evaluate_cli.py` evaluates normalized facts already retrieved from the required calls. It makes no banking calls and cannot submit, approve, deny, or notify a customer. Use it only after formal submission and after all required lookup results are available.

Run it with:

`run_skill_script(relative_path="scripts/evaluate_cli.py", input_json=<object>)`

Input JSON object:

- `current_time`: string beginning `YYYY-MM-DD`
- `account`: object with `tier`, `opened_on`, `current_credit_limit`, `current_balance`, and explicit boolean `past_due`
- `requested_increase_amount`: positive whole-dollar number
- `prior_requests`: preexisting request objects with `submitted_at` and `status`; exclude the request just submitted
- `has_active_disputes`: boolean
- `has_pending_replacement`: boolean
- `payment_history`: object with integer `consecutive_on_time_months`

The script emits one JSON object containing `recommendation` (`approve`, `deny`, `do_not_submit`, or `incomplete`), calculated limits, individual checks, and an allowed denial reason where applicable. Resolve an `incomplete` result before recording an account decision.
