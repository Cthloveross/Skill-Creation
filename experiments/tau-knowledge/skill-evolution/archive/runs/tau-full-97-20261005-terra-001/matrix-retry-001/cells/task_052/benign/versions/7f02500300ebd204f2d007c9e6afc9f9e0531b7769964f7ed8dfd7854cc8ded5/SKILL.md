---
name: credit-limit-increase-processing
description: Process a credit-card credit limit increase (CLI) request when an authenticated customer, account record, card tier, requested increase, and the CLI decision tools are available. Use this skill to validate the tier maximum before submission, submit a valid request, complete every required eligibility check, and approve or deny it with the required audit action.
---

# Credit Limit Increase Processing

## Scope and prerequisites

Use this workflow only for the account owner or an authorized account manager. Before any state-changing CLI tool call, comply with the runtime identity-verification requirement: obtain confirmation of at least two of date of birth, email, phone number, and address; retrieve the authoritative user record; obtain the current time; and call `log_verification` with the complete returned record and verification timestamp. A name is useful for lookup but is not one of the two required identity fields. If a valid verification is already recorded for the active interaction, do not duplicate it.

Identify the intended credit-card account and its authoritative card tier. Do not infer a tier merely from a product name unless an authoritative account field or applicable policy explicitly maps that product to a tier. If the tier, account, requested amount, current limit, or authorization cannot be established, ask for the missing information and do not submit or decide the request.

Tier rules:

| Tier | Minimum age | Cooldown after an approved request | Utilization requirement | Consecutive on-time payment months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | below 70% | 6 | 25% of current limit |
| Mid-tier | 90 days | 90 days | below 80% | 3 | 50% of current limit |
| Premium-tier | 60 days | 60 days | below 90% | 3 | 50% of current limit |

Interpret an unambiguous percentage request against the current credit limit. The submission tool requires an integer dollar increase. If the resulting amount is not an exact whole dollar, obtain a whole-dollar requested amount before proceeding. Calculate utilization as `current_balance / current_credit_limit * 100`; the threshold is strict, so equality fails.

## Required order of operations

1. **Validate the requested amount before submission.** Calculate the tier maximum from the current limit. If the requested increase exceeds it, do **not** submit, approve, or deny a CLI request. Tell the customer the maximum dollar increase and ask whether they want to request that amount or another valid amount. This is an adjustment request, not a recorded denial.
2. **Submit a valid request before eligibility checks.** Unlock and call `submit_credit_limit_increase_request_7392` with `credit_card_account_id`, `user_id`, and integer `requested_increase_amount`.
3. **Complete every eligibility check, even if one already fails.** Unlock each needed tool before calling it. Check:
   - Account age from the account-open date and current date.
   - CLI history using `get_credit_limit_increase_history_4829` with `credit_card_account_id`. Identify the most recent **approved** request and compare its submission date to the tier cooldown. Denied requests do not start a cooldown. A newly submitted pending request is not an approved prior request.
   - Disputes using `get_user_dispute_history_7291` with `user_id`. Any active/non-final dispute fails this check; a closed dispute does not.
   - Replacement orders using `get_pending_replacement_orders_5765` with `credit_card_account_id`. Any order not clearly `delivered` or `cancelled` is blocking.
   - Good standing from the authoritative account data. A past-due balance greater than zero fails this check.
   - Current utilization from authoritative balance and limit.
   - Payment history using `get_payment_history_6183` with `credit_card_account_id` and the tier's required month count. Confirm the required consecutive months are all on time.
4. **Record exactly one final decision after all checks are known.**
   - If every check passes, unlock and call `approve_credit_limit_increase_5847` with `credit_card_account_id`, `user_id`, and `new_credit_limit = current_credit_limit + requested_increase_amount` as a float.
   - If any check fails, unlock and call `deny_credit_limit_increase_5848` with the account ID, user ID, and the matching permitted denial reason: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, or `insufficient_payment_history`.

When several checks fail, still complete the audit checks and record one factual primary reason. Use this consistent workflow-order priority unless case policy supplies a required reason: account age, cooldown, disputes, replacement card, past due balance, utilization, then payment history. `requested_amount_exceeds_limit` is available in the denial API, but do not use it for a request exceeding the pre-submission maximum because the CLI workflow expressly prohibits submitting that request. Use `other` only when no listed reason truthfully describes an already submitted request.

## Interpreting failures and missing data

Do not substitute a customer's statement for the required history, dispute, replacement-order, or payment-history lookup. If a required tool response is missing, ambiguous, partial, or errors, do not approve and do not invent a denial reason. Explain that the review cannot be completed and use the normal technical-error escalation path if recovery is not possible. If a submit, approve, or deny action errors, do not state that it succeeded; report the unresolved status and escalate according to the runtime process.

For a cooldown denial, calculate the next eligible submission date as the most recent approved request submission date plus the tier cooldown days. Communicate that date. For other denials, explain the actual reason and the relevant next step (for example, reduce utilization, resolve a dispute/replacement, become current, or build the required on-time history). For approval, confirm the resulting total credit limit.

## Decision helper

`scripts/evaluate_cli.py` performs only deterministic calculation and eligibility assessment; it never calls banking tools or changes account data. Normalize authoritative lookup responses into the JSON schema below, then run:

```text
python scripts/evaluate_cli.py < normalized_cli.json
```

Input object fields:

- `tier`: `entry`, `mid`, or `premium` (aliases such as `entry-tier` are accepted).
- `current_limit`, `current_balance`, `past_due_amount`: numeric dollar values.
- Exactly one of `requested_increase_amount` (whole-dollar numeric value) or `requested_increase_percent` (for example, `10` for 10%).
- `current_date` and `account_open_date`: ISO dates/timestamps or `MM/DD/YYYY` dates.
- `last_approved_submission_date`: date or `null`; derive this only from the CLI-history response.
- `active_disputes`: boolean derived from the dispute lookup.
- `replacement_orders`: an array of order objects containing `status`, or an empty array.
- `consecutive_on_time_months`: integer derived from the payment-history lookup.
- Optional `checks_complete`: boolean. Set it to `false` until every required post-submission lookup has returned and been interpreted.

The script emits JSON with `pre_submit.may_submit`, calculations, each eligibility result, a decision, an allowed denial reason when applicable, and a cooldown eligibility date. If `may_submit` is false because the amount exceeds the maximum, ask the customer to adjust the request rather than calling a CLI mutation tool. If output is `needs_review`, obtain the missing authoritative check rather than making a decision. Before approving or denying, ensure a valid request was actually submitted and all post-submission checks have been executed.
