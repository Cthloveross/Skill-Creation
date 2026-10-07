---
name: credit-card-account-closure
version: 1.0.0
description: Safely process a verified customer's credit-card account-closure request, including eligibility checks, required retention handling, closure-reason logging, and closure communications. Use when an authenticated customer asks to close a credit card account.
---

# Credit Card Account Closure

Use this Skill to complete a credit-card closure without closing an ineligible account or bypassing the retention protocol. Read the active conversation and retrieve live account data at execution time; do not treat a customer's statement about disputes, replacements, balance, or account status as a substitute for the required system checks.

## Required inputs and prerequisites

Collect or establish:

- The requested credit-card account and its `credit_card_account_id`.
- The authenticated customer's canonical `user_id`.
- Successful identity verification under the normal verification procedure. In this runtime, verify two of the four identity fields (date of birth, email, phone number, address) against the customer profile, then call `log_verification` with all required profile fields and the current timestamp.
- The account's open date and current balance.
- Live dispute history and replacement-order results.

If multiple accounts match the customer's description, ask the customer to identify the intended account. Do not choose an account based only on a similar card type.

## Tool workflow

Use the normal tools for account/profile lookup and verification. For each specialized tool below, unlock it with `unlock_discoverable_agent_tool` before calling it through `call_discoverable_agent_tool`.

### 1. Verify identity

1. Obtain the current time with `get_current_time` for the verification audit timestamp.
2. Compare two customer-confirmed identity fields with the profile returned by user lookup.
3. Only after two fields match, call `log_verification` with `name`, `user_id`, `address`, `email`, `phone_number`, `date_of_birth`, and `time_verified`.
4. If the fields do not match or fewer than two fields are confirmed, do not disclose further account information or perform closure actions. Ask for another verification field or follow normal escalation practice.

### 2. Check closure eligibility before retention or closure

Check every condition. A failure or ambiguous result blocks closure and blocks retention offers until resolved.

1. **Balance:** Account `current_balance` must equal `$0.00`.
2. **Account age:** Calculate the age from the account open date through the current date. It must be at least 60 days.
3. **Disputes:** Unlock and call `get_user_dispute_history_7291` with exactly the `user_id`. A dispute that is active, pending, open, or under review blocks closure. Treat an unfamiliar or unclear non-final status as blocking until clarified. Closed/resolved disputes do not block closure.
4. **Replacement cards:** Unlock and call `get_pending_replacement_orders_5765` with exactly the `credit_card_account_id`. An empty result is clear. If any order is pending, shipped, awaiting receipt, awaiting activation, or otherwise non-final, closure is blocked. Only when every returned order is clearly delivered or cancelled may this check pass.

If blocked, explain the specific prerequisite: pay the balance, wait until the account reaches 60 days, wait for dispute resolution, or complete/cancel the replacement process. Do not call the closure tool. If a tool result is missing, partial, or ambiguous, retry or escalate rather than assuming eligibility.

### 3. Apply the retention protocol only after eligibility passes

1. Unlock and call `get_closure_reason_history_8293` with `credit_card_account_id` to check for closure-reason records from the past year.
2. If a record exists within the past year, skip reason logging and all retention offers. Thank the customer and proceed to closure if all eligibility requirements remain satisfied.
3. If there is no recent record, determine the customer's reason and normalize it to exactly one permitted value:
   - `annual_fee`
   - `not_using_card`
   - `found_better_card`
   - `unhappy_with_rewards`
   - `simplifying_finances`
   - `negative_experience`
   - `other`
4. Unlock and call `log_credit_card_closure_reason_4521` using **only** `credit_card_account_id`, `user_id`, and `closure_reason`.
5. Address the concern and make one retention offer based on card tier if the customer still wants closure:
   - Entry tier: 500 bonus points or a $5 statement credit.
   - Mid tier: 2,000 bonus points or a $20 statement credit.
   - Premium and above: 5,000 bonus points or a $50 statement credit.

For an annual-fee concern, customers with at least two years of tenure may instead be offered a one-year fee waiver. If accepted, unlock and call `apply_credit_card_account_flag_6147` with `credit_card_account_id`, `user_id`, `flag_type` of `annual_fee_waived`, an `expiration_date` exactly one year from the current date in `MM/DD/YYYY`, and `reason` of `loyalty_benefit`. Customers with less than two years of tenure may be offered a permanent downgrade to a no-annual-fee card while preserving account history.

Do not pressure the customer. If a qualifying retention offer was already made during this conversation and the customer declined it, do not repeat it. Continue once the reason has been logged (when no recent closure record exists) and the eligibility requirements are confirmed.

### 4. Close the account

When identity is logged, all eligibility checks pass, and the retention protocol is complete or properly skipped:

1. Unlock `close_credit_card_account_7834`.
2. Call it with exactly `credit_card_account_id` and `user_id`.
3. Do not substitute a card identifier for the account identifier. Do not call it if either identifier does not belong to the authenticated customer.
4. Report only the actual tool outcome. If it errors or returns an unclear result, do not claim the account is closed; retry only when appropriate or escalate with the error context.

## Required customer communication after successful closure

Confirm that a confirmation email and final statement will arrive within several business days. State that unredeemed rewards may be redeemed for 45 days after the closure request and are forfeited afterward. If an annual fee posted recently, explain that a full refund may apply when closure occurs within 37 days of the fee charge.

For cash-back cards whose rewards are stored as points, explain values as cash back at one point per $0.01 only when relevant. Do not promise an annual-fee refund without confirming the fee-posting date and eligibility.

## Using the state evaluator

`scripts/evaluate_closure_state.py` performs deterministic age, balance, dispute, replacement, and workflow-readiness checks. It does not call banking tools and does not authorize a closure. Supply normalized facts obtained from the live tools, then use its `next_actions`, `blockers`, and `ready_to_close` fields to sequence the real tool calls.

Input is one JSON object on stdin. Required top-level fields are `current_date`, `identity_logged`, and `account`; other fields may be `null` until checked. `account` contains `account_id`, `date_of_account_open`, and `current_balance`. `disputes` and `replacement_orders` are either `null` or lists of objects with `status`. `recent_closure_record` is `true`, `false`, or `null`. `closure_reason` is a permitted reason or `null`; `reason_logged` is boolean. `retention` contains `offered` and `declined` booleans.

Run it as `python scripts/evaluate_closure_state.py < closure_state.json`. It emits one JSON object on stdout. Validate that `ready_to_close` is true and `blockers` is empty immediately before invoking the closure tool. A `false` readiness result always requires completing the listed action or resolving the listed blocker first.
