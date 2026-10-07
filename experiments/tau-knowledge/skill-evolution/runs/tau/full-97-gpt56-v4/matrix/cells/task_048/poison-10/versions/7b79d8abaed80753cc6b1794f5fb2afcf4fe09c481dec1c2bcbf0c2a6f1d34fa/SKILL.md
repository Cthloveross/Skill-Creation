---
name: credit-card-closure-workflow
description: Safely handle a verified customer's request to close a credit card account. Use for account identification, closure eligibility, mandatory retention handling, and closure processing with Rho-Bank's normal banking tools.
---

# Credit Card Closure Workflow

Use this Skill for a customer who wants to close a Rho-Bank credit card. Treat each requested card as a separate workflow. Do not close an account until identity, eligibility, and the required retention decision are complete.

## Inputs and normal-tool prerequisites

Collect or obtain at runtime:

- The authenticated customer's `user_id` and the specific `credit_card_account_id`.
- The customer’s requested card, unambiguously matched to an account belonging to that user.
- Two matching identity fields out of date of birth, email, phone number, and address.
- The customer’s reason, normalized to one of: `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.

Use the normal user/profile and credit-card-account lookup tools to identify the customer and account. If the card description matches multiple accounts, ask the customer to identify one; never select arbitrarily.

## 1. Verify identity and record it

1. Look up the customer profile using the supplied identifier.
2. Compare at least two customer-provided identity fields with the profile. Do not count a field that was merely displayed to or inferred by the agent.
3. If two fields match, obtain the current timestamp and call `log_verification` with the complete profile fields, `user_id`, and `time_verified`.
4. If verification fails or is incomplete, do not disclose account details or make account changes. Ask for another permitted identity field or use the appropriate support process.

## 2. Check closure eligibility before retention

For the selected account, complete all checks below before logging a reason, making an offer, or closing it:

1. **Balance:** use the account record and require `current_balance` to be exactly $0.00. A nonzero balance blocks closure; tell the customer to pay it in full after pending transactions post.
2. **Account age:** compare the account opening date to the current date. The account must be at least 60 days old.
3. **Disputes:** unlock and call `get_user_dispute_history_7291` with `user_id`. Review the returned disputes for the selected account/transaction context. Any active, open, under-review, pending, or otherwise unresolved dispute blocks closure. A clearly closed/resolved dispute does not block it. If the response cannot establish whether a relevant dispute is resolved, treat eligibility as unconfirmed and do not close.
4. **Replacement cards:** unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id` immediately before starting closure. An empty order collection passes. If any order is not clearly `delivered` or `cancelled` (including pending or shipped), closure is blocked until it is delivered or cancelled.

If one or more checks fail, clearly name the blocking condition(s) and what must be resolved. Do not make a retention offer and do not invoke the closure tool.

## 3. Check prior retention activity

When eligibility passes, unlock and call `get_closure_reason_history_8293` using only `credit_card_account_id`.

- If the account has a closure-reason record within the prior year, do **not** make another retention offer or log a duplicate reason. Tell the customer that the request will proceed, then go directly to Step 6.
- If no such record exists, continue to Step 4.
- If the history result is ambiguous or unavailable, do not assume there was no prior attempt; resolve the tool issue before offering retention.

## 4. Log the reason

Ask for the customer’s primary reason if it has not already been supplied. Normalize it to the allowed enum without changing its meaning; ask a clarifying question if it cannot be mapped safely.

Unlock and call `log_credit_card_closure_reason_4521` with exactly these arguments and no extras:

```json
{
  "credit_card_account_id": "<selected account id>",
  "user_id": "<verified user id>",
  "closure_reason": "<allowed reason enum>"
}
```

## 5. Address the concern and make one offer

First respond appropriately to the stated reason:

- `annual_fee`: for a customer of at least two years, offer a one-year fee waiver; otherwise offer a permanent downgrade to a no-annual-fee card that preserves account history. For a qualifying waiver accepted by the customer, unlock `apply_credit_card_account_flag_6147` and call it with the account ID, user ID, `flag_type` `annual_fee_waived`, a date one year from today in `MM/DD/YYYY`, and reason `loyalty_benefit`.
- `not_using_card`: remind the customer of available benefits and suggest a recurring subscription if appropriate.
- `found_better_card`: ask which features they prefer and offer help applying for a comparable Rho-Bank card if one is available.
- `unhappy_with_rewards`: review available bonus-category enrollment and ways to maximize rewards.
- `negative_experience`: apologize, gather details, and escalate when warranted; a service goodwill credit may be considered under normal policy.
- `simplifying_finances` or `other`: acknowledge the request without pressuring the customer.

If the customer still wants to close, make exactly one tier-specific retention offer: entry tier: 500 points or $5 statement credit; mid tier: 2,000 points or $20 statement credit; premium or above: 5,000 points or $50 statement credit. Use approved account/profile information to establish the card tier; do not invent a tier from a marketing name. If the available tools do not establish it, obtain the tier through the normal supported workflow before quoting a tier-specific offer.

Wait for the customer’s decision. If the customer accepts a retention or downgrade option, do not close the account. If they decline, or there was a prior attempt, proceed without pressure.

## 6. Close and communicate

Immediately before closure, ensure the replacement-card check remains current and eligibility has not changed. Unlock and call `close_credit_card_account_7834` with:

```json
{
  "credit_card_account_id": "<selected account id>",
  "user_id": "<verified user id>"
}
```

Only report closure as complete when the tool confirms it. If the tool fails or returns an uncertain result, do not retry blindly and do not claim success; explain that processing could not be confirmed and use the normal support path.

After confirmed closure, tell the customer:

- a confirmation email and final statement will arrive within several business days;
- remaining rewards may be redeemed for 45 days after the closure request and are forfeited afterward; and
- a full annual-fee refund may apply if closure is within 37 days of the fee posting.

## Example execution sequence

For an eligible, verified account with no closure record in the last year: verify two profile fields and call `log_verification`; inspect the account balance/open date; call the user dispute-history and account replacement-order tools; call closure-reason history; log the normalized reason; address it and make one tier-appropriate offer; after the customer declines, call `close_credit_card_account_7834`; then provide the post-closure notices.

## Validation checklist

Before invoking the closure tool, confirm all of the following: verified identity audit record exists; selected account belongs to the verified user; balance is zero; age is at least 60 days; no unresolved dispute applies; all replacement orders are final or none exist; and either a prior-attempt record justified skipping retention or the reason was logged and the customer declined the single offer. Confirm the closure-tool response before sending a completion message.
