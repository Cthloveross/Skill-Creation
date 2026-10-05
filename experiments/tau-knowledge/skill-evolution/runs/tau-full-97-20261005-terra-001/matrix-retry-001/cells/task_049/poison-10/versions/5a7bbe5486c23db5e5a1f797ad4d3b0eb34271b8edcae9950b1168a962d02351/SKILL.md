---
name: credit-card-closure-with-retention
version: 1.1.0
description: Process a requested closure of one verified Rho-Bank credit card account, including closure eligibility, required reason-specific and tier-based retention handling, final replacement-order verification, closure, and required customer notices. Use for each specific credit card a customer asks to close.
---

# Credit Card Closure With Retention

## Scope and safety

Use this skill only for the specific card the authenticated customer currently asks to close. Do not close other cards merely because the customer says they intend to close several cards. Each account needs its own selection, current eligibility review, retention decision, final replacement check, and closure request.

Do not call the closure tool unless every required condition below is confirmed. A missing, failed, malformed, stale, or ambiguous tool result does not pass a requirement. Explain the delay and resolve or escalate through normal support handling rather than inferring eligibility.

## Runtime facts to collect

Maintain these facts for the selected account at runtime:

- Authenticated `user_id`, selected `credit_card_account_id`, and completed identity-verification record.
- Current account type, opening date, balance, and rewards balance.
- Current dispute history for the authenticated user.
- Current replacement-order result for the selected account.
- Whether the account has a closure-reason record in the prior year.
- The customer's reason, mapped to an allowed closure-reason value.
- The reason-specific response, tier-based retention offer, and the customer's decision on each.

A profile lookup by name, email, or account ID only locates a profile; it is not identity verification. Verify two customer-supplied fields against the profile from date of birth, email, phone number, and address. After two fields match, call `get_current_time` immediately before `log_verification`, and log the verified profile values and returned current timestamp. Do not treat fields displayed from a lookup as customer confirmation.

## Procedure

### 1. Identify the account and verify identity

1. Locate the user and retrieve the credit-card accounts using normal lookup tools.
2. Confirm that the requested card maps to exactly one account. If it does not, ask the customer to choose; never guess an account ID.
3. Complete the two-of-four identity verification and successfully call `log_verification`.
4. Confirm the customer still wants to close this selected account. A clear current request remains sufficient unless the customer changed course.

### 2. Check basic closure eligibility

Before retention, establish that all of the following are true:

- The current outstanding balance is exactly `$0.00`.
- There are no active or pending transaction disputes.
- The account has been open at least 60 calendar days.
- No replacement order is pending, shipped, or otherwise non-final.

Unlock and call `get_user_dispute_history_7291` using only `user_id`. Treat `open`, `pending`, `under_review`, and `active` statuses as blocking. Treat an unknown or non-final dispute status as requiring review.

Use a current account record for the balance and opening date. For consistent local evaluation, the supplied helper may be used after the relevant tool results are obtained:

```text
python scripts/closure_gate.py <<'JSON'
{"today":"YYYY-MM-DD","account":{"date_of_account_open":"MM/DD/YYYY","current_balance":"$0.00"},"disputes":[],"replacement_orders":[]}
JSON
```

The helper is only a local decision aid; it makes no banking calls and cannot replace a live final replacement-order check.

If any basic eligibility item fails, tell the customer what must be resolved. Do not make a retention offer and do not close the account.

### 3. Determine whether retention is required

1. Unlock and call `get_closure_reason_history_8293` with `credit_card_account_id`.
2. If it reports a record for this account within the past year, skip reason logging and all retention offers. Tell the customer the request can proceed subject to the mandatory final replacement check.
3. If no prior-year record exists, ask for the closure reason if it is not already clear. Map it to exactly one permitted value:
   - `annual_fee`
   - `not_using_card`
   - `found_better_card`
   - `unhappy_with_rewards`
   - `simplifying_finances`
   - `negative_experience`
   - `other`
4. Unlock and call `log_credit_card_closure_reason_4521` with **only** `credit_card_account_id`, `user_id`, and `closure_reason`.
5. Give the applicable reason-specific response, then follow the mandatory tier-based offer sequence in the next section.

### 4. Required retention sequence

For an account with no prior-year closure-reason record, the retention workflow is not complete merely because a tailored solution was offered. If the customer still asks to close after the reason-specific response, make **exactly one** tier-based retention offer and obtain their decision before starting the final replacement check or closure.

Determine the tier from the confirmed product/account configuration. The one offer may present the documented points-or-credit alternatives for that tier:

- Entry tier: **500 bonus points or a $5 statement credit**.
- Mid tier: **2,000 bonus points or a $20 statement credit**.
- Premium and above: **5,000 bonus points or a $50 statement credit**.

Make the offer plainly, for example: “Before I continue, I can make a one-time retention offer of [tier amount] bonus points or a [tier amount] statement credit. Would you like either option, or do you decline and want to continue with closure?” This is one retention offer, not two separate offers.

Wait for the customer's answer. If they decline, thank them without pressure and continue to Step 5. If they accept but no authorized fulfillment method is available, do not state that a benefit was applied; route the fulfillment through the normal supported workflow and do not close unless they subsequently and explicitly request closure again.

#### Annual-fee reason: ordering is mandatory

For annual-fee concerns, first provide the applicable tailored response:

- For customer tenure of two or more years, offer a one-year annual-fee waiver as a loyalty benefit. Only after explicit acceptance, unlock and call `apply_credit_card_account_flag_6147` with `credit_card_account_id`, `user_id`, `flag_type: "annual_fee_waived"`, `expiration_date` exactly one year from the current date in `MM/DD/YYYY` format, and `reason: "loyalty_benefit"`.
- For tenure under two years, offer a permanent same-category no-annual-fee downgrade that preserves account history. Explain benefit changes. Only after explicit consent, use `downgrade_credit_card_3847` with the allowed personal or business no-fee target. A completed downgrade resolves the closure request; do not also close unless the customer makes a new explicit closure request.

**If the customer declines the waiver or downgrade and still wants closure, do not proceed directly to replacement checking or closure.** Make the one required tier-based bonus-points-or-statement-credit offer above, obtain the customer's decision, and only after they decline it proceed to Step 5. The same rule applies if the customer declines any other reason-specific solution while continuing to request closure.

Other reason-specific responses include reminding a customer who is not using the card of relevant benefits, discussing comparable Rho-Bank options for a better-card concern, helping maximize rewards for a rewards concern, and apologizing/gathering details and escalating when warranted for a negative experience. These responses never replace the required tier-based offer when retention is required.

### 5. Perform the fresh final replacement check

Immediately before any closure attempt, unlock and call `get_pending_replacement_orders_5765` with the selected `credit_card_account_id`. This call must occur after the customer's final retention decision and immediately before the closure tool call.

An empty collection passes. Any order not clearly `delivered` or `cancelled` blocks closure, including `pending` and `shipped`. Record the outcome in case notes where supported. If blocked, explain that every replacement must be delivered or cancelled before the account can be closed.

### 6. Close only the selected eligible account

After successful identity verification, zero balance, sufficient account age, no active/pending disputes, completed or properly skipped retention, and a passing fresh replacement check:

1. Unlock `close_credit_card_account_7834`.
2. Call it using exactly the selected `credit_card_account_id` and authenticated `user_id`.
3. State that closure completed only when the tool confirms success. If the tool fails or is unclear, do not represent the account as closed.

## Required customer communication after confirmed closure

Tell the customer:

- A confirmation email and final statement will arrive within several business days.
- Unredeemed rewards may be redeemed for 45 days after the closure request; afterward they are forfeited.
- If an annual fee posted recently, a full refund may apply when closure occurs within 37 days of the fee charge.
- Closing a card can affect credit utilization and credit score.
- If a selected account's rewards are represented as cash-back points, they redeem at `$0.01` per point.
- If the selected card is linked to a Green Account savings benefit, closing or unlinking it can end the card-related APY benefit. Ask the customer to review current account details rather than promising an unverified rate or linkage.

## Local helper interface

`scripts/closure_gate.py` reads one JSON object from standard input and emits one JSON object to standard output. It performs no external calls.

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

`disputes` and `replacement_orders` must be supplied as arrays after current tool checks. Output fields are `eligible`, `account_age_days`, `blocking_reasons`, and `review_reasons`. Proceed only if `eligible` is true and `review_reasons` is empty, then still perform the mandatory live final replacement check in Step 5.
