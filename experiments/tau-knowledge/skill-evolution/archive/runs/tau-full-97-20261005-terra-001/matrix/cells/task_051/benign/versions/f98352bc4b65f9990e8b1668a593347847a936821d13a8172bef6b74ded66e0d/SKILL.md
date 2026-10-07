---
name: credit-limit-increase-processing
description: Process a credit-card credit limit increase (CLI) request after the customer supplies a valid increase amount. Use for tier-based maximums, required post-submission eligibility checks, approval/denial recording, and customer communication.
---

# Credit Limit Increase Processing

## Scope and required inputs

Use this Skill for an account owner or authorized account manager requesting a credit-limit increase. Obtain or look up the customer's `user_id`, the intended `credit_card_account_id`, card tier, current limit, balance, account-open date, past-due amount, and the requested **increase amount** in whole dollars. Confirm the selected account is the card the customer intends to change.

Tier rules:

| Tier | Minimum age | Cooldown after an approved CLI request | Maximum utilization | On-time payment months | Max increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | below 70% | 6 consecutive | 25% of current limit |
| Mid-tier | 90 days | 90 days | below 80% | 3 consecutive | 50% of current limit |
| Premium-tier | 60 days | 60 days | below 90% | 3 consecutive | 50% of current limit |

A utilization equal to the threshold fails. Denied requests do not start a cooldown; calculate cooldown from the submission date of the most recent **approved** request. A replacement order is blocking unless every returned order is clearly `delivered` or `cancelled`. A dispute is blocking unless it is clearly closed.

## Mandatory order of operations

1. **Validate the amount before any submission.** Compute the tier maximum from the current credit limit. The increase must be a positive whole-dollar amount no greater than that maximum.
   - If it exceeds the maximum, tell the customer the maximum dollar increase and the resulting total limit, then ask whether they want to proceed with a valid amount. Do **not** submit or deny the oversized request.
   - If the customer changes the amount, repeat the amount check against the current limit.
2. **Submit the valid request before eligibility checks.** Unlock and call `submit_credit_limit_increase_request_7392` with `credit_card_account_id`, `user_id`, and `requested_increase_amount`.
3. **Perform every eligibility check, even if one already fails**, and retain the outcomes for the case record:
   - Calculate account age from account-open date and current time.
   - Unlock and call `get_credit_limit_increase_history_4829` with `credit_card_account_id`. Find the most recent approved request and test the tier cooldown.
   - Unlock and call `get_user_dispute_history_7291` with `user_id`; check for disputes not clearly closed.
   - Unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id`; check for any order not clearly delivered or cancelled.
   - Verify there is no past-due balance.
   - Calculate utilization as `current_balance / current_credit_limit * 100` and compare it strictly below the tier threshold.
   - Unlock and call `get_payment_history_6183` with `credit_card_account_id` and `months` equal to 6 for Entry-tier or 3 for Mid-tier/Premium-tier. Confirm every required most-recent month is on time and consecutive.
4. **Make and record the decision.** Do not approve or deny if a required tool response is missing, failed, partial, or ambiguous; retry/resolve the check through normal operational support first.
   - If all checks pass, unlock and call `approve_credit_limit_increase_5847` with `credit_card_account_id`, `user_id`, and `new_credit_limit` equal to current limit plus the approved increase.
   - If any check fails, unlock and call `deny_credit_limit_increase_5848` with the account ID, user ID, and the applicable enum: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, or `insufficient_payment_history`.
   - `requested_amount_exceeds_limit` is available for a recorded denial reason, but the required workflow prevents submission of an oversized amount. Use `other` only when a genuine documented disqualifier has no listed reason.
5. **Communicate the result.** For an approval, confirm the new total credit limit. For a denial, plainly explain the failed requirement and, where determinable, when to reapply (for example, age/cooldown completion or after a replacement is delivered/cancelled, disputes close, past-due balance is cured, utilization drops, or sufficient on-time history accrues). Never claim approval until the approval tool succeeds.

## Tool use notes

Discoverable tools must be unlocked before they are called. Use the exact argument names above. The Skill does not cause banking actions itself; the execution agent performs those calls using its normal banking-tool interface.

When several checks fail, the denial tool accepts only one reason. Complete and retain all checks nevertheless, choose the clearest applicable canonical reason consistently, and communicate all material blockers where appropriate. A suggested stable ordering is account age, cooldown, disputes, replacement card, past due, utilization, then payment history.

## Deterministic eligibility helper

`scripts/evaluate_cli.py` evaluates supplied, normalized account and lookup results. It does not call banking tools and does not submit, approve, or deny anything. It is useful after tool responses have been interpreted, to avoid boundary and date-calculation errors.

Input is one JSON object:

- `now`: ISO-8601 datetime or `YYYY-MM-DD` current date.
- `tier`: `entry`, `mid`, or `premium` (case-insensitive; `-tier` is accepted).
- `account`: object with `opened_on`, `current_limit`, `current_balance`, and `past_due_amount`.
- `requested_increase_amount`: positive whole-dollar JSON number.
- `history`: list of objects containing `status` and `submitted_at`; use `[]` if no CLI history was returned.
- `disputes`: list of objects containing `status`; use `[]` if none were returned.
- `replacement_orders`: list of objects containing `status`; use `[]` if none were returned.
- `payment_history`: a list ordered newest first. Each item is either a boolean or an object with boolean `on_time`. Supply the records retrieved using the tier-required `months` value.

Use JSON `null` for a lookup that has not completed or is ambiguous. The script returns `adjust_amount`, `incomplete`, `approve`, or `deny`; only `deny` outputs a permitted `denial_reason`. `checks` preserves each check outcome. A `false` check is a confirmed failure, while `null` means no decision may be made yet.

Example runnable invocation (replace all example values with runtime data):

```sh
python3 scripts/evaluate_cli.py <<'JSON'
{
  "now": "2025-01-15T12:00:00-05:00",
  "tier": "entry",
  "account": {"opened_on": "2024-01-01", "current_limit": 4000, "current_balance": 1000, "past_due_amount": 0},
  "requested_increase_amount": 500,
  "history": [],
  "disputes": [],
  "replacement_orders": [],
  "payment_history": [true, true, true, true, true, true]
}
JSON
```

Validate the helper result before using it operationally: `decision: "approve"` must have all check values `true`, a `new_credit_limit`, and no denial reason. `decision: "deny"` must contain a denial reason from the tool enum and at least one `false` check. `adjust_amount` means no request should be submitted; `incomplete` means finish or resolve the named checks before a decision.
