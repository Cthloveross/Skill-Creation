---
name: credit-card-account-closure
version: 1.0.0
description: Safely verify, retain when required, and close a customer's credit card account. Use for authenticated requests to close a credit card, including eligibility checks, pending-dispute and replacement-order checks, retention handling, and post-closure communication.
---

# Credit Card Account Closure

Use this Skill when a customer asks to close a credit card account. The executor performs all banking actions with its normal banking tools; packaged scripts only assess supplied facts and never close an account.

## Required controls

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this workflow specifically:

1. Verify the requester using **two of four** customer-provided factors: date of birth, email address, phone number, or street address. A name used to locate a profile does not count as one of these factors. Match each provided factor to the trusted customer record.
2. Confirm the requester is the authenticated customer and that the selected credit-card account belongs to that customer.
3. Obtain the current timestamp and call `log_verification` only after successful two-factor verification. Supply every required field from the trusted customer record and that timestamp.
4. Never treat a customer assertion that there are no disputes or replacement orders as a substitute for the required system checks.
5. Do not call the closure tool unless verification has been logged, all closure eligibility conditions are evidenced, and the retention workflow permits proceeding.

## Closure eligibility

The selected account must meet every condition immediately before closure:

- Outstanding balance is exactly `$0.00`.
- There are no active or pending transaction disputes for the selected account.
- The account has been open at least 60 days.
- There is no pending replacement card order. An order is clear only when every returned order is delivered or cancelled; any other or ambiguous status blocks closure.

If any condition is not met, explain the specific blocker and do not make a retention offer or attempt closure. If a required lookup is unavailable, incomplete, or cannot be associated to the selected account, do not infer eligibility; resolve or escalate the missing evidence.

## Tool-assisted procedure

1. **Identify the account.** Locate the authenticated customer's accounts and have them identify the intended card if more than one account could match. Confirm the selected `credit_card_account_id`, its card type, ownership, open date, and current balance.
2. **Verify and audit identity.** Complete the required two-factor process above, obtain current time, then call `log_verification`.
3. **Perform eligibility checks.** Unlock and use the following discoverable tools as needed:
   - `get_user_dispute_history_7291` with `user_id`. Review statuses and transaction/card context. Only use results as clearance when the account association is complete. Open, pending, under-review, or otherwise non-final disputes for the selected account block closure.
   - `get_pending_replacement_orders_5765` with `credit_card_account_id`. Any order not clearly `delivered` or `cancelled` blocks closure.
   - Use the account record and current date to establish that the account age is at least 60 days; ensure balance is `$0.00`.
4. **Check retention-attempt history only after eligibility passes.** Unlock and call `get_closure_reason_history_8293` with only `credit_card_account_id`.
   - If it reports a closure-reason record within the past year, skip reason logging and all retention offers. Respect the customer's request and proceed to closure.
   - If it reports no such record, ask for the reason, map it to exactly one allowed value, and unlock/call `log_credit_card_closure_reason_4521` with **only** `credit_card_account_id`, `user_id`, and `closure_reason`.
   - Allowed reason values: `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, `other`.
5. **Address the stated concern and make one offer when required.** Tailor the discussion to the reason, then make one retention offer for the account tier:
   - Entry tier: 500 bonus points or a $5 statement credit.
   - Mid tier: 2,000 bonus points or a $20 statement credit.
   - Premium or above: 5,000 bonus points or a $50 statement credit.

   For annual-fee concerns, a customer with at least two years of tenure may be offered a one-year waiver. If they accept, unlock/call `apply_credit_card_account_flag_6147` with `credit_card_account_id`, `user_id`, `flag_type` of `annual_fee_waived`, an `expiration_date` exactly one year from the current date in `MM/DD/YYYY`, and `reason` of `loyalty_benefit`. For shorter tenure, discuss a permanent no-annual-fee downgrade that preserves history. Do not apply an offer without customer acceptance.

   If the customer declines the retention offer and still wants closure, do not pressure them. If prior history required retention to be skipped, likewise proceed without an offer.
6. **Close only when permitted.** Unlock and call `close_credit_card_account_7834` with exactly the selected `credit_card_account_id` and authenticated `user_id`. Treat the account as closed only after a successful tool result. If the closure tool fails or returns an ambiguous result, do not claim completion; report the failure and use normal escalation procedures if it cannot be resolved.
7. **Provide completion information.** On successful closure, tell the customer that a confirmation email and final statement will arrive within several business days. Remaining rewards may be redeemed for 45 days after the closure request, after which they are forfeited. If an annual fee posted within 37 days of closure, the customer is eligible for a full refund; do not promise a refund when the fee-posting date is unknown or outside that window. Explain, if useful, that closure can reduce available credit and affect credit utilization and credit score.

## Deterministic eligibility assessment helper

`scripts/assess_credit_card_closure.py` evaluates explicitly supplied evidence before a closure call. It is useful after gathering account and tool results, and does not replace the live tool calls or identity-verification audit.

### Input JSON schema

```json
{
  "as_of": "MM/DD/YYYY or YYYY-MM-DD",
  "authenticated_user_id": "string",
  "identity_verified": true,
  "verification_logged": true,
  "account": {
    "account_id": "string",
    "user_id": "string",
    "current_balance": "$0.00",
    "opened_on": "MM/DD/YYYY or YYYY-MM-DD"
  },
  "dispute_check": {
    "performed": true,
    "account_association_complete": true,
    "records": [{"status": "closed", "belongs_to_selected_account": true}]
  },
  "replacement_check": {
    "performed": true,
    "orders": [{"status": "delivered"}]
  },
  "retention": {
    "history_checked": true,
    "prior_attempt_within_year": false,
    "reason": "found_better_card",
    "reason_logged": true,
    "card_tier": "mid",
    "offer_presented": true,
    "customer_decision": "declined",
    "customer_wants_close": true
  }
}
```

`dispute_check.records` must include an explicit `belongs_to_selected_account` value for each relevant dispute. Any unresolved account association causes `needs_review`. A non-final dispute status or a replacement-order status other than `delivered` or `cancelled` blocks closure.

The helper emits JSON with `eligibility_status` (`eligible`, `ineligible`, or `needs_review`), concrete `eligibility_blockers`, missing evidence, computed account age, retention guidance, and `closure_permitted`. `closure_permitted: true` means the supplied evidence supports making the normal closure-tool call; it does not execute that call.

Run it by supplying a JSON document at runtime, for example:

```sh
printf '%s' "$CLOSURE_INPUT_JSON" | python3 scripts/assess_credit_card_closure.py
```

Validate that `eligibility_status` is `eligible`, `closure_permitted` is `true`, and no `eligibility_blockers` or `missing_evidence` remain before calling `close_credit_card_account_7834`. If any input is absent, malformed, or ambiguous, collect the required source evidence rather than guessing.
