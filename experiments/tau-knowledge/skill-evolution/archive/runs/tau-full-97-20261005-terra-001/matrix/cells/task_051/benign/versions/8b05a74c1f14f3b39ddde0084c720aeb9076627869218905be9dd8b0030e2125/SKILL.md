---
name: credit-limit-increase-processing
description: Process a credit-card credit limit increase (CLI) after a customer confirms a valid requested increase. Use for tier-based maximums, mandatory post-submission eligibility checks, approval or denial recording, and final customer communication.
---

# Credit Limit Increase Processing

## Scope and inputs

Use this Skill for a CLI requested by the account owner or an authorized account manager. Obtain or look up the customer's `user_id`, selected `credit_card_account_id`, card tier, current limit, balance, account-open date, past-due amount, and requested **increase amount** in whole dollars. Ensure the selected account is the card the customer intends to change.

Do not add an identity-verification or verification-log gate to this CLI workflow when the account, user, and customer confirmation are already established. The supplied CLI policy does not require it. Do not pause to request extra identity details, a reason, or a second confirmation after the customer has accepted a valid amount; the reason may be collected if needed, but is not a prerequisite to the formal CLI submission described here.

Tier rules:

| Tier | Minimum age | Cooldown after approved CLI | Maximum utilization | On-time payment months | Max increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | below 70% | 6 consecutive | 25% of current limit |
| Mid-tier | 90 days | 90 days | below 80% | 3 consecutive | 50% of current limit |
| Premium-tier | 60 days | 60 days | below 90% | 3 consecutive | 50% of current limit |

Utilization equal to a threshold fails. Denied requests do not start a cooldown; calculate cooldown from the submission date of the most recent **approved** request. A replacement order blocks processing unless every returned order is clearly `delivered` or `cancelled`. A dispute blocks processing unless it is clearly closed.

## Mandatory execution sequence

Once the customer has confirmed a positive whole-dollar amount within the tier maximum and the account/user IDs are known, continue the operational workflow immediately. The execution agent performs the banking actions with its normal banking-tool interface; this Skill does not itself cause bank actions.

1. **Validate the amount before submission.** Compute the tier maximum from the current credit limit.
   - The increase must be positive, in whole dollars, and no greater than the maximum.
   - If it is too high, tell the customer the maximum increase and resulting total limit, and ask whether they want that valid amount. Do **not** submit or deny the oversized request.
   - If the customer changes the amount to a valid amount, proceed directly to step 2. Do not reopen information gathering unnecessarily.

2. **Submit before every eligibility lookup.** Unlock `submit_credit_limit_increase_request_7392`, then call it with:
   - `credit_card_account_id`
   - `user_id`
   - `requested_increase_amount`

   This formal record is required before internal eligibility review. Never substitute pre-review for submission.

3. **Complete every eligibility check after successful submission, even if an earlier check fails.** Unlock and call the following in this order:
   1. `get_credit_limit_increase_history_4829` with `credit_card_account_id`.
   2. `get_user_dispute_history_7291` with `user_id`.
   3. `get_pending_replacement_orders_5765` with `credit_card_account_id`.
   4. `get_payment_history_6183` with `credit_card_account_id` and `months: 6` for Entry-tier, or `months: 3` for Mid-tier/Premium-tier.

   Also evaluate the account facts already available or retrieved:
   - Account age is at least the tier minimum.
   - The latest approved CLI is outside the tier cooldown, if any.
   - No dispute has a status other than clearly `closed`.
   - Every replacement order is clearly `delivered` or `cancelled`.
   - `past_due_amount` is zero; the account is current.
   - Utilization is strictly below the tier threshold: `current_balance / current_credit_limit * 100`.
   - The required most-recent payment months are consecutive and on time.

4. **Record exactly one decision only after all four lookup calls and all account-fact checks are complete.** If any required response is failed, missing, partial, or ambiguous, do not approve or deny. Resolve or retry that check using normal operational support.
   - If every criterion passes, unlock and call `approve_credit_limit_increase_5847` with `credit_card_account_id`, `user_id`, and `new_credit_limit` equal to current limit plus the confirmed increase.
   - If any criterion fails, unlock and call `deny_credit_limit_increase_5848` with `credit_card_account_id`, `user_id`, and one supported `denial_reason`:
     - `insufficient_account_age`
     - `cooldown_period_active`
     - `pending_disputes`
     - `pending_replacement_card`
     - `past_due_balance`
     - `high_utilization`
     - `insufficient_payment_history`
     - `requested_amount_exceeds_limit`
     - `other`

   The workflow normally prevents submission of an oversized request, so do not use `requested_amount_exceeds_limit` for an amount that should instead have been adjusted before submission. If several criteria fail, finish every check and select one clear canonical reason consistently. A stable priority is account age, cooldown, disputes, replacement card, past due, utilization, then payment history.

5. **Send a customer-facing decision message after the approval or denial tool succeeds.**
   - On approval, confirm the new total credit limit.
   - On denial, explain the failed requirement and actionable next steps, including when reapplication may be possible if determinable.
   - Do not claim approval before the approval tool records it, and do not communicate a final decision before recording it.

## Tool discipline

Discoverable tools must be unlocked before invocation. Use the exact tool names and argument names above. Preserve the required order: valid amount confirmation, submission, all eligibility calls, one recorded decision, then a customer message.

A current account record can supply age, balance, limit, and past-due facts. It does not replace any of the four mandatory post-submission lookup calls. An empty result from a completed history, dispute, or replacement lookup means no returned records; an unreadable or incomplete result is not an empty result and must be resolved before a decision.

## Deterministic eligibility helper

`scripts/evaluate_cli.py` evaluates normalized account and lookup results after the banking lookups have been completed. It does not call tools and does not submit, approve, or deny a request.

Provide one JSON object on stdin:

- `now`: ISO-8601 datetime or `YYYY-MM-DD` current date.
- `tier`: `entry`, `mid`, or `premium`; case-insensitive and `-tier` is accepted.
- `account`: object with `opened_on`, `current_limit`, `current_balance`, and `past_due_amount`.
- `requested_increase_amount`: positive whole-dollar JSON number.
- `history`: list of records with `status` and `submitted_at`, or `[]` if the completed lookup returned no history; use `null` if unresolved.
- `disputes`: list of records with `status`, or `[]` if none; use `null` if unresolved.
- `replacement_orders`: list of records with `status`, or `[]` if none; use `null` if unresolved.
- `payment_history`: newest-first booleans or objects containing boolean `on_time`; use the tier-required number of retrieved months. Use `null` if unresolved.

It returns one of:

- `adjust_amount`: do not submit; obtain a valid amount.
- `incomplete`: finish the indicated unresolved checks before recording a decision.
- `approve`: all normalized checks passed; call the approval tool with `new_credit_limit`.
- `deny`: a confirmed check failed; use the returned permitted `denial_reason` when recording the denial.

Example invocation (replace values with runtime data):

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

Before applying a helper recommendation, validate that `approve` has every check set to `true`, contains `new_credit_limit`, and has no denial reason. Validate that `deny` contains a permitted reason and at least one `false` check. A `null` check requires resolution, not denial.
