---
name: credit-card-closure-with-retention
version: 1.0.0
description: Process a requested closure of one verified Rho-Bank credit card account, including eligibility checks, required retention handling, final replacement-order check, closure, and customer notifications. Use when a customer asks to close a specific credit card; process each requested card independently.
---

# Credit Card Closure With Retention

## Scope and safety

Use this skill only for the specific card the authenticated customer currently asks to close. Do not close other cards merely because the customer said they eventually want to close several. Obtain a separate selection, eligibility review, and final confirmation for every account.

Do not call the closure tool unless every prerequisite below is confirmed. If a tool response is missing, ambiguous, malformed, or fails, do not infer that the condition passed; explain the delay and resolve or escalate through normal support handling.

## Inputs and runtime state

Collect or retain the following at runtime:

- Customer-selected `credit_card_account_id` and authenticated `user_id`.
- Identity-verification state and verification timestamp.
- Account type, opening date, current balance, and reward balance from the current account lookup.
- Current dispute history for the `user_id`.
- Current replacement-order results for the selected account.
- Whether a closure-reason record exists for this account in the preceding year.
- Customer's reason, mapped to one permitted reason value when logging is required.
- Whether the customer has already received the required retention offer and has explicitly declined it.

A lookup by name, email, or account ID locates a profile; it is not identity verification. Verify two of these four customer-supplied fields against the profile: date of birth, email, phone number, and address. Once two match, call `log_verification` with all required profile fields and the current timestamp. Never ask the customer to disclose information already presented as a confirmation unless needed to meet the two-field rule.

## End-to-end procedure

### 1. Identify the exact account and verify identity

1. Locate the user and retrieve their credit card accounts using the available standard lookup tools.
2. Confirm the requested card type maps to exactly one account. If it does not, ask the customer to select the account; do not guess.
3. Complete the two-of-four identity verification described above. Call `get_current_time` immediately before `log_verification`, then log the successful verification.
4. Confirm the customer still wants to close this selected account. A clear existing request can serve as confirmation unless the conversation changed course.

### 2. Obtain eligibility facts and evaluate them

The account may be closed only when all conditions are true:

- Current outstanding balance is exactly `$0.00`.
- There are no active or pending transaction disputes.
- The account has been open at least 60 calendar days.
- There is no pending replacement-card activity.

Unlock and call `get_user_dispute_history_7291` with only `user_id`. Treat statuses such as `open`, `pending`, `under_review`, or `active` as blocking. A dispute with an unknown/nonfinal status also requires review rather than proceeding.

Use the current account record for balance and opening date. Normalize the data and, if useful, run:

```text
python scripts/closure_gate.py <<'JSON'
{"today":"YYYY-MM-DD","account":{"date_of_account_open":"MM/DD/YYYY","current_balance":"$0.00"},"disputes":[],"replacement_orders":[]}
JSON
```

The script is a local decision aid only; it does not make banking calls and cannot replace current tool checks.

If any eligibility condition fails, tell the customer precisely what must be resolved. Do not make a retention offer and do not close the account.

### 3. Apply the retention protocol after basic eligibility passes

1. Unlock and call `get_closure_reason_history_8293` with `credit_card_account_id`.
2. If it reports a record within the past year, skip reason logging and retention offers. Inform the customer that their request will proceed, subject to the final replacement check.
3. If no such record exists, obtain the reason and map it to exactly one of:
   - `annual_fee`
   - `not_using_card`
   - `found_better_card`
   - `unhappy_with_rewards`
   - `simplifying_finances`
   - `negative_experience`
   - `other`
4. Unlock and call `log_credit_card_closure_reason_4521` with **only** `credit_card_account_id`, `user_id`, and `closure_reason`.
5. Address the reason appropriately, then make one retention offer based on the verified card tier. Do not invent a tier or an unavailable crediting tool. The documented offers are 500 points or $5 for entry tier, 2,000 points or $20 for mid-tier, and 5,000 points or $50 for premium-and-above cards.
6. If the customer declines, do not pressure them. Continue to closure. If they accept a retention option but no authorized execution method is available, do not claim it was applied; handle the unavailable fulfillment through the normal supported workflow.

For an annual-fee concern, a customer with at least two years of tenure may be offered a one-year fee waiver. Only after acceptance, unlock and call `apply_credit_card_account_flag_6147` using `flag_type: "annual_fee_waived"`, `reason: "loyalty_benefit"`, and an `expiration_date` exactly one year from the current date in `MM/DD/YYYY` format. For tenure under two years, offer a same-category no-annual-fee downgrade instead of a waiver. With explicit consent, use `downgrade_credit_card_3847` and the permitted personal or business target card type. A downgrade resolves the closure request; do not also close the account unless the customer again explicitly requests closure.

### 4. Immediately before closure, check replacements again

This is a mandatory final freshness check even if replacement information was reviewed earlier. Unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id` immediately before the closure call.

An empty order collection passes. Any order that is not clearly `delivered` or `cancelled` blocks closure, including `pending` and `shipped`. Record the outcome in the case notes according to the operating environment. If blocked, explain that the replacement must be delivered or cancelled first.

### 5. Close the selected account

After verified identity, zero balance, sufficient age, no active/pending dispute, a passing final replacement check, and completed/skipped retention protocol:

1. Unlock `close_credit_card_account_7834`.
2. Call it using `credit_card_account_id` and `user_id` for the selected authenticated account.
3. Report completion only if the tool confirms it. If it fails or is unclear, do not represent the account as closed.

## Required customer communication after a confirmed closure

Tell the customer:

- A confirmation email and final statement will arrive within several business days.
- Unredeemed rewards may be redeemed for 45 days after the closure request; afterward they are forfeited. Where the selected card's rewards are represented as cash-back points, they redeem at `$0.01` per point.
- If an annual fee was posted recently, a full refund may apply when closure occurs within 37 days of the fee charge.
- Closing a card can affect credit utilization and credit score.
- If the account is linked to a Green Account savings benefit, closing or unlinking the card can end its card-related APY benefit; have the customer review their current account details rather than promising a rate not confirmed for the linkage.

## Local helper interface

`scripts/closure_gate.py` reads one JSON object from stdin and emits one JSON object to stdout.

Input schema:

```json
{
  "today": "YYYY-MM-DD",
  "account": {
    "date_of_account_open": "MM/DD/YYYY or YYYY-MM-DD",
    "current_balance": "$0.00 or numeric string"
  },
  "disputes": [{"status": "closed"}],
  "replacement_orders": [{"status": "delivered"}]
}
```

`disputes` and `replacement_orders` may be empty arrays but must be present after their respective current tool checks. The output contains `eligible`, `account_age_days`, `blocking_reasons`, and `review_reasons`. Proceed only when `eligible` is true and `review_reasons` is empty, and only after the live final replacement check required above.
