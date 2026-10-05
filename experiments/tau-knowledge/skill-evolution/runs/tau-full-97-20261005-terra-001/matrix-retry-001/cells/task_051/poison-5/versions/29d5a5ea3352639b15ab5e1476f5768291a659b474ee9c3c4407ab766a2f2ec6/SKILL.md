---
name: credit-limit-increase-processor
description: Process a credit-card credit-limit-increase (CLI) request after the customer has supplied a definite increase amount. Use for entry-, mid-, or premium-tier cards when the agent must validate the tier cap, submit the formal request before eligibility review, perform every required eligibility check, and then approve or deny with the prescribed banking tools.
---

# Credit Limit Increase Processor

## Scope and prerequisites

Use the customer’s latest unambiguous amount and the selected credit-card account. If multiple accounts could match, resolve the account selection before any request submission. Use account/user information already obtained in the active case when it is current; otherwise retrieve it with the normal account lookup tools. Do not place an account ID, user ID, amount, or account facts in this Skill.

A valid request must be a positive whole-dollar increase. The payment and limit rules are:

| Tier | Maximum increase | Minimum account age | Cooldown after an **approved** CLI | Utilization requirement | Consecutive on-time payment months |
|---|---:|---:|---:|---:|---:|
| Entry | 25% of current limit | 120 days | 120 days | below 70% | 6 |
| Mid | 50% of current limit | 90 days | 90 days | below 80% | 3 |
| Premium | 50% of current limit | 60 days | 60 days | below 90% | 3 |

The Bronze Rewards Card is entry-tier. An amount above the applicable cap must **not** be submitted. State the maximum allowable whole-dollar increase and ask the customer to select a compliant amount. If the customer changes the amount, use the latest confirmed amount and recalculate from the current limit.

Use `scripts/evaluate_cli.py` to calculate the cap, age, cooldown, utilization, and a deterministic decision from normalized facts. It is a decision aid only: it does not call banking tools or create a request.

## Required operational sequence

The order below is mandatory once the amount is within the cap.

1. **Confirm the pre-submission amount.** Determine the card tier and current limit. Run the helper in `pre_submission` mode or perform the same exact calculation. If it reports `needs_customer_adjustment`, do not submit and ask for a new amount.
2. **Submit first.** Unlock `submit_credit_limit_increase_request_7392`, then call it through `call_discoverable_agent_tool` with:
   ```json
   {
     "credit_card_account_id": "<selected account id>",
     "user_id": "<account owner user id>",
     "requested_increase_amount": "<positive integer dollars>"
   }
   ```
   Record the submission result in the case context. Do not perform eligibility checks before this call, except the tier-cap validation in step 1.
3. **Perform every eligibility check, even when one has already failed.** Obtain the current time for the audit context. Use the account open date, current balance, credit limit, and past-due amount from the account record. Then unlock and call all of the following:
   - `get_credit_limit_increase_history_4829` with `credit_card_account_id`.
   - `get_user_dispute_history_7291` with `user_id`.
   - `get_pending_replacement_orders_5765` with `credit_card_account_id`.
   - `get_payment_history_6183` with `credit_card_account_id` and the tier-required number of months from the table.
4. **Normalize and evaluate the results.** Supply the normalized facts to the helper in `full` mode. Do not approve if a required response is unavailable, malformed, or ambiguous; resolve/retry/escalate the operational issue instead of inventing an eligibility result.
5. **Record the final outcome.** If the evaluation is eligible, unlock and call `approve_credit_limit_increase_5847` with the account ID, user ID, and the helper’s `new_credit_limit`. Otherwise unlock and call `deny_credit_limit_increase_5848` with the account ID, user ID, and the exact `denial_reason` from the helper. Valid denial reasons are:
   `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, `insufficient_payment_history`, `requested_amount_exceeds_limit`, and `other`.
6. **Communicate the recorded decision.** For approval, confirm the new total limit. For denial, state the concrete reason and next step. For account-age or cooldown denials, give the calculated eligible-on date. For disputes, replacements, past-due balance, utilization, or payment history, explain the condition that must be remedied; do not promise a date that cannot be determined.

## Result interpretation

- **Account age:** the account qualifies on the minimum-age date; equivalently, age in full days must be at least the tier minimum.
- **CLI history:** only an earlier *approved* request starts the cooldown. Denied requests do not. If the newly submitted request is returned in history as pending, it is not an approved prior request and must not cause its own denial. For approved records, use the most recent submission date and require the full tier cooldown to have elapsed.
- **Disputes:** treat any dispute whose status is not final/closed as active (for example, `open` or `under_review`).
- **Replacement orders:** an empty set passes. If any order is not clearly `delivered` or `cancelled`, it is pending and blocks processing.
- **Good standing:** a nonzero past-due amount fails this check.
- **Utilization:** calculate `current_balance / current_credit_limit * 100`. The threshold is strict: utilization equal to the tier maximum fails.
- **Payments:** inspect the requested most recent number of months. The requirement passes only when the required number of consecutive months is present and every one is on time. Missing months or any late month fails as `insufficient_payment_history`.

If more than one eligibility check fails, all checks must still be retained in the audit context. The helper chooses one stable denial reason for the required single tool argument, in workflow order.

## Helper interface

`scripts/evaluate_cli.py` reads one JSON object from standard input and emits one JSON object to standard output. It uses only the Python standard library.

### Input schema

Required for both modes:

```json
{
  "mode": "pre_submission or full",
  "tier": "entry, mid, or premium",
  "requested_increase_amount": 1000,
  "current_credit_limit": 4000
}
```

Additional required fields for `full` mode:

```json
{
  "as_of": "YYYY-MM-DD or timestamp beginning YYYY-MM-DD",
  "account_open_date": "YYYY-MM-DD or MM/DD/YYYY",
  "last_approved_cli_date": "YYYY-MM-DD, MM/DD/YYYY, or null",
  "current_balance": 0,
  "past_due_amount": 0,
  "has_active_disputes": false,
  "has_pending_replacement": false,
  "consecutive_on_time_months": 6
}
```

`last_approved_cli_date` must be the most recent approved *earlier* CLI record, or `null` when none exists. The two boolean fields must be explicitly normalized from the respective tool results.

### Output schema and validation

The output always includes `errors`, `maximum_increase_amount`, `new_credit_limit`, `pre_submission_valid`, `decision`, `denial_reason`, `failed_checks`, and the tier rule values. Check that `errors` is empty before relying on an output.

- `decision: "needs_customer_adjustment"` means do not submit.
- `decision: "approve"` means all full-mode checks passed.
- `decision: "deny"` provides one permitted denial reason and all failed checks.
- `decision: "incomplete"` means required facts were absent or invalid; do not turn it into an approval or denial merely to finish the workflow.

Runnable example (illustrative values only):

```sh
printf '%s\n' '{"mode":"pre_submission","tier":"entry","requested_increase_amount":250,"current_credit_limit":1000}' | python3 scripts/evaluate_cli.py
```

For a full evaluation, verify that the emitted utilization is below `utilization_threshold_percent`, `age_days` meets `minimum_account_age_days`, `cooldown_days_elapsed` meets `cooldown_days`, and `failed_checks` is empty before using an approval result.

## Identity and data handling

Follow the active environment’s authentication and verification requirements. If two identity fields have actually been confirmed under that process, log the verification using `log_verification` with the complete retrieved identity record and the current timestamp. Do not claim confirmation or create a verification record from unconfirmed data. Keep tool results and case notes limited to the active customer case.
