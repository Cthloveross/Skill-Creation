---
name: credit-limit-increase-processing
description: Process a verified cardholder's credit-limit-increase (CLI) request. Use for a confirmed dollar increase on an identified credit-card account when the agent can submit, review eligibility, and record an approval or denial using the CLI tools.
---

# Credit Limit Increase Processing

## Scope and controls

Use this workflow only for a CLI request made by the account owner or an authorized account manager. Before any banking action, verify customer identity, authority, account ownership, product eligibility, available credit, applicable limits, card/account details, and any required confirmation. Obtain and log identity verification after the customer confirms at least two of date of birth, email, phone number, or address; use `get_current_time` and `log_verification` for the audit record.

Do not expose internal eligibility criteria beyond an appropriate customer-facing explanation. Do not approve, deny, or submit if identity, authority, account ownership, the target account, the requested dollar amount, or the applicable tier cannot be established. Ask for the missing information or escalate operational/tool failures rather than guessing.

The source workflow requires this order:

1. Validate the confirmed amount against the tier maximum **before submission**.
2. Submit a valid confirmed request.
3. Check every eligibility item, including payment history.
4. Record one approval or denial.
5. Communicate the result.

A request that exceeds the per-request maximum is not submitted. Tell the customer the calculated maximum and obtain a new explicit dollar amount. A percentage expression alone is not a confirmed dollar amount unless it can be unambiguously calculated from the verified current limit and the customer confirms the calculated amount.

## Tier policy

| Tier | Minimum age | Approved-request cooldown | Utilization requirement | Consecutive on-time months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | strictly below 70% | 6 | 25% of current limit |
| Mid-tier | 90 days | 90 days | strictly below 80% | 3 | 50% of current limit |
| Premium-tier | 60 days | 60 days | strictly below 90% | 3 | 50% of current limit |

Obtain the tier from the card/product record or a reliable product mapping. Do not infer a tier solely from a generic card name when the mapping is unavailable. Calculate utilization as `current_balance / current_credit_limit * 100`; a balance equal to the limit is 100%. The utilization comparison is strict: equality with the threshold fails.

The cooldown applies only to the most recent **approved** CLI request. Count from the date that request was submitted. It has elapsed when the required full number of days has passed. Denied requests do not start a cooldown.

## Required runtime procedure

### 1. Identify and verify the requester

1. Locate the user and account using the supplied identity information and an account lookup.
2. Have the requester confirm two identity fields. Retrieve authoritative fields using `get_user_information_by_id` when needed.
3. Call `get_current_time`, then call `log_verification` with the complete retrieved identity record, `user_id`, and that timestamp.
4. Confirm the verified user's `user_id` owns the selected `credit_card_account_id`, and confirm the requester is the owner or authorized manager.
5. Read and retain the current credit limit, balance, past-due amount, account/current status, account-open date, card details, and product tier.

### 2. Confirm an in-range amount before submission

Calculate the maximum permitted increase from the current limit and tier percentage. Obtain explicit confirmation of an integer-dollar increase that is positive and no greater than that maximum. State the resulting total limit for confirmation.

If the amount is too high, explain the maximum and ask whether the customer wants to proceed with a specific compliant amount. Do not call the submission tool and do not call the denial tool merely because the original amount was above the maximum; this is an adjustment request, not a submitted CLI decision.

### 3. Submit the confirmed valid request

Unlock and call `submit_credit_limit_increase_request_7392` with:

```json
{
  "credit_card_account_id": "<verified account id>",
  "user_id": "<verified user id>",
  "requested_increase_amount": "<confirmed integer dollar amount>"
}
```

Record that submission succeeded. The formal CLI request must be created before the eligibility review below. If submission fails or its result is ambiguous, do not approve or deny; resolve the submission state first to avoid duplicate or conflicting records.

### 4. Perform and record every eligibility check

After successful submission, unlock the listed discoverable tool before its first use and make all of these checks even if an earlier one fails:

1. **Account age:** Calculate full days from the account-open date to the current date and compare with the tier minimum.
2. **Cooldown:** Unlock and call `get_credit_limit_increase_history_4829` with `credit_card_account_id`. Identify the most recent approved request and its submission date. Ignore denied requests for cooldown purposes. If it is within the tier cooldown, calculate the first date on which another request can be submitted.
3. **Disputes:** Unlock and call `get_user_dispute_history_7291` with `user_id`. Any active/non-final dispute, such as `open` or `under_review`, fails this check. Closed disputes do not.
4. **Replacement cards:** Unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id`. An empty collection passes. If any order is not clearly `delivered` or `cancelled` (for example, pending or shipped), this check fails.
5. **Good standing:** Verify the account is current and has no past-due balance. A positive past-due amount fails.
6. **Utilization:** Compare current utilization with the tier threshold.
7. **Payment history:** Unlock and call `get_payment_history_6183` with `credit_card_account_id` and `months` equal to the tier requirement. Confirm every returned month in that required consecutive period is on time.

Do not treat missing, malformed, partial, or ambiguous tool data as a pass. Retry or follow operational escalation procedures as appropriate; do not make a final CLI decision until all checks have an auditable result.

`python3 scripts/assess_cli.py` can calculate the deterministic tier thresholds, dates, utilization, and a proposed decision from normalized results. It does not call banking tools or cause any banking action.

### 5. Record the decision

If every check passes, unlock and call `approve_credit_limit_increase_5847` with the verified account and user IDs and `new_credit_limit` equal to:

`current_credit_limit + confirmed_requested_increase_amount`

If one or more eligibility checks fails, unlock and call `deny_credit_limit_increase_5848` once, selecting the applicable standardized reason:

- age failure: `insufficient_account_age`
- approved-request cooldown: `cooldown_period_active`
- active dispute: `pending_disputes`
- non-final replacement order: `pending_replacement_card`
- not current or past-due balance: `past_due_balance`
- utilization at or above threshold: `high_utilization`
- required consecutive on-time payments not met: `insufficient_payment_history`

Use `requested_amount_exceeds_limit` only for a request that was already formally submitted under a permitted operational exception; under the normal workflow, an excessive amount is caught before submission. Use `other` only when no listed reason accurately describes a confirmed, documented failure.

If more than one condition fails, preserve all check results in the case record and choose a truthful listed reason for the single denial call, preferably the first failed item in the ordered review above.

### 6. Communicate

For an approval, confirm that the increase was approved and state the new total credit limit. For a denial, explain the relevant customer-facing reason without revealing internal-only details. State the next actionable date for a cooldown or account-age denial when it can be calculated. For utilization, advise lowering utilization below the applicable threshold; for payment history, advise establishing the required consecutive on-time period; for a pending replacement, explain that processing must wait until it is delivered or cancelled.

## Helper input and output

`scripts/assess_cli.py` reads one JSON object from standard input and writes one JSON object to standard output. It accepts normalized values gathered from authoritative runtime tools; it does not parse arbitrary tool prose.

Required inputs: `tier`, `now`, `account_open_date`, `current_credit_limit`, `current_balance`, `requested_increase_amount`, `submission_recorded`, `is_current`, `past_due_amount`, `approved_request_dates` (array), `active_disputes` (boolean), `replacement_order_statuses` (array), and `consecutive_on_time_months`. Dates may be ISO dates/timestamps or `MM/DD/YYYY`. Tier is one of `entry`, `mid`, or `premium` (the corresponding `-tier` spellings are also accepted).

The output contains policy thresholds, calculated account age, utilization, maximum and proposed new limit, a `checks` object, `missing_or_invalid`, `status`, a recommended standardized `denial_reason` when applicable, and `cooldown_eligible_on` when applicable. Statuses are `needs_amount_adjustment`, `awaiting_submission`, `ready_to_approve`, `ready_to_deny`, or `insufficient_data`.

Example invocation with runtime-collected values (replace every placeholder with actual normalized values):

```sh
printf '%s' '{"tier":"<entry|mid|premium>","now":"<date>","account_open_date":"<date>","current_credit_limit":<number>,"current_balance":<number>,"requested_increase_amount":<integer>,"submission_recorded":true,"is_current":true,"past_due_amount":<number>,"approved_request_dates":[],"active_disputes":false,"replacement_order_statuses":[],"consecutive_on_time_months":<integer>}' | python3 scripts/assess_cli.py
```

Validate that `missing_or_invalid` is empty and that the tool-derived values used in the calculation match the verified account before relying on the output. Only `ready_to_approve` supports the approval call; only `ready_to_deny` supports a denial call after the required submission and complete review.