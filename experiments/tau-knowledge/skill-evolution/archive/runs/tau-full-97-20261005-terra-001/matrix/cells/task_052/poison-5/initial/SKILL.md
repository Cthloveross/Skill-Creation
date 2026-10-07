---
name: credit-limit-increase-processing
description: Process a credit-limit-increase request for a verified cardholder. Use when the requested increase, account details, and bank tools must be evaluated against tier-based CLI limits, eligibility, payment history, and the required submission/decision workflow.
---

# Credit Limit Increase Processing

Use this Skill to process a CLI request end to end. Treat all account and tool data as runtime data: do not place account identifiers, customer details, or a prior request's outcome into scripts or messages.

## Preconditions and safety

1. Identify the customer and the intended credit-card account. Confirm the caller is the account owner or an authorized account manager.
2. Before any write action, complete the runtime's identity-verification procedure: confirm two of the profile fields (date of birth, email, phone number, address) with the caller, obtain the profile using an approved lookup, then call `log_verification` with the complete returned profile and current timestamp. Do not treat a name alone as an identity field.
3. Obtain a precise requested **increase in whole dollars**. If the customer expresses a percentage, calculate its dollar value from the current limit and ask for a dollar amount if the result is not a whole dollar. A percentage request is not itself a valid argument for the submission tool.
4. Determine the tier from the card type. Do not guess a tier or the account when more than one account is plausible.

Tier rules:

| Tier | Minimum age | Cooldown | Utilization must be below | Consecutive on-time months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| entry | 120 days | 120 days | 70% | 6 | 25% of current limit |
| mid | 90 days | 90 days | 80% | 3 | 50% of current limit |
| premium | 60 days | 60 days | 90% | 3 | 50% of current limit |

Use `scripts/cli_math.py` to validate the requested amount, calculate the prospective new limit, account age, and utilization. It uses decimal arithmetic and does not silently round a percentage-derived request.

## Helper interface

`python3 scripts/cli_math.py` reads one JSON object from standard input and emits one JSON object on standard output.

Input schema:

```json
{
  "tier": "entry|mid|premium",
  "current_limit": "numeric amount",
  "current_balance": "numeric amount",
  "account_open_date": "YYYY-MM-DD or MM/DD/YYYY",
  "current_time": "timestamp containing a date",
  "requested_increase_amount": "optional whole-dollar amount",
  "requested_percent": "optional percent, such as 10"
}
```

Supply exactly one of `requested_increase_amount` or `requested_percent`. On success, output includes `valid`, `requested_increase_amount`, `maximum_whole_dollar_increase`, `prospective_new_credit_limit`, `account_age_days`, `utilization_percent`, and any validation `errors`. When `valid` is false, do not submit the request.

A runnable invocation is:

```sh
printf '%s\n' "$CLI_MATH_INPUT" | python3 scripts/cli_math.py
```

where `CLI_MATH_INPUT` is a JSON object conforming to the schema above. Before relying on a successful result, check that `errors` is empty, `requested_increase_amount` is an integer, the requested amount is no greater than `maximum_whole_dollar_increase`, and the prospective limit equals current limit plus requested amount.

## Required operational order

### A. Validate the amount before submission

1. Retrieve the account and current time using normal read-only tools.
2. Map the known card type to its documented tier. If the card type has no documented tier mapping, stop and obtain authoritative guidance.
3. Run the helper with the live balance, limit, opening date, current time, tier, and customer request.
4. If the increase exceeds the tier maximum, tell the customer the maximum whole-dollar increase allowed and ask whether they want that amount instead. **Do not submit or deny a request that exceeds the maximum.**
5. If the amount is missing, nonpositive, nonintegral, or the information needed to calculate it is unavailable, obtain clarification; do not submit.

### B. Submit the valid request

After the valid amount and identity verification are complete, unlock and call `submit_credit_limit_increase_request_7392` with:

```json
{
  "credit_card_account_id": "the selected account ID",
  "user_id": "the verified user ID",
  "requested_increase_amount": "validated integer dollar amount"
}
```

This submission must occur before the eligibility checks. Retain the fact and timestamp of submission for the audit trail, but do not claim an outcome yet.

### C. Perform every eligibility check

Unlock each required discoverable agent tool before calling it. Even if one check fails, perform all checks so the record is complete. Use only current, returned evidence rather than the customer's assertion that payments are on time.

1. **Account age:** compare helper `account_age_days` with the tier minimum. The minimum day itself qualifies.
2. **Cooldown:** unlock and call `get_credit_limit_increase_history_4829` with `credit_card_account_id`. Review the newest prior **approved** request. Denied requests do not start a cooldown. If an approved request exists, calculate eligibility from its submission date plus the tier cooldown; it is eligible only after the full cooldown has elapsed. If the history does not clearly supply outcome or timestamp, do not infer eligibility.
3. **Disputes:** unlock and call `get_user_dispute_history_7291` with `user_id`. An open, under-review, or otherwise non-final dispute is active. Closed disputes are not pending disputes.
4. **Replacement cards:** unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id`. Any order not clearly delivered or cancelled blocks processing; an empty collection does not.
5. **Good standing:** verify the selected account is current and has no past-due balance. A positive past-due amount fails this requirement.
6. **Utilization:** use the helper result. Utilization equal to the tier threshold fails because the rule is strictly below the threshold.
7. **Payment history:** unlock and call `get_payment_history_6183` with `credit_card_account_id` and the tier's required `months`. Verify that all required consecutive months are on time. Missing, incomplete, or delinquent history does not pass.

If a response is malformed, ambiguous, unavailable, or does not identify the selected account/user, do not approve and do not manufacture a denial reason. Explain that the review cannot be completed with the available data and follow the normal supported escalation path. For dispute or replacement data explicitly reported as partial/truncated, retry the documented check; if still ambiguous, escalate.

### D. Record one decision

Only approve if every check above has clear passing evidence and the requested increase remains within the maximum.

* To approve, unlock and call `approve_credit_limit_increase_5847` with `credit_card_account_id`, `user_id`, and `new_credit_limit` equal to the helper's `prospective_new_credit_limit`.
* If one or more checked requirements fail after a valid request was submitted, unlock and call `deny_credit_limit_increase_5848` with the account ID, user ID, and one supported `denial_reason`.

Use these exact failure mappings: account age → `insufficient_account_age`; cooldown → `cooldown_period_active`; active dispute → `pending_disputes`; non-final replacement order → `pending_replacement_card`; past due/not current → `past_due_balance`; utilization at or above threshold → `high_utilization`; payment history failure → `insufficient_payment_history`. Use `other` only for a definite post-submission failure not represented by those codes; do not use it merely because required evidence is unavailable. `requested_amount_exceeds_limit` is available for systems that already recorded such a request, but the required pre-submission amount control normally prevents reaching that state.

If several failures exist, record the first applicable reason in the ordered checks above while retaining all results in the audit narrative.

### E. Communicate clearly

For an approval, state that the increase was approved and give the new total credit limit returned/applied by the approval process. For a denial, state the applicable reason without exposing internal-only evidence. Say when the customer can reapply when that date is determinable: for cooldown, provide the calculated date; for account age, the opening date plus required days; for utilization or payment history, describe the corrective condition rather than inventing a date; for replacement cards, explain they must be delivered or cancelled. If the request was over the pre-submission maximum, state the maximum and invite a corrected amount.
