---
name: credit-card-account-closure
version: 1.0.0
description: Safely process a verified customer's request to close one specific Rho-Bank credit-card account, including eligibility checks, required retention workflow, the closure action, and required customer communication. Use when a customer asks to close a credit card.
---

# Credit Card Account Closure

## Scope and safety

Process only the specifically requested card for the authenticated customer. Never infer that a request to close several cards authorizes closing all accounts. Do not call the closure tool unless identity is logged as verified and every closure prerequisite is satisfied.

A closure requires all of the following:

- outstanding balance is exactly $0.00;
- no active or pending dispute affecting the target account;
- account has been open for at least 60 days;
- no pending replacement card order (only delivered or cancelled orders are final);
- the customer has been identity-verified using two of the four profile fields: date of birth, email, phone number, and address.

Use only the declared banking tools. Unlock a discoverable agent tool before calling it. Tool responses are authoritative; do not treat an unavailable, ambiguous, malformed, or failed response as a successful check.

## Runtime inputs to collect

1. Obtain an account locator and the customer's closure reason. An email address or user ID may locate the profile.
2. Look up the profile and then list that user's credit-card accounts. Match the requested card by its actual card type and confirm its `user_id` matches the verified customer.
3. Ask for enough identity fields to compare against the profile. Once two fields match, obtain the current timestamp and record verification with `log_verification`. That tool requires all profile fields (`name`, `user_id`, `address`, `email`, `phone_number`, `date_of_birth`) plus `time_verified`; pass the retrieved profile values, not merely the fields spoken in the conversation.
4. If identity cannot be verified, stop without discussing account-specific data or performing closure actions.

## Required operational sequence

### 1. Establish eligibility

After verification, retrieve the target account details and determine balance and opening date. Calculate age against the current date; use `scripts/closure_precheck.py` if a deterministic precheck is useful.

For disputes:

1. Unlock `get_user_dispute_history_7291`.
2. Call it with `{"user_id":"<verified user id>"}`.
3. Inspect the returned dispute records. A record in an active/non-final status such as `open` or `under_review` blocks closure when it concerns the target card. Use account/card transaction context when supplied. If an active record cannot safely be attributed or excluded, do not assume it is unrelated; obtain clarification or route for review rather than closing.

For replacement cards:

1. Unlock `get_pending_replacement_orders_5765`.
2. Call it with `{"credit_card_account_id":"<target account id>"}`.
3. An empty order collection passes. Any order that is not clearly `delivered` or `cancelled` blocks closure.

If any eligibility condition fails, explain the specific blocker and what must be resolved. Do not make a retention offer and do not call the closure tool.

Because replacement status can change, run the replacement-order check again immediately before the closure call whenever another substantive retention or conversation step occurred after the first check.

### 2. Follow the retention protocol

Only after eligibility is clear:

1. Unlock `get_closure_reason_history_8293` and call it with the target `credit_card_account_id`.
2. If a record exists for this account within the past year, skip all retention offers and proceed to the final replacement check and closure if the customer continues to request closure.
3. Otherwise, normalize the customer's stated reason to exactly one accepted value and unlock/call `log_credit_card_closure_reason_4521` with **only**:
   ```json
   {"credit_card_account_id":"<target account id>","user_id":"<verified user id>","closure_reason":"<accepted reason>"}
   ```
   Accepted reasons are `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, and `other`.
4. Address the reason and make one appropriate retention offer only if the customer has not already clearly declined offers. If the customer explicitly declines an offer in advance or after it is made, respect that decision without pressure.

For annual-fee concerns, offer a one-year annual-fee waiver only when two or more years of customer tenure is established; otherwise offer the permitted no-annual-fee downgrade. A waiver uses `apply_credit_card_account_flag_6147` with `flag_type` `annual_fee_waived`, `reason` `loyalty_benefit`, and an `expiration_date` exactly one year from today in `MM/DD/YYYY` format. Do not guess customer tenure or card tier. For other reasons, use the documented tailored discussion. Where the tier is established, the one retention offer is: entry 500 points or $5 statement credit; mid-tier 2,000 points or $20; premium-and-above 5,000 points or $50.

### 3. Close the account

Immediately before closing, confirm the final replacement-order result still passes. Then unlock `close_credit_card_account_7834` and call it with exactly the authenticated customer and target account:

```json
{"credit_card_account_id":"<target account id>","user_id":"<verified user id>"}
```

Do not repeat a closure request if its result is unknown, ambiguous, or failed. Report the tool's actual result and preserve any reported confirmation details.

## Required customer communication after a successful closure request

Tell the customer that a confirmation email and final statement will arrive within several business days. Tell them unredeemed rewards remain redeemable for 45 days after the closure request and are forfeited afterward. If an annual fee was posted recently, explain that a full refund may apply only when closure occurs within 37 days of that fee charge.

For cash-back cards, including the Green Rewards Card, database rewards labeled `points` represent cash back at $0.01 per point. State the cash value only from the current account record, and do not imply rewards were redeemed unless a redemption action actually occurred. If helpful, mention that closing a card can reduce available credit and may affect credit utilization and credit score.

## Precheck helper

`scripts/closure_precheck.py` accepts one JSON object on stdin and emits one JSON object on stdout. Its input schema is:

- `as_of` (required): current date or timestamp;
- `date_of_account_open` (required): account opening date;
- `current_balance` (required): a decimal number or formatted currency string;
- `target_disputes` (required): dispute records already determined to concern the target account;
- `replacement_orders` (required): replacement-order records for the target account.

It reports account age, recognized eligibility blockers, and `eligible`. It is a consistency aid, not a substitute for tool calls, identity verification, or retention workflow. A runnable invocation using a runtime-created JSON input file is:

```sh
python3 scripts/closure_precheck.py < runtime_precheck.json
```

Validate that `input_valid` is true and that `eligible` is true before treating the four mechanical conditions as passed. An empty `target_disputes` list means the executor found no target-account disputes; do not use an empty list to discard ambiguous active user-level disputes.
