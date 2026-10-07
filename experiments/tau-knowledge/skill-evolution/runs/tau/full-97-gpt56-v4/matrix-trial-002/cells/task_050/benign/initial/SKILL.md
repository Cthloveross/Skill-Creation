---
name: credit-limit-increase-processing
description: Process a credit-card credit limit increase (CLI) request through identity verification, tier-based amount validation, required submission, eligibility checks, approval or denial, and customer communication. Use for an account owner's request to add a specified dollar amount to an existing credit limit.
---

# Credit Limit Increase Processing

Use this Skill only for a customer-requested CLI. Treat the requested amount as the **dollar increase**, not the desired new total limit.

## Required information and assumptions

Obtain or establish at runtime:

- Customer identity, including two independently confirmed identity fields out of date of birth, email, phone number, and address.
- `user_id`, the specific `credit_card_account_id`, card tier, current credit limit, current balance, and account-open date.
- A positive requested increase amount.
- The current date/time.
- Status evidence for prior approved CLI requests, active disputes, replacement-card orders, account standing/past-due balance, and on-time payment history.

Do not treat a customer assertion as a substitute for an internal check where an internal verification tool is available. Do not expose internal eligibility logic beyond an appropriate customer-facing explanation.

## Tier policy

| Tier | Minimum age | Cooldown after an approved request | Utilization must be below | Consecutive on-time months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | 70% | 6 | 25% of current limit |
| Mid-tier | 90 days | 90 days | 80% | 3 | 50% of current limit |
| Premium-tier | 60 days | 60 days | 90% | 3 | 50% of current limit |

A customer qualifies on the minimum-age day and after the stated number of full cooldown days. Utilization exactly equal to the threshold fails. Only an **approved** prior CLI request starts the cooldown; a denied request does not.

For example, the documented Gold Rewards Card is Premium-tier. Do not infer a tier for another product without reliable account or product information.

## Operational workflow

Follow this order exactly.

1. **Verify identity and choose the account.** Locate the user using the supplied name or email. Ask the customer to confirm two identity fields; retrieve the user record, compare the fields, get the current time, and call `log_verification` with the complete retrieved identity record and timestamp. Retrieve the customer's credit-card accounts and have the customer identify the intended account if more than one is plausible.
2. **Collect and validate the request amount before submission.** Confirm that the amount is a positive dollar increase. Determine the tier maximum from the current credit limit. If the amount exceeds that maximum, tell the customer the maximum dollar increase and ask whether they want to proceed at that amount. **Do not submit** an over-limit request. Restart this step if the customer changes the amount.
3. **Submit the valid request before eligibility checks.** Unlock `submit_credit_limit_increase_request_7392`, then call it with `credit_card_account_id`, `user_id`, and integer `requested_increase_amount`. Record the result for the customer case. Submission is required even if a later check will cause a denial.
4. **Perform every eligibility check after submission.**
   - Calculate account age from the account-open date and current date.
   - Unlock and call `get_credit_limit_increase_history_4829` with the account ID. Inspect request status and date; apply cooldown only to the most recent approved request.
   - Verify active-dispute status with the supported account/dispute source.
   - Verify replacement status with the supported replacement-order source. If no such source is available in the runtime, do not claim the check passed merely because the customer said no.
   - Verify that the account is current and has no past-due balance using supported account-status data. A displayed zero current balance alone is not proof of no past-due balance unless the returned status explicitly establishes it.
   - Compute utilization as `current_balance / current_credit_limit * 100` from current account data.
   - Unlock and call `get_payment_history_6183` using the account ID and the tier-required number of months. Confirm the returned period shows every required payment month on time.
5. **Decide and record the result.** If all checks pass, unlock and call `approve_credit_limit_increase_5847` with `new_credit_limit = current_credit_limit + requested_increase_amount`. If one or more checks fail, unlock and call `deny_credit_limit_increase_5848` with the applicable allowed reason:
   - age → `insufficient_account_age`
   - cooldown → `cooldown_period_active`
   - dispute → `pending_disputes`
   - replacement → `pending_replacement_card`
   - standing/past due → `past_due_balance`
   - utilization → `high_utilization`
   - payment history → `insufficient_payment_history`

   An over-limit amount is handled before submission by asking for an adjusted amount, not by submitting it for denial.
6. **Handle unavailable or ambiguous required evidence safely.** If a required verification cannot be run or its result is ambiguous, do not approve and do not fabricate a denial reason. Leave the submitted request unfinalized and transfer/escalate using the applicable supported reason (normally `technical_system_error` for unavailable verification capability), stating which required verification remains unavailable.
7. **Communicate clearly.** For approval, confirm the dollar increase and new total credit limit. For denial, state the customer-facing reason and a relevant next step (for example, wait until the cooldown expires, lower utilization, or establish the required payment history). Do not reveal internal IDs or unsupported details.

## Eligibility helper

Use `scripts/cli_eligibility.py` to calculate deterministic tier limits, dates, utilization, and a safe recommendation. It does not call banking tools and does not itself approve, deny, submit, or transfer anything.

### Input JSON

```json
{
  "tier": "Premium-tier",
  "as_of_date": "YYYY-MM-DD",
  "account_open_date": "YYYY-MM-DD",
  "current_credit_limit": "5000.00",
  "current_balance": "0.00",
  "requested_increase_amount": "2500.00",
  "last_approved_request_date": null,
  "payment_on_time_consecutive_months": 3,
  "has_active_disputes": false,
  "has_pending_replacement_card": false,
  "has_past_due_balance": false
}
```

Use `null` for an unavailable check. `last_approved_request_date: null` means there is no prior approved request, not merely that history has not been checked.

### Output JSON

The helper emits an object with tier thresholds, monetary calculations, each criterion's `pass`/`fail`/`unknown` state, and one of these recommendations:

- `approve` — every required criterion passed and amount is within the tier maximum.
- `deny` — a post-submission eligibility criterion failed; `denial_reason` is an allowed tool value.
- `hold_for_verification` — one or more required checks are unknown.
- `amount_requires_customer_adjustment` — requested increase exceeds the maximum and must not be submitted.
- `invalid_input` — values or dates cannot safely be evaluated.

Before acting on an `approve` or `deny` recommendation, compare its inputs to current tool results and ensure the CLI has already been submitted when required.
