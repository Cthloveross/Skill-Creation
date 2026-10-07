---
name: credit-limit-increase-processing
description: Safely process a verified customer's credit-card credit-limit-increase request, including amount validation, formal submission, all required eligibility checks, and an approval, denial, or supported escalation.
---

# Credit Limit Increase Processing

Use this Skill for a request to increase the limit on a credit-card account. The workflow has a significant ordering constraint: validate a definite requested amount against an **authoritative** tier first; submit a valid request; then perform every eligibility check; finally record exactly one approval or denial. Never infer a CLI tier from a card's marketing/product name.

## Runtime facts required

Obtain at runtime, from the authenticated customer and authoritative records:

- the customer `user_id` and intended `credit_card_account_id`;
- two matching identity fields and the user record needed for verification logging;
- the account's authoritative CLI tier: `Entry-tier`, `Mid-tier`, or `Premium-tier`;
- current limit, balance, opening date, status, and past-due balance;
- a whole-dollar, positive increase amount confirmed by the customer; and
- the current time plus the required history, dispute, replacement, and payment results.

A customer name identifies a record but is not authentication. Before disclosing account-specific information or taking an account action, ask the customer for two of date of birth, email address, phone number, and address. Compare both with the user record, obtain the current time, and call `log_verification` with every required field from that record and the timestamp. Do not log verification if either field does not match.

The supplied policy defines rules by CLI tier, not by product/card name. A product page's general limit range is not a tier mapping. Look for an explicit authoritative tier in an account record or policy. Do not ask the customer to self-classify a tier as a substitute for that source. If no authoritative source or retrieval tool is available, do not submit, approve, or deny a CLI request; explain the missing classification without guessing and transfer/escalate through the available support path.

## Rules by authoritative tier

| Tier | Account age at least | Cooldown after an approved request | Utilization | On-time months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | below 70% | 6 consecutive | 25% of current limit |
| Mid-tier | 90 days | 90 days | below 80% | 3 consecutive | 50% of current limit |
| Premium-tier | 60 days | 60 days | below 90% | 3 consecutive | 50% of current limit |

Calculate utilization as `current_balance / current_limit * 100`. The threshold is strict: equality fails. Age and cooldown pass on the required full day (`>=`). Only an **approved** prior CLI request starts a cooldown; its date is the submission date. A denied request does not start one.

## Procedure

1. **Identify, authenticate, and select the account.** Locate the named customer, verify two identity fields, log successful verification, retrieve the customer's card accounts, and confirm the requested account. Retrieve a current timestamp and account facts. If the account is ambiguous, ask the authenticated customer to choose it.

2. **Obtain a definite amount and authoritative tier.** If the customer states a percentage, calculate the dollar amount from the current limit, present the amount, and obtain confirmation of that whole-dollar amount. Obtain the tier only from an authoritative record/policy. If the tier is unavailable, stop without any CLI decision or request and escalate; do not infer it from branding.

3. **Validate the amount before submitting.** Calculate the tier maximum from the current limit. The amount must be a positive integer number of dollars and no greater than that maximum. If it is too high, do not submit; state the maximum and ask whether the customer wants that amount instead. If it is non-integral or missing, request a whole-dollar amount.

4. **Submit a valid request.** Unlock and call `submit_credit_limit_increase_request_7392` with `credit_card_account_id`, `user_id`, and the confirmed integer `requested_increase_amount`. Preserve the actual submitted amount. Submission must occur before post-submission eligibility checks.

5. **Complete every post-submission check.** Do not substitute a customer statement for an internal check. In addition to account age, current/good status with no past due balance, and strict utilization, unlock and call:
   - `get_credit_limit_increase_history_4829` with `credit_card_account_id`; find the most recent **approved** request and assess cooldown from its submission date.
   - `get_user_dispute_history_7291` with `user_id`; an open, active, or under-review dispute blocks processing. Closed disputes alone do not.
   - `get_pending_replacement_orders_5765` with `credit_card_account_id`; any order not clearly delivered or cancelled blocks processing.
   - `get_payment_history_6183` with `credit_card_account_id` and the tier's required month count; every required consecutive month must be on time.

   If a required tool response is failed, incomplete, or ambiguous, do not approve. Retry where appropriate or escalate using the normal support path. Still complete the other available required checks when a request was submitted, so the audit record is complete.

6. **Record one decision after all checks.** If all checks pass, unlock and call `approve_credit_limit_increase_5847` with the account ID, user ID, and `new_credit_limit` equal to current limit plus submitted increase as a float. Otherwise unlock and call `deny_credit_limit_increase_5848` with the applicable allowed reason:
   - `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, or `insufficient_payment_history`;
   - `requested_amount_exceeds_limit` only for the invalid pre-submission amount case (normally there is no submitted request); or
   - `other` only when no listed reason accurately captures a documented blocker.

   If several checks fail, complete them all and use the most specific applicable reason while communicating the material customer-safe blockers.

7. **Communicate.** Confirm an approved new total limit. For a denial, give the customer-safe reason and a practical next step, such as waiting through cooldown, reducing utilization, resolving a dispute, awaiting replacement delivery/cancellation, or establishing payment history. Do not expose internal-only information.

## Eligibility calculator

Run `scripts/evaluate_cli.py` only after the executor has normalized authoritative facts. It reads one JSON object from stdin and writes one JSON object to stdout; it never invokes banking tools or causes a banking action.

Input schema:

- `tier`: one of the three tier strings above;
- `current_limit`, `current_balance`, `requested_increase_amount`, `past_due_amount`: finite numeric values;
- `account_open_date`, `as_of`: ISO-8601 date or timestamp strings;
- `last_approved_request_date`: ISO date/timestamp string or `null`;
- `account_current`, `has_active_dispute`, `has_pending_replacement`: JSON booleans; and
- `consecutive_on_time_months`: non-negative integer.

Output schema includes the applicable requirements, full-day age/cooldown calculations, utilization, maximum and proposed new limit, named check booleans, blockers, and a recommended post-submission decision. `pre_submission_valid` is false for a non-whole-dollar, non-positive, or excessive requested amount; such a result means clarify/offer the maximum rather than submit. Validate that all input facts, especially tier and prior-approved date, were derived from live authoritative sources before using the result.
