---
name: credit-card-account-closure
version: 1.0.0
description: Safely process a verified customer's request to close one specific credit-card account, including account-scoped eligibility checks, required retention handling, just-in-time replacement-order verification, closure, and required customer communications.
---

# Credit Card Account Closure

Use this Skill when a customer asks to close a credit card. Process **one explicitly selected account at a time**. Do not infer that a request to close multiple cards authorizes closure of every account.

## Required runtime inputs

Obtain at runtime:

- `user_id` and the selected `credit_card_account_id`, with evidence that the account belongs to that user.
- The customer-provided identity confirmations and the profile values needed to compare them.
- Account opening date and current outstanding balance.
- The customer’s closure reason and response to any required retention offer.
- Results of the account-scoped dispute review and the just-in-time replacement-order check.

Do not hardcode customer identifiers, account identifiers, dates, balances, or results from a prior conversation.

## Tool access

Specialized tools named below must be unlocked with `unlock_discoverable_agent_tool` before calling them through `call_discoverable_agent_tool`. Use exactly the documented arguments.

- `get_user_dispute_history_7291` — `{ "user_id": string }`
- `get_pending_replacement_orders_5765` — `{ "credit_card_account_id": string }`
- `get_closure_reason_history_8293` — `{ "credit_card_account_id": string }`
- `log_credit_card_closure_reason_4521` — `{ "credit_card_account_id": string, "user_id": string, "closure_reason": string }`
- `close_credit_card_account_7834` — `{ "credit_card_account_id": string, "user_id": string }`

The closure-reason value must be exactly one of: `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.

## Procedure

### 1. Identify the target without overreaching

1. Locate the customer using information they provide, then retrieve their credit-card accounts.
2. Confirm which single card they intend to close. Confirm its account identifier belongs to the authenticated user and matches the requested card type.
3. If the customer mentioned other cards, acknowledge those as separate future requests; do not act on them now.

### 2. Complete identity verification before account action

1. Retrieve the user profile using the established `user_id` only to compare customer-supplied values.
2. Require the customer to confirm at least **two of the four** identity fields: date of birth, email, phone number, and residential address. A name lookup, information visible in a profile, or an agent repeating profile data is not a customer confirmation.
3. If fewer than two fields are confirmed, ask for another one of the four fields and stop. Do not log verification, make offers, log a closure reason, or close the account.
4. Once two fields match, obtain the current time and call `log_verification` with all required profile fields, `user_id`, and the timestamp. This is the auditable completion of verification.

### 3. Check closure eligibility

The account may proceed only when all of these are true:

- outstanding balance is exactly `$0.00`;
- account age is at least 60 days as of the current date;
- there are no active or pending disputes **for the selected account**; and
- there are no pending replacement cards.

Use `get_user_dispute_history_7291` with the verified `user_id`. Review each returned dispute’s status and transaction/card context to determine whether it belongs to the selected account. Any active, open, pending, or under-review dispute for that account blocks closure. If account association or status is ambiguous, do not treat it as clear; obtain clarification or escalate according to operating procedures.

Use `scripts/evaluate_closure_eligibility.py` to consistently evaluate the known account facts if desired. It does not replace tool calls or human judgment about dispute account association.

If a requirement is not met, explain the specific blocker and what must happen first (pay balance, wait until 60 days, resolve dispute, or complete/cancel replacement). Do not perform retention steps or invoke closure.

### 4. Follow retention protocol after eligibility passes

1. Unlock and call `get_closure_reason_history_8293` for the selected account.
2. If a closure-reason record exists within the previous year, skip retention offers and proceed to the final replacement check. Tell the customer that their closure request will proceed.
3. Otherwise, ask for the reason if it has not already been provided. Map it faithfully to one allowed reason, confirm an unclear mapping with the customer, and call `log_credit_card_closure_reason_4521` with only its three allowed arguments.
4. Address the stated concern and make one tier-appropriate retention offer:
   - entry tier: 500 points or $5 statement credit;
   - mid tier: 2,000 points or $20 statement credit;
   - premium and above: 5,000 points or $50 statement credit.
5. If the customer accepts an offer or needs time to decide, do not close the account. If they decline, continue without pressure.

For annual-fee concerns, apply the separate retention policy before closure: customers of 2+ years may be offered a one-year annual-fee waiver; those below 2 years may be offered a same-category no-annual-fee downgrade. Use only the separately documented tools and only when the customer accepts.

### 5. Recheck replacement orders immediately before closure

Immediately before calling the closure tool, unlock and call `get_pending_replacement_orders_5765` with the selected account ID. This check must be fresh even if eligibility was checked earlier.

- An empty order collection passes.
- Orders all clearly `delivered` or `cancelled` pass.
- Any other status, including `pending` or `shipped`, blocks closure.
- An empty, malformed, or ambiguous response that cannot be reliably interpreted must be retried or escalated; never assume it passes.

Use `scripts/evaluate_replacement_orders.py` to normalize a structured tool response when useful.

### 6. Close and communicate

Only after successful verification, eligibility, retention handling, and the immediate replacement check:

1. Unlock and call `close_credit_card_account_7834` using exactly the verified `credit_card_account_id` and `user_id`.
2. Report the actual tool result. Do not claim closure if the tool errors or returns an unclear outcome.
3. On success, tell the customer that a confirmation email and final statement will arrive within several business days.
4. Tell them that unredeemed rewards remain redeemable for 45 days after the closure request and are then forfeited. For cash-back cards whose balances are stored as points, one point is worth $0.01 when redeemed as a statement credit or checking-account credit. State any card-specific benefit impact supported by policy; for example, closing a card can end a linked savings APY bonus.
5. If relevant, explain that a full annual-fee refund may apply when closure occurs within 37 days of the fee posting. Do not promise a refund without confirming timing.

## Fail-safe behavior

- Missing verification, unknown balance, unverified age, unclear dispute scope/status, failed tool calls, or unclear replacement results are blockers, not passes.
- Never substitute an account-level identifier with a card-level identifier.
- Never add parameters to `log_credit_card_closure_reason_4521`.
- If a tool reports access, malformed input, or system failure, correct the identifier or retry as appropriate; if it remains unresolved, escalate rather than closing.

## Helper script interface

Both scripts read one JSON object from stdin and emit one JSON object to stdout. They are advisory validators: the executor must still obtain fresh runtime data and perform the documented tool calls.

Example:

```json
{"as_of_date":"2025-01-01","date_of_account_open":"2024-10-01","current_balance":"0.00","disputes_scope_confirmed":true,"account_dispute_statuses":[],"replacement_orders_checked":true,"replacement_order_statuses":[]}
```

Run `scripts/evaluate_closure_eligibility.py` with this schema. A valid result has `eligible: true`; otherwise its `blockers` list explains why not to continue.
