---
name: credit-limit-increase-processing
description: Process a credit-card credit limit increase (CLI) request after identifying and verifying the account holder. Use for requests that require tier-based amount validation, formal submission, post-submission eligibility checks, and an approve-or-deny banking-tool decision.
---

# Credit Limit Increase Processing

## Scope and prerequisites

Use this Skill for a customer requesting a dollar increase to a credit-card limit. The executor must have access to the normal banking tools named below and must establish the card's **documented CLI tier** (`entry`, `mid`, or `premium`). Do not infer a CLI tier merely from a marketing card name unless an authoritative product/account record explicitly maps that card to the tier.

Before any account-changing action:

1. Identify the customer and the intended credit-card account.
2. Confirm the requester is the account owner or authorized account manager.
3. Verify identity by matching at least two of date of birth, email, phone number, and address against the user record. Obtain the values from the customer rather than disclosing them. Call `log_verification` with all required record fields and the timestamp from `get_current_time` only after the two matches succeed.
4. Obtain a positive whole-dollar requested increase and the customer's reason. A requested new total limit can be converted to an increase only after confirming the current limit.
5. Obtain current account facts from the authoritative account record: current limit, current balance, account-open date, past-due/current status, and the documented CLI tier. If a required fact is absent, seek an authorized account-status/product-tier source. Do not fabricate a passing result from a customer assertion.

The normal tools used by this workflow are discoverable. Unlock each tool before its first call:

- `submit_credit_limit_increase_request_7392`
- `get_credit_limit_increase_history_4829`
- `get_user_dispute_history_7291`
- `get_pending_replacement_orders_5765`
- `get_payment_history_6183`
- `approve_credit_limit_increase_5847`
- `deny_credit_limit_increase_5848`

## Tier rules

| Tier | Minimum age | Cooldown after an approved request | Utilization must be below | Consecutive on-time months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| entry | 120 days | 120 days | 70% | 6 | 25% of current limit |
| mid | 90 days | 90 days | 80% | 3 | 50% of current limit |
| premium | 60 days | 60 days | 90% | 3 | 50% of current limit |

Use `scripts/cli_rules.py` for the deterministic tier thresholds, amount limit, utilization, account-age, and cooldown calculation. Monetary inputs are strings or numbers representing dollars; do not use binary floating-point arithmetic for the decision.

## Required order of operations

### 1. Validate the requested increase *before submission*

Run `cli_rules.py` with `action: "precheck"`, the established tier, current limit, requested whole-dollar amount, account-open date, and current timestamp. Ensure the amount is positive and does not exceed the tier maximum. An exact maximum is permitted.

If the amount exceeds the maximum, tell the customer the maximum permissible increase and ask whether they want that lower amount. **Do not submit, approve, or deny a CLI request** for the excessive amount. If they choose a revised amount, repeat this precheck using the revised explicit amount.

If the tier, current limit, or amount cannot be established, do not submit an unverifiable request; explain what is needed or use the approved escalation path for unavailable internal data.

### 2. Submit the valid request

For a valid amount, call:

```text
submit_credit_limit_increase_request_7392(
  credit_card_account_id=<account id>,
  user_id=<user id>,
  requested_increase_amount=<whole-dollar increase>
)
```

Submission creates the required audit record and occurs **before** eligibility checks. Record the submission result. If submission fails or is ambiguous, do not retry blindly and do not approve/deny unless the banking system clearly establishes the request state.

### 3. Perform and record every eligibility check

After successful submission, complete all checks even if an earlier one fails so the audit is complete:

1. **Account age:** calculate from the account-open date and current date. The minimum is inclusive.
2. **Cooldown:** call `get_credit_limit_increase_history_4829` with the account ID. Inspect the most recent *approved* CLI request. Denied requests do not start a cooldown. A customer is eligible when the configured number of full days has elapsed since the approved request's submission date. Capture the next eligible date if blocked.
3. **Disputes:** call `get_user_dispute_history_7291` with the user ID. Any dispute in a non-final active status (for example `open` or `under_review`) blocks the CLI. Closed disputes do not.
4. **Replacement cards:** call `get_pending_replacement_orders_5765` with the account ID. Any order not clearly `delivered` or `cancelled` blocks the CLI.
5. **Good standing:** verify from authoritative account-status data that there is no past-due balance and the account is current. Do not equate a zero current balance with no past-due status unless the system expressly does so.
6. **Utilization:** calculate `current_balance / current_limit * 100` using the current authoritative amounts. It must be strictly less than the tier threshold; equality fails.
7. **Payment history:** call `get_payment_history_6183` with the account ID and the tier-required number of months. Confirm every one of the required consecutive months is on time. A partial response, missed payment, or unparseable status fails this requirement.

Use `cli_rules.py` with `action: "evaluate"` to make age, utilization, and cooldown boundary handling consistent. Supply `last_approved_request_date` only for an approved historical request; use `null` when none exists. Pass the observed boolean results for disputes, replacement orders, standing, and payment history.

If a required tool/source is unavailable, malformed, or ambiguous, do not represent the criterion as passed. Preserve the submission audit record and use the organization-approved handling/escalation path rather than guessing a decision.

### 4. Record the decision

If every required check passes, calculate `new_credit_limit = current_limit + requested_increase_amount` exactly and call:

```text
approve_credit_limit_increase_5847(
  credit_card_account_id=<account id>,
  user_id=<user id>,
  new_credit_limit=<new total limit as a float>
)
```

If any check fails, call `deny_credit_limit_increase_5848` once with the account ID, user ID, and one permitted reason. Map failures as follows:

- age → `insufficient_account_age`
- approved-request cooldown → `cooldown_period_active`
- active dispute → `pending_disputes`
- non-final replacement order → `pending_replacement_card`
- not current/past due → `past_due_balance`
- utilization at or above threshold → `high_utilization`
- required on-time history absent → `insufficient_payment_history`
- a submitted request later found to exceed the permitted amount → `requested_amount_exceeds_limit`
- a substantiated issue with no listed category → `other`

When more than one criterion fails, choose the first applicable reason in the ordered workflow above for the required tool field, while retaining all observed failures in internal notes where supported.

### 5. Customer communication

State that the request was submitted and then communicate the recorded outcome. For an approval, confirm the new total limit. For a denial, explain the applicable reason without exposing internal-only details and give a practical next step. For cooldown, state the calculated next eligible date; for age, state the date the age threshold will be reached; for utilization, say it must be reduced below the tier threshold; for payment history, explain the required consecutive on-time months. Never claim an action succeeded if its tool result did not confirm it.

## Helper interface

`scripts/cli_rules.py` reads one JSON object from stdin and writes one JSON object to stdout.

`precheck` input fields:

- `action`: `"precheck"`
- `tier`: `"entry"`, `"mid"`, or `"premium"`
- `current_limit`: dollar amount
- `requested_increase`: dollar amount
- `account_open_date`: ISO date (`YYYY-MM-DD`)
- `as_of`: ISO date or timestamp

It returns `amount_valid`, `max_increase`, `account_age_days`, `age_valid`, and tier thresholds.

`evaluate` accepts the above current-limit/account/date fields plus `current_balance`, `last_approved_request_date` (ISO date or `null`), `no_active_disputes`, `no_pending_replacement`, `good_standing`, and `payment_history_valid`. It returns individual criteria, `denial_reason`, `next_cooldown_eligible_date`, and an exact-string `new_credit_limit`. Validate that all expected booleans and computed fields agree with actual tool results before acting.
