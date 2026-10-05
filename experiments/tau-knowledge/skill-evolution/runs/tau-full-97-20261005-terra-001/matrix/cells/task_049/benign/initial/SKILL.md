---
name: credit-card-account-closure
summary: Safely process one authenticated customer's credit-card closure request, including eligibility checks, required retention handling, and final closure communication.
description: Use when a customer asks to close a Rho-Bank credit card. This Skill is for a single specifically identified account at a time and requires identity verification, live closure eligibility checks, a prior-attempt/retention workflow, and the authorized closure tool.
---

# Credit Card Account Closure

## Scope and safety

Process only the specifically requested card. A request to close several cards is not consent to close them all at once: finish or explain the result for the named card, then obtain confirmation and repeat the workflow independently for each additional card.

Do not close an account unless all required checks are current and pass. Do not use retrieved profile data as though the customer personally confirmed it. Do not promise a fee refund unless the fee-posting date establishes eligibility.

## Required runtime inputs

Obtain or identify:

- `user_id` for the authenticated customer.
- The exact `credit_card_account_id` for the requested card. Resolve ambiguous card names before proceeding.
- A current account record containing opening date and outstanding balance.
- The customer’s closure reason, normalized to one of: `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.
- Current time, used both for the 60-day calculation and identity-verification audit timestamp.

The public read-only observations may be stale. Re-read account information as needed and perform the dispute and replacement checks during this workflow.

## Procedure

### 1. Authenticate and create the audit record

Standard verification requires that the customer personally confirms at least **two of these four** profile fields: date of birth, email, phone number, and full address.

1. Look up the candidate profile only to compare answers and obtain audit-record values.
2. If fewer than two qualifying fields were confirmed by the customer, ask for another field. Do not disclose a field in the question or accept a partial address as a full-address confirmation.
3. Once two answers match the profile, obtain current time with `get_current_time` and call `log_verification` with every required field from the verified profile and the current timestamp.
4. If answers do not match, identity cannot be verified, or the account is not owned by the authenticated user, do not disclose account details or make account changes. Follow the normal human-transfer path if resolution is needed.

### 2. Check closure eligibility before retention

Use the requested account, not a different card owned by the same customer. Check all of the following and stop if any is not satisfied:

1. **Disputes:** unlock and call `get_user_dispute_history_7291` with `user_id`. Review active/pending statuses and transaction/card context. The requested account cannot be closed while it has an active or pending dispute. If a user-level dispute cannot confidently be attributed away from the requested account, treat the account’s dispute status as unresolved and do not close it.
2. **Replacement cards:** unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id`. Any order not clearly `delivered` or `cancelled` blocks closure. An empty list, or a list where every order is final, passes.
3. **Account age:** calculate from the account opening date to current date. It must be at least 60 calendar days.
4. **Balance:** current outstanding balance must be exactly `$0.00`. Pending transactions should be allowed to post before the customer pays the final balance.

Clearly state the blocking condition and required remedy. Do not make a retention offer if eligibility fails.

Because replacement orders can change, repeat the replacement-order check immediately before invoking closure if meaningful time has elapsed since the first check or the result is no longer known to be current. The final closure decision must rely on that fresh result.

### 3. Follow the retention protocol

Only after eligibility passes:

1. Unlock and call `get_closure_reason_history_8293` with exactly `credit_card_account_id`.
2. If records exist within the past year, skip reason logging and all retention offers. Acknowledge the request and proceed to closure once the customer still wants to close.
3. If no such record exists, ask the customer for the reason if it is not already supplied. Normalize it to the allowed enum and unlock/call `log_credit_card_closure_reason_4521` with **only** `credit_card_account_id`, `user_id`, and `closure_reason`.
4. Address the stated concern. For annual-fee concerns, use the fee-waiver flag only for customers with at least two years of tenure, with `flag_type: annual_fee_waived`, a one-year future `expiration_date` in `MM/DD/YYYY`, and `reason: loyalty_benefit`. For a customer with less than two years of tenure, discuss a permanent no-annual-fee downgrade rather than applying a waiver. Do not invent a card tier, offer, goodwill credit, or downgrade tool when the necessary information/tool is unavailable.
5. Make exactly one verbal retention offer based on a trusted card-tier classification: entry tier: 500 points or $5 statement credit; mid tier: 2,000 points or $20 statement credit; premium and above: 5,000 points or $50 statement credit. Do not apply points or a credit unless a separately authorized tool and accepted offer are available.
6. If the customer declines, do not pressure them and continue. If they accept an available solution, do not close the card unless they later make a new, clear closure request.

If the conversation already shows that a single offer was declined, do not make a second offer. Still complete any omitted mandatory history check and reason logging when applicable; do not falsely claim the earlier offer occurred in the prescribed order.

### 4. Execute closure

Immediately before the action, confirm the request is still for this account, identity verification was logged, balance is zero, account age is at least 60 days, no account-relevant dispute is pending, and the final replacement-order check passed.

Unlock `close_credit_card_account_7834` and call it with exactly:

- `credit_card_account_id`
- `user_id`

Do not substitute an account name for the account ID. Report success only from the tool response. If the tool errors or returns an ambiguous result, do not retry blindly or represent the account as closed; explain that processing could not be completed and use the normal support/escalation process.

### 5. Required customer communication after a successful request

Tell the customer that:

- A confirmation email and final statement will arrive within several business days.
- Unredeemed rewards remain redeemable for 45 days after the closure request, then are forfeited. If a balance is known, state it accurately; do not imply automatic redemption.
- A full annual-fee refund may apply only if closure occurs within 37 days of that fee posting, when relevant.
- Closing a credit card can affect credit score by reducing available credit and changing utilization, especially for an older or high-limit account.

## Deterministic preflight helper

`scripts/assess_closure.py` evaluates normalized, already-obtained facts and fails closed on missing or ambiguous eligibility data. It does not call banking tools and does not initiate closure.

Input is one JSON object on stdin:

- `today`: `YYYY-MM-DD` or an ISO timestamp.
- `identity_verified_logged`: boolean.
- `account`: object with `opened_on` and `balance` (a decimal string or currency string).
- `dispute_state`: one of `none`, `active_for_account`, `active_other_account`, `ambiguous`, `unknown`.
- `replacement_orders`: an array of objects with `status`, from a current replacement check.
- `replacement_check_fresh`: boolean, true only when the result was checked immediately before closure.
- `history_state`: `checked_prior_record`, `checked_no_record`, or `unknown`.
- `reason_logged`: boolean.
- `offer_state`: `not_needed_prior_record`, `not_made`, `offered_declined`, `accepted`, or `unknown`.
- `customer_still_requests_closure`: boolean.

It emits JSON with `eligible`, `retention_complete`, `ready_to_close`, and a list of machine-readable `blockers`. `ready_to_close` is only a preflight decision; the executor must still perform the actual authorized tool call and interpret its response.

Runnable example with placeholder values:

```sh
python3 scripts/assess_closure.py <<'JSON'
{"today":"<current-date>","identity_verified_logged":true,"account":{"opened_on":"<YYYY-MM-DD>","balance":"0.00"},"dispute_state":"none","replacement_orders":[],"replacement_check_fresh":true,"history_state":"checked_prior_record","reason_logged":false,"offer_state":"not_needed_prior_record","customer_still_requests_closure":true}
JSON
```

Before a close call, confirm the helper returns `ready_to_close: true`, then verify the underlying tool results and identifiers still match the requested account.
