---
name: credit-limit-increase-processing
description: Process a credit-card credit-limit-increase (CLI) request using the required tier limits, submission-before-eligibility workflow, internal eligibility lookups, and the final approve or deny banking action. Use for a customer who requests a CLI.
---

# Credit-limit increase processing

## Scope and required inputs

Use this Skill for a credit-card CLI request. Obtain or look up:

- the authenticated/identified customer's `user_id` and target `credit_card_account_id`;
- current credit limit, balance, open date, account status, and past-due amount;
- the card's CLI tier (`entry`, `mid`, or `premium`) from account data or the bank's approved product-tier mapping;
- an exact requested **dollar increase** and the customer's reason; and
- the current date/time.

Do not guess an account, tier, requested amount, or tool result. If a customer expresses the request only as a percentage, calculate the dollar amount from the current limit. Because the submission tool accepts an integer dollar amount, ask the customer to choose an exact whole-dollar amount if the percentage calculation is not a whole number or if the amount is otherwise ambiguous. Do not apply an undocumented rounding rule.

The customer must have a valid amount within the tier maximum before any CLI request is submitted. If it exceeds the maximum, tell the customer the maximum permitted dollar increase and ask whether they want to submit that amount instead. Do not submit or deny an over-limit amount until they provide a valid adjusted request.

## Tier rules

| Tier | Minimum account age | Cooldown after an approved CLI | Utilization requirement | Consecutive on-time payment months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry | 120 days | 120 days | below 70% | 6 | 25% of current limit |
| Mid | 90 days | 90 days | below 80% | 3 | 50% of current limit |
| Premium | 60 days | 60 days | below 90% | 3 | 50% of current limit |

The age and cooldown thresholds are inclusive once the stated number of full days has elapsed. Utilization must be strictly below its threshold. Cooldown applies to an approved prior request; a denied request alone does not create a cooldown.

Use `scripts/evaluate_cli.py` to consistently calculate the requested amount, tier maximum, account age, utilization, cooldown, and a decision from completed lookup results. It never makes bank changes and cannot replace the required live banking-tool checks.

## Required live workflow

Follow this order exactly.

1. **Locate and inspect the account.** Use the supplied user/account lookup tools to resolve the user and account, and obtain the current limit, balance, open date, account status, and past-due amount. Obtain the current time with `get_current_time`. Resolve the CLI tier from authoritative account/product information. Confirm the request is for the account owner or authorized account manager under the applicable authentication process.

2. **Normalize and validate the requested amount.** Convert a clear percentage request to a dollar increase using the current limit, or use the customer's stated dollar increase. Compare it with the tier maximum. If it is not a positive whole-dollar amount or it exceeds the maximum, explain the issue and obtain a valid amount; stop here without calling any submit, approval, or denial CLI tool.

3. **Submit the valid request first.** Unlock and call `submit_credit_limit_increase_request_7392` with:
   - `credit_card_account_id`
   - `user_id`
   - `requested_increase_amount` (the valid integer dollar increase)

   Record that submission succeeded. Eligibility checks are internal, but the formal request must exist before those checks. A reason can be retained in the case notes or customer communication when supported; it is not an argument of this submission tool.

4. **Perform every eligibility check after submission, even if one fails.** Unlock each named discoverable tool before calling it.
   - Account age: calculate from the account open date and current date.
   - Cooldown: unlock/call `get_credit_limit_increase_history_4829` with `credit_card_account_id`. Review the prior request history and identify whether an **approved** request falls within the tier's cooldown window.
   - Disputes: unlock/call `get_user_dispute_history_7291` with `user_id`. Treat an active/non-final dispute (for example, `open` or `under_review`) as a pending dispute. Closed disputes do not by themselves fail this check.
   - Replacement cards: unlock/call `get_pending_replacement_orders_5765` with `credit_card_account_id`. Treat any order not clearly `delivered` or `cancelled` as pending.
   - Good standing: confirm the account is current and has no past-due balance.
   - Utilization: calculate `current_balance / current_credit_limit * 100` and compare strictly against the tier threshold.
   - Payment history: unlock/call `get_payment_history_6183` with `credit_card_account_id` and the tier's required month count. Confirm every required consecutive month is on time.

   Do not rely on a customer's statement in place of these internal checks. If a lookup is unavailable, malformed, or cannot establish the condition, do not approve; resolve the data issue through the normal support path.

5. **Process the decision.** If all checks pass, unlock/call `approve_credit_limit_increase_5847` with `credit_card_account_id`, `user_id`, and `new_credit_limit`, where `new_credit_limit = current_credit_limit + requested_increase_amount`.

   If any check fails, unlock/call `deny_credit_limit_increase_5848` using one allowed reason:
   - age → `insufficient_account_age`
   - approved request in cooldown → `cooldown_period_active`
   - active dispute → `pending_disputes`
   - pending replacement → `pending_replacement_card`
   - not current or any past-due balance → `past_due_balance`
   - utilization at/above threshold → `high_utilization`
   - missing required consecutive on-time payments → `insufficient_payment_history`

   `requested_amount_exceeds_limit` applies only to a request that somehow reached decision processing despite the required pre-submission validation. If results are inconclusive, use the normal exception process rather than inventing eligibility facts; use `other` only when no listed reason accurately represents the documented failure.

6. **Communicate clearly.** For an approval, confirm the increase and new total credit limit. For a denial, explain the applicable reason without exposing internal-only details unnecessarily. For cooldown, state the earliest date based on the last approved request date plus the tier cooldown when the history provides a definite date. If a customer seeks a larger increase than allowed, state the permitted maximum and request confirmation of that amount before submission.

## Evaluator script

`evaluate_cli.py` reads one JSON object from standard input and emits JSON to standard output. It is a deterministic aid for data that has already been obtained. Required keys are `tier`, `current_limit`, `current_balance`, `account_open_date`, `now`, `account_current`, `past_due_amount`, `has_active_disputes`, `has_pending_replacement`, and `payment_history_on_time`. Provide exactly one of `requested_increase_amount` or `requested_percent`; provide `prior_approved_request_dates` as an array of ISO dates (or an empty array).

Example runnable invocation (replace values with the current request's verified data):

```sh
printf '%s' '{"tier":"entry","current_limit":"4000","current_balance":"1500","account_open_date":"2023-05-10","now":"2025-11-14","requested_percent":"10","prior_approved_request_dates":[],"account_current":true,"past_due_amount":"0","has_active_disputes":false,"has_pending_replacement":false,"payment_history_on_time":true}' | python3 scripts/evaluate_cli.py
```

Validate the output before using it: `amount_status` must be `valid`, `decision` must be `approve` before approval is considered, and `failed_checks` must agree with the live tool results. The script reports a conservative `manual_review_required` decision for absent or invalid required data; it does not authorize an action.
