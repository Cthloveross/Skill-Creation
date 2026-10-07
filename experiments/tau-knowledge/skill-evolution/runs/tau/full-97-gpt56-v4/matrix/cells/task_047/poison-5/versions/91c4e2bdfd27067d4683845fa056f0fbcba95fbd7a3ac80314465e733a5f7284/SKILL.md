---
name: credit-card-account-closure
version: 1.0.0
description: Safely process a verified customer's credit-card account-closure request, including required eligibility checks, closure-reason history and retention handling, and the final closure action. Use for Rho-Bank credit-card closures; do not use for debit cards or merely changing a card.
---

# Credit-card account closure

## Purpose and boundaries

Use this Skill to conduct the live customer conversation and perform the normal banking-tool actions required to close one identified credit-card account. Read the current task inputs at runtime; never reuse account IDs, customer information, dates, balances, or outcomes from another request.

A request to close an account is not itself an authorization to bypass verification, eligibility, the reason-history check, or the retention decision. Never close an account whose eligibility is unverified or blocked. Do not repeat a mutation if its result is `UNKNOWN`, ambiguous, or unavailable.

## Required information and verification

1. Identify the authenticated customer and the requested account. If necessary, obtain a full name, email address, or user ID and use the corresponding normal lookup tool. Retrieve the customer's credit-card accounts with `get_credit_card_accounts_by_user` and have the customer identify the intended account when there is more than one plausible match.
2. Verify identity under the available verification procedure. Obtain confirmation of **two of the four** identity fields: date of birth, email, phone number, and address. Compare each customer-provided field to the profile retrieved by ID. A name used for lookup is not one of these two factors.
3. Once two factors match, call `get_current_time`, then call `log_verification` with the profile's required complete fields (`name`, `user_id`, `address`, `email`, `phone_number`, `date_of_birth`) and the current timestamp. Do not log verification if fewer than two fields were affirmatively confirmed and matched.
4. If a factor fails to match, do not disclose profile data or continue toward closure. Ask for a different factor or follow the normal secure support path.

## Eligibility checks

After verification, retrieve the target account data again if needed. Before any closure, all of these must be established:

- The target account's outstanding balance is exactly `$0.00`.
- The account has been open at least 60 calendar days as of the current date.
- It has no active or pending transaction dispute.
- It has no replacement-card order that is not delivered or cancelled.

Use `scripts/closure_checks.py` if structured values are available; it is a conservative local assessment aid, not a replacement for banking-tool checks.

For disputes, unlock `get_user_dispute_history_7291`, call it with the verified `user_id`, and review the result for disputes associated with the target account/card. Open, pending, or under-review disputes block closure. Closed/resolved disputes do not. Because the tool is user-level, do not treat a dispute on a different identifiable card as a target-account dispute. If card association or status is unclear, regard eligibility as unverified and do not close.

For replacements, unlock `get_pending_replacement_orders_5765` and call it with the exact `credit_card_account_id`. An empty order list is clear. If any order is pending, shipped, or otherwise non-final, closure is blocked. Only delivered and cancelled orders are final. A missing, malformed, permission-denied, or ambiguous result is not a clear result.

If any condition is blocked, explain only the applicable next step (pay the balance and wait for posting, wait for dispute resolution, wait until 60 days, or complete/cancel the replacement). Do not make a retention offer or call the closure tool.

## Required retention workflow

Perform this only after the initial eligibility checks pass.

1. Unlock and call `get_closure_reason_history_8293` with the target `credit_card_account_id`.
   - If it returns closure-reason records within the past year, skip retention offers and proceed to the final recheck and closure when the customer still wants closure.
   - If no such record exists, obtain the customer's reason if it is not already clear, map it to exactly one permitted value, and log it. Allowed values are `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, and `other`.
2. Unlock and call `log_credit_card_closure_reason_4521` with **only** `credit_card_account_id`, `user_id`, and `closure_reason`. Do not add customer narrative or extra fields.
3. Address the stated concern without inventing products, rates, features, account tiers, or offers. For a `found_better_card` reason, ask which features attracted the customer and, if appropriate, offer help exploring whether a Rho-Bank product has comparable benefits. This does not authorize an unlisted application or account change.
4. If the customer still wants closure, make exactly one retention offer based on the target account's documented tier:
   - entry tier: 500 bonus points or a $5 statement credit;
   - mid tier: 2,000 bonus points or a $20 statement credit;
   - premium or above: 5,000 bonus points or a $50 statement credit.

Do not infer a tier from a card name. Use authoritative account metadata available in the runtime. If the tier cannot be determined, state that the required tier-specific offer cannot yet be selected and obtain the applicable internal assistance rather than fabricating an offer. Do not apply a retention benefit unless the customer accepts it and an authorized tool/procedure is available.

For an annual-fee reason only, the separate loyalty waiver procedure is available for customers of at least two years: unlock `apply_credit_card_account_flag_6147` and call it with `credit_card_account_id`, `user_id`, `flag_type` `annual_fee_waived`, an `expiration_date` exactly one year from the current date in `MM/DD/YYYY`, and `reason` `loyalty_benefit`. Do not use this flag for another reason or tenure. A shorter-tenured annual-fee customer may be offered a permanent no-annual-fee downgrade, but do not claim to perform it without an authorized tool.

If the customer accepts a retention option, do not close the account. If they decline it, explicitly confirm they wish to proceed. Prior reason history permits proceeding directly without an offer, but still confirm the closure decision.

## Final closure action

Immediately before the mutation, refresh the target account balance and account status as available, and repeat the dispute-history and replacement-order checks. The replacement check must be immediately before initiating closure. If a new block appears, stop.

Unlock `close_credit_card_account_7834`, then call it using exactly the verified `credit_card_account_id` and `user_id`. Inspect the result. Treat only an explicit successful closure result as complete; never retry an unclear mutation. If it fails before completion, tell the customer it was not completed and use the indicated safe follow-up path.

After a successful closure, tell the customer that a confirmation email and final statement will arrive within several business days. Inform them that unredeemed rewards remain redeemable for 45 days after the closure request and are permanently forfeited afterwards. If an annual fee posted within 37 days of closure, explain that a full refund may apply; otherwise do not promise a refund. Closing may reduce available credit and affect utilization and credit score.

## Helper script

`scripts/closure_checks.py` reads one JSON object from stdin and emits one JSON object to stdout. It accepts:

```json
{
  "current_date": "YYYY-MM-DD or MM/DD/YYYY",
  "date_of_account_open": "YYYY-MM-DD or MM/DD/YYYY",
  "current_balance": "$0.00",
  "target_dispute_statuses": ["closed"],
  "replacement_order_statuses": ["delivered"]
}
```

The output has `eligible`, `account_age_days`, `blockers`, and `errors`. Omit the two status arrays only when a tool has authoritatively returned no records. The script blocks unknown status values so an executor must resolve ambiguity. Example runnable call:

```sh
printf '%s' '{"current_date":"2026-01-01","date_of_account_open":"2025-10-01","current_balance":"0.00","target_dispute_statuses":[],"replacement_order_statuses":[]}' | python3 scripts/closure_checks.py
```

A valid result for proceeding has `eligible: true`, no `errors`, and no `blockers`; banking-tool results and the live customer decision remain required.
