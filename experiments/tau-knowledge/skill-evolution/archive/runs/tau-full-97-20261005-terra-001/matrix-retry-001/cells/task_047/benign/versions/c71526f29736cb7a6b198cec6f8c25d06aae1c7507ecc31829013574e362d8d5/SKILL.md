---
name: credit-card-account-closure
version: 1.0.0
description: Safely handle a verified customer's credit-card closure request, including eligibility checks, required retention handling, and the final closure action. Use for any request to close a credit card account when internal account and discoverable banking tools are available.
---

# Credit Card Account Closure

Use this Skill to guide a closure request from identification through an approved closure. Do not close an account based only on a name, account type, or an account lookup: complete standard identity verification first.

## Runtime inputs and outputs

At runtime, obtain the authenticated user's identity information, credit-card accounts, current date/time, and results from the required banking tools. Never use account IDs, personal data, dates, balances, or tool results from an earlier case as inputs for a new case.

The included `scripts/assess_closure.py` accepts a **structured, already-observed** case snapshot on stdin and emits a deterministic eligibility/next-step assessment on stdout. It neither calls banking tools nor performs a closure. See the script docstring for the JSON schema.

Example invocation through the packaged script runner:

```json
{"today":"YYYY-MM-DD","identity_verified":true,"account":{"account_id":"<id>","user_id":"<id>","date_of_account_open":"YYYY-MM-DD","current_balance":"0.00"},"disputes":[],"replacement_orders":[],"closure_reason_history":[]}
```

Validate that the output has `valid: true` before relying on it. A `blocked` result means do not make a retention offer or call the closure tool. The script reports only facts supplied in its input; unknown or malformed information remains a blocker requiring clarification or a reliable tool result.

## Procedure

### 1. Locate the intended account and verify identity

1. If necessary, ask for a name or email, retrieve the user record, and retrieve that user's credit-card accounts. Confirm which account the customer means if there is ambiguity.
2. Verify identity under standard procedures by confirming at least two of the four stored fields: date of birth, email, phone number, and address.
3. After successful verification, obtain the current timestamp and call `log_verification` with all required stored identity fields, the authenticated `user_id`, and the timestamp. Do not treat a name or an account number alone as verification.
4. Ensure the target account belongs to the verified user. Use its account-level identifier, not a card-level identifier.

If identity cannot be verified, do not disclose account details or take closure actions. Request usable verification information or follow the applicable human-transfer process.

### 2. Check closure eligibility before retention

Perform these checks before retention. Use current results, not assumptions from old account data:

1. **Disputes:** unlock and call `get_user_dispute_history_7291` with `user_id`. Any active or pending dispute blocks closure. Treat clearly non-final statuses such as `open`, `pending`, or `under_review` as blocking; if status is missing or ambiguous, do not proceed until resolved.
2. **Replacement cards:** immediately before any final closure action, unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id`. An empty order list passes. If any order is not clearly `delivered` or `cancelled` (for example, pending or shipped), closure is blocked. Recheck immediately before the final closure call if time or intervening workflow makes the prior result stale.
3. **Age:** calculate calendar age from the account opening date. The account must be open at least 60 days.
4. **Balance:** the current outstanding balance must be exactly $0.00. Pending transactions must post and the full balance must be paid before closure.

For any failure or unknown result, explain the specific condition to resolve and stop; do not attempt retention offers or closure. Record check outcomes in the appropriate case record when that capability is available.

### 3. Apply the retention protocol

Only after all eligibility requirements pass:

1. Unlock and call `get_closure_reason_history_8293` with the target `credit_card_account_id`.
2. If the account has a closure-reason record within the previous year, skip retention offers. Tell the customer that you will proceed with the closure request, subject to the final replacement-order recheck, and go to Step 4.
3. Otherwise, identify the customer's reason. If their stated reason maps to a supported value, unlock and call `log_credit_card_closure_reason_4521` with exactly `credit_card_account_id`, `user_id`, and one of:
   `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.
   Do not add parameters. Ask a focused follow-up if the reason is unclear.
4. Address the concern without making unsupported claims:
   - For `found_better_card`, ask which rewards or benefits matter most and discuss any relevant current card benefits supported by account/card documentation.
   - For annual-fee concerns, a customer of at least two years may receive a one-year waiver using `apply_credit_card_account_flag_6147` with `flag_type: annual_fee_waived`, a date one year from today in `MM/DD/YYYY`, and `reason: loyalty_benefit`. For less than two years, offer a same-category downgrade to the documented no-annual-fee card if the customer wants it.
   - For other reasons, use the documented tailored discussion; escalate service complaints where warranted.
5. If the customer still wants to close, make **one** retention offer according to the card tier. Entry tier: 500 points or $5 statement credit; mid tier: 2,000 points or $20 statement credit; premium and above: 5,000 points or $50 statement credit. Do not pressure the customer.
6. If the customer accepts an alternative, complete only the applicable documented action (for example, a downgrade) and do not close the account. If they decline the retention offer, proceed. If they have prior closure-reason history, no offer is required.

### 4. Close and communicate

1. Confirm the customer still wants the specified account closed.
2. Run the replacement-order check immediately before closure and stop if it now blocks the request.
3. Unlock and call `close_credit_card_account_7834` with the verified `credit_card_account_id` and `user_id` only as documented. Do not claim success unless the tool returns success.
4. On successful closure, explain that a confirmation email and final statement arrive within several business days. Inform the customer that remaining rewards may be redeemed for 45 days after the closure request, then are forfeited. If an annual fee was posted within 37 days of closure, advise that a full refund may apply; otherwise do not promise a refund.

## Error handling

- If a specialized tool cannot be unlocked, returns access/technical errors, or provides an incomplete/ambiguous result, do not infer that its check passed. Retry only where appropriate and otherwise transfer or escalate with a concise summary.
- Do not use a dispute result for a different user or a replacement-order result for a different account.
- If the customer asks to close a different account mid-workflow, reconfirm the target and repeat account-specific checks.
- Never invoke the closure tool before identity verification, all eligibility checks, required retention decision handling, and the final replacement-order check.
