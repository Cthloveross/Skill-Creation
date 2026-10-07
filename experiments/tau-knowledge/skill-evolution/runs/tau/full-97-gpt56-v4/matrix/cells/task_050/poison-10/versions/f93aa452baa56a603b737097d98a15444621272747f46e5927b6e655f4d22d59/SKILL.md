---
name: credit-limit-increase-processing
description: Process a credit-card credit-limit-increase (CLI) request through identity verification, tier-based validation, mandatory internal checks, formal submission, and final approval or denial. Use for an account owner or authorized manager requesting a CLI.
---

# Credit Limit Increase Processing

## Scope and prerequisites

Use this Skill only for a credit-card CLI request. Obtain and verify the requesting customer's identity before revealing account details or performing an account-changing action. Confirm at least two identity fields against the user record (date of birth, email, phone number, or address), obtain the current timestamp, and call `log_verification` with all required record fields and that timestamp.

The requester must be the account owner or an authorized account manager. Obtain:

- a reliable user lookup value and resolve the canonical `user_id`;
- the target `credit_card_account_id` and current credit limit;
- the requested *increase* as a positive whole-dollar integer; and
- confirmation of ownership/authorization.

Do not hardcode a customer, account, amount, date, or outcome. Treat user statements as useful context, but use the required internal checks to make the decision.

## Tier policy

Map the account's card product to its documented tier. Gold Rewards Card is a premium-tier product. If the product/tier cannot be determined from available policy, stop rather than guessing.

| Tier | Minimum age | Cooldown after an approved request | Utilization must be below | On-time months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry | 120 days | 120 days | 70% | 6 consecutive | 25% of current limit |
| Mid | 90 days | 90 days | 80% | 3 consecutive | 50% of current limit |
| Premium | 60 days | 60 days | 90% | 3 consecutive | 50% of current limit |

Calculate utilization as `current_balance / current_credit_limit * 100`. A balance equal to a threshold fails because the threshold is strict. An account is old enough or past cooldown when the applicable number of full calendar days has elapsed. Denied historical requests do **not** trigger the cooldown; evaluate the most recent approved request.

## Required workflow and order

1. **Verify identity and locate the account.** Resolve the user, verify two identity factors, log verification, retrieve the user's card accounts, and select the requested card only after confirming it belongs to that user.
2. **Validate the requested amount before submission.** Calculate the tier maximum from the current credit limit. If the requested increase exceeds it, do not submit a CLI request. Tell the customer the maximum permitted increase and ask whether they want to request that amount instead. If they do, obtain clear confirmation and restart amount validation with the revised amount.
3. **Submit the valid request before eligibility checks.** Unlock and call `submit_credit_limit_increase_request_7392` with `credit_card_account_id`, `user_id`, and `requested_increase_amount`. Retain its confirmation/reference if returned. This formal submission must precede eligibility review.
4. **Run every required review, even if one item already appears to fail.** Unlock and call the following tools with the exact documented IDs:
   - `get_credit_limit_increase_history_4829` with `credit_card_account_id`;
   - `get_user_dispute_history_7291` with `user_id`;
   - `get_pending_replacement_orders_5765` with `credit_card_account_id`; and
   - `get_payment_history_6183` with `credit_card_account_id` and the tier-required number of months.

   Also inspect the account record/current account-status data for account opening date, current balance, credit limit, and whether it is current with no past-due balance. Use the current time for age and history-date calculations.
5. **Interpret the results.** Check all of the following:
   - account age meets the tier minimum;
   - no approved CLI request falls within the tier cooldown;
   - no dispute is active (for example, `open` or `under_review`);
   - no replacement order is non-final (anything other than clearly `delivered` or `cancelled`);
   - the account is current and has no past-due balance;
   - utilization is strictly below the tier threshold; and
   - each required payment-history month is on time and consecutive.
6. **Record the decision.** If every condition passes, unlock and call `approve_credit_limit_increase_5847` with the account ID, user ID, and `new_credit_limit = current_credit_limit + requested_increase_amount`. Otherwise unlock and call `deny_credit_limit_increase_5848` with the account ID, user ID, and the applicable allowed denial reason:
   - age → `insufficient_account_age`
   - cooldown → `cooldown_period_active`
   - active dispute → `pending_disputes`
   - pending/non-final replacement → `pending_replacement_card`
   - past due → `past_due_balance`
   - threshold reached/exceeded → `high_utilization`
   - payment history inadequate → `insufficient_payment_history`
   - a post-submission amount issue → `requested_amount_exceeds_limit`
   - another documented, verified disqualifier → `other`
7. **Communicate plainly.** For an approval, confirm the increase and new total limit. For a denial, state the verified reason and a useful next step: the applicable eligibility date for age/cooldown, lowering utilization, resolving a dispute/replacement, bringing the account current, or establishing the required payment history. Do not claim a decision occurred unless its decision tool returned success.

## Safety and incomplete-data handling

Do not make a decision based solely on the customer saying there are no disputes, no replacement, or on-time payments. Do not approve if a required check is unavailable, ambiguous, or returns malformed data. Do not invent an undocumented banking tool. Preserve the submitted request, explain that review cannot be completed because a required internal verification is unavailable, and use normal support escalation/transfer procedures if needed. Do not retry an action-changing call whose result is unknown.

If several verified eligibility failures exist, complete all checks and use the most directly applicable documented denial reason; retain the other findings in the case context if supported by the environment. The amount-limit precheck is the exception: no request should be submitted until the customer confirms a compliant amount.

## Optional deterministic evaluator

`scripts/cli_policy.py` evaluates normalized, non-sensitive facts after tool responses are interpreted. It does not call banking tools and does not itself approve, deny, or submit anything. It is useful for checking date boundaries, percentage limits, and a consistent decision reason.

Example invocation:

```sh
python3 scripts/cli_policy.py <<'JSON'
{"tier":"premium","as_of":"2025-01-15","opened_on":"2024-01-01","current_limit":"5000","current_balance":"100","requested_increase":2000,"approved_request_dates":[],"active_dispute":false,"pending_replacement":false,"past_due":false,"consecutive_on_time_months":3}
JSON
```

Input is one JSON object. Required fields are `tier`, `as_of`, `opened_on`, `current_limit`, `current_balance`, `requested_increase`, `approved_request_dates`, `active_dispute`, `pending_replacement`, `past_due`, and `consecutive_on_time_months`. Dates may be ISO dates or ISO timestamps. `approved_request_dates` must contain only approved-request submission dates. The output JSON reports the allowed maximum, proposed total limit, each check, and either `eligible`, `denial_reason`, `request_amount_invalid`, or `manual_review_required`. Before acting, ensure each normalized input came from the appropriate current account/tool result.
