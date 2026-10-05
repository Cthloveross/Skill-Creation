---
name: credit-limit-increase-processing
description: Process a verified cardholder's credit limit increase (CLI) request through the required amount validation, submission, complete eligibility review, approval or recorded denial, and customer communication. Use for supported credit-card CLI requests when internal CLI tools are available.
---

# Credit Limit Increase Processing

## Purpose and prerequisites

Use this Skill to process a request for an increase amount, not merely answer a general question about CLIs. Obtain the runtime account data; never reuse identifiers, limits, dates, or other customer data from another case.

Before acting on an account, verify the requester according to the available verification policy: the customer must confirm two of the four identity fields (date of birth, email, phone number, address). Do not count facts retrieved from an internal profile as customer confirmation. Retrieve the profile using the supplied name or email/user ID, compare the two customer-provided fields, obtain the current time, and call `log_verification` with all required profile fields and the timestamp. If identity cannot be verified, do not submit or process a CLI.

This Skill supports these tiers only:

| Tier | Minimum age | Cooldown | Maximum utilization | On-time months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | below 70% | 6 | 25% of current limit |
| Mid-tier | 90 days | 90 days | below 80% | 3 | 50% of current limit |
| Premium-tier | 60 days | 60 days | below 90% | 3 | 50% of current limit |

Identify the tier from supported card documentation. Do not infer a tier from a card's name unless a supplied source explicitly maps it. Gold Rewards Card is a premium-tier card.

## Required operational order

1. **Clarify and verify.** Obtain either a dollar increase or enough information to calculate one. If the customer supplies a desired total limit, calculate `desired_total - current_limit`; a nonpositive result is not a CLI request and should be clarified. Verify identity and log the verification as described above.
2. **Read the account and validate the amount before submission.** Obtain the relevant account, its current limit, opening date, current balance, and current standing/past-due status. Determine its tier. Compute the tier maximum from the current limit.
   - The requested increase must be a positive whole-dollar amount and must not exceed the maximum.
   - If it exceeds the maximum, **do not submit** a formal CLI request and do not call the denial tool. Tell the customer the maximum permissible increase and ask whether they want that amount instead.
   - If required account or tier data are absent or ambiguous, stop and resolve the data problem; do not guess.
3. **Submit a valid request before eligibility checks.** Unlock `submit_credit_limit_increase_request_7392`, then call it through the discoverable-agent tool with `credit_card_account_id`, `user_id`, and integer `requested_increase_amount`. Retain the request ID and submission time if returned. A valid amount is not itself an approval.
4. **Perform every eligibility check after submission.** Unlock and use all applicable tools below. Complete all checks even if an earlier check fails, so the audit is complete.
   - Account age: compare the opening date with the current date.
   - Cooldown: unlock and call `get_credit_limit_increase_history_4829` with the account ID. Assess prior requests, excluding the request just submitted. A denied request does not trigger cooldown. If the most recent prior request was approved, the customer qualifies on the date that is the approved request's submission date plus the tier cooldown days.
   - Active disputes: unlock and call `get_user_dispute_history_7291` with the user ID. A dispute with a non-final status (for example, `open` or `under_review`) is active. A `closed` dispute is not active. If a returned status cannot be classified, treat this check as unresolved rather than assuming it is closed.
   - Replacement orders: unlock and call `get_pending_replacement_orders_5765` with the account ID. An empty order collection passes. Orders block processing if any order is not clearly `delivered` or `cancelled`; `pending` and `shipped` are blocking.
   - Standing: verify that the account is current and has no past-due balance. A zero current balance alone does not establish this check.
   - Utilization: calculate `current_balance / current_credit_limit * 100`; it must be strictly below the tier threshold. A value equal to the threshold fails.
   - Payment history: unlock and call `get_payment_history_6183` with the account ID and the tier's required month count. Confirm every one of those requested consecutive months is on time.
5. **Decide only after all check results are known.** If all checks pass, unlock and call `approve_credit_limit_increase_5847` with the account ID, user ID, and `new_credit_limit = current_credit_limit + requested_increase_amount`. If one or more checks fail, unlock and call `deny_credit_limit_increase_5848` with an allowed denial reason. Use this deterministic primary-reason order if more than one fails:
   1. `insufficient_account_age`
   2. `cooldown_period_active`
   3. `pending_disputes`
   4. `pending_replacement_card`
   5. `past_due_balance`
   6. `high_utilization`
   7. `insufficient_payment_history`

   Never approve, deny, or use `other` merely because a required lookup failed, returned incomplete data, or was ambiguous. Retry or resolve the operational issue according to normal procedures; if it cannot be resolved, explain that processing cannot yet be completed.
6. **Communicate the recorded result.** For approval, state that the request was approved and state the new total credit limit. For a denial, explain the primary recorded reason and an actionable next step. For account age, state the date eligibility begins when calculable; for cooldown, state the next eligible submission date; for replacement orders, explain that the replacement must be delivered or cancelled; for utilization, advise reducing utilization below the tier threshold. Do not disclose internal-only eligibility details beyond the appropriate customer-facing explanation.

## Discoverable-tool call pattern

For each specialized tool, first call `unlock_discoverable_agent_tool` with the exact tool name, then call `call_discoverable_agent_tool` with that same name and a JSON-string `arguments` object. Specialized tools and arguments are:

- `submit_credit_limit_increase_request_7392`: `credit_card_account_id`, `user_id`, `requested_increase_amount`
- `get_credit_limit_increase_history_4829`: `credit_card_account_id`
- `get_user_dispute_history_7291`: `user_id`
- `get_pending_replacement_orders_5765`: `credit_card_account_id`
- `get_payment_history_6183`: `credit_card_account_id`, `months`
- `approve_credit_limit_increase_5847`: `credit_card_account_id`, `user_id`, `new_credit_limit`
- `deny_credit_limit_increase_5848`: `credit_card_account_id`, `user_id`, `denial_reason`

Read the actual returned records rather than assuming a response shape. Preserve the request/lookup outcome in normal case notes where that is supported.

## Decision helper

`scripts/evaluate_cli.py` performs deterministic arithmetic, date, and normalized eligibility evaluation. It does not call banking tools or submit any action. Give it normalized data obtained at runtime only after completing the required post-submission checks. It emits a recommendation; the executor remains responsible for ensuring the data accurately reflects the tool responses and performing the required bank action.

### Input schema

Send one JSON object on stdin:

```json
{
  "current_time": "YYYY-MM-DD ...",
  "account": {
    "tier": "premium",
    "opened_on": "YYYY-MM-DD",
    "current_credit_limit": 0,
    "current_balance": 0,
    "past_due": false
  },
  "requested_increase_amount": 0,
  "prior_requests": [
    {"submitted_at": "YYYY-MM-DD", "status": "approved"}
  ],
  "has_active_disputes": false,
  "has_pending_replacement": false,
  "payment_history": {"consecutive_on_time_months": 0}
}
```

`prior_requests` must contain only requests before the just-submitted request; do not pass the new request returned by this workflow. `past_due`, dispute, and replacement values must be explicit booleans based on actual lookup results. `status` is case-insensitive. Dates may begin with an ISO date even if a time follows.

### Output and validation

The script emits JSON containing `recommendation` (`approve`, `deny`, `do_not_submit`, or `incomplete`), `new_credit_limit`, `maximum_increase`, per-check results, and the applicable `denial_reason` or `next_eligible_on` when determinable. Validate before acting:

- `do_not_submit` means no CLI submission or denial-recording action occurred.
- `incomplete` means required data are missing/invalid and no decision action may be called.
- An `approve` recommendation must have every `checks` value `true` and a numeric `new_credit_limit`.
- A `deny` recommendation names only one of the permitted denial enums.

Runnable invocation in the Skill runtime:

```text
run_skill_script(relative_path="scripts/evaluate_cli.py", input_json=<normalized JSON object above>)
```
