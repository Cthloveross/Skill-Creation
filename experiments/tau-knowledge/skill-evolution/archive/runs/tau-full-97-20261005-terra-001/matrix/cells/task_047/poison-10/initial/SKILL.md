---
name: credit-card-closure-and-retention
version: 1.0.0
description: Safely process a verified customer's credit-card closure request, including eligibility checks, required retention workflow, and final closure communication. Use for a request to close a credit card account; do not use it for a downgrade-only request.
---

# Credit Card Closure and Retention

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety

Use this workflow only for the authenticated cardholder's request to close a specified credit-card account. Never infer an account from a card name when multiple matching accounts are possible. Do not close an account, apply a retention benefit, or downgrade a card without the customer's applicable confirmation.

The executor, not the packaged script, performs banking-tool calls. Use the normal banking tools, unlock a documented discoverable agent tool before calling it, and stop if a tool fails, returns incomplete data, or produces an ambiguous result. Explain the blocker or escalate through the normal support process rather than guessing.

## Required prerequisites

1. **Identity, authority, and ownership:** Obtain and match at least two of date of birth, email, phone number, and mailing address against the customer record. Confirm the requester is authorized and that the selected account belongs to that verified user. Get the current time and create the audit record with `log_verification` only after successful matching.
2. **Correct product:** Retrieve the user's credit-card accounts and identify the requested account by its account-level ID, card type, and matching `user_id`. Reconfirm that this is the account the customer wants closed.
3. **Closure eligibility:** All of the following must be satisfied:
   - Current outstanding balance is exactly $0.00. Pending transactions must post and any balance must be paid before closure.
   - There are no active or pending transaction disputes. A dispute is acceptable only when it is fully resolved.
   - Account age is at least 60 days.
   - There is no pending replacement-card order. An order blocks closure unless every returned order is clearly `delivered` or `cancelled`.
4. **Final confirmation:** Before the irreversible close call, confirm the customer still wants to close the exact account after any required retention interaction. Recheck the current account balance and replacement-order state immediately before the action, because either can have changed.

## End-to-end workflow

### 1. Verify and identify

- Look up the customer using supplied identifying information. Match two identity fields and the full name to a single user record.
- Call `get_current_time`, then call `log_verification` with all required returned profile fields, the verified `user_id`, and that timestamp.
- Call `get_credit_card_accounts_by_user(user_id)` and select only the account that matches the requested card and user. Review its current balance and opening date.
- If identity, authority, ownership, account selection, or any mandatory-control prerequisite cannot be established, do not continue to retention or closure.

### 2. Determine eligibility

- Unlock and call `get_user_dispute_history_7291` with `user_id`. Any open, under-review, pending, active, or otherwise unresolved dispute blocks closure. If the status is unfamiliar or the result is incomplete, treat it as unresolved until clarified.
- Determine account age from the account opening date and current date. It must be at least 60 calendar days.
- Confirm the account balance is $0.00. Do not treat rewards as a balance payment.
- Unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id`. Empty orders are clear; if orders are returned, proceed only if every order is `delivered` or `cancelled`.
- If a requirement fails, state the specific requirement that must be resolved and do not make retention offers or call the closure tool.

### 3. Apply the retention protocol only after eligibility passes

1. Unlock and call `get_closure_reason_history_8293` with the `credit_card_account_id` to determine whether there is a closure-reason record within the past year.
2. If a qualifying prior record exists, skip all retention offers and proceed to the final-decision and closure steps. Do not log a duplicate reason.
3. Otherwise, obtain the customer's reason and normalize it to exactly one of:
   `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.
4. Unlock and call `log_credit_card_closure_reason_4521` with **only** `credit_card_account_id`, `user_id`, and `closure_reason`.
5. Address the concern before making one tier-based retention offer:
   - `annual_fee`: for customers of 2+ years, offer a one-year fee waiver as a loyalty benefit. Apply `annual_fee_waived` with `apply_credit_card_account_flag_6147` only if accepted, using `reason: loyalty_benefit` and an expiration date exactly one year from the current date in `MM/DD/YYYY` format. For less than 2 years, offer a no-annual-fee downgrade instead; do not perform it unless accepted.
   - `not_using_card`: remind the customer of relevant benefits and suggest a recurring subscription to keep the card active.
   - `found_better_card`: ask which features are better and, if applicable, offer help applying for a comparable Rho-Bank card rather than closing the current account.
   - `unhappy_with_rewards`: review bonus-category enrollment and ways to maximize rewards based on spending.
   - `negative_experience`: apologize, gather details, and escalate to a supervisor when warranted; consider a modest goodwill credit for service-related complaints according to normal authorization rules.
   - `simplifying_finances` or `other`: acknowledge the request and continue without pressure.
6. Make exactly one retention offer based on card tier if the customer still wants closure: entry tier = 500 points or $5 statement credit; mid tier = 2,000 points or $20 statement credit; premium and above = 5,000 points or $50 statement credit. The Silver Zoom Card is mid-tier.
7. If the customer accepts a retention offer, perform only the accepted, authorized action and do not close the account. If they decline (or retention was skipped due to prior attempts), thank them and proceed without pressure.

### 4. Optional accepted downgrade

A fee-related downgrade is an alternative to closure, not a closure prerequisite. Verify identity and obtain explicit agreement that benefits will change. Preserve account history and credit line. Use `downgrade_credit_card_3847` only with the account and user IDs plus the appropriate same-category target:

- Personal: `Bronze Rewards Card`
- Business: `Business Bronze Rewards Card`

Do not downgrade a business card to a personal product or vice versa. If the customer declines or later still wants closure, return to the closure decision workflow.

### 5. Final recheck, close, and communicate

- Confirm the final decision to close the identified account.
- Refresh the account record to reconfirm a $0.00 balance. Immediately before initiating closure, repeat `get_pending_replacement_orders_5765` and ensure all orders are absent, delivered, or cancelled. Do not proceed if a dispute status has changed or any result is ambiguous.
- Unlock and call `close_credit_card_account_7834` with exactly:
  - `credit_card_account_id`
  - `user_id`
- Report only the closure outcome returned by the tool. On success, tell the customer that a confirmation email and final statement will arrive within several business days.
- Tell the customer that unredeemed rewards may be redeemed for 45 days after the closure request and are forfeited afterward. For cash-back cards such as Silver Zoom, database points represent cash back at $0.01 per point when redeemed as a statement credit or Rho-Bank checking credit.
- If an annual fee posted recently, explain that a full fee refund may apply when closure occurs within 37 days of that fee charge. Do not promise a refund without confirming the posting date and eligibility.

## Tool use reference

| Purpose | Tool and required arguments |
|---|---|
| Dispute review | `get_user_dispute_history_7291(user_id)` |
| Replacement-order review | `get_pending_replacement_orders_5765(credit_card_account_id)` |
| Prior retention-attempt check | `get_closure_reason_history_8293(credit_card_account_id)` |
| Record a new reason | `log_credit_card_closure_reason_4521(credit_card_account_id, user_id, closure_reason)`; no extra parameters |
| One-year waiver after acceptance | `apply_credit_card_account_flag_6147(credit_card_account_id, user_id, flag_type='annual_fee_waived', expiration_date, reason='loyalty_benefit')` |
| Accepted downgrade | `downgrade_credit_card_3847(credit_card_account_id, user_id, target_card_type)` |
| Close after all gates | `close_credit_card_account_7834(credit_card_account_id, user_id)` |

## Deterministic planning helper

`scripts/closure_plan.py` evaluates normalized, non-sensitive check results and identifies the next safe workflow stage. It does not query tools, make a banking decision, or execute a banking action.

Send one JSON object on standard input (or `run_skill_script` input) with this schema:

```json
{
  "identity_verified": true,
  "account_owner_confirmed": true,
  "balance": "0.00",
  "account_open_date": "YYYY-MM-DD",
  "current_time": "YYYY-MM-DD HH:MM:SS TZ",
  "disputes_checked": true,
  "dispute_statuses": [],
  "replacement_orders_checked": true,
  "replacement_order_statuses": [],
  "history_checked": false,
  "prior_closure_reason_within_year": null,
  "closure_reason": null,
  "closure_reason_logged": false,
  "concern_addressed": false,
  "retention_decision": "pending",
  "final_confirmation": false,
  "preclose_recheck_completed": false
}
```

`dispute_statuses` and `replacement_order_statuses` are status strings extracted from current tool results. `retention_decision` must be `pending`, `accepted`, or `declined`. Omitted or malformed inputs generate `manual_review` items rather than an approval. The script emits JSON with `eligible_now`, blockers, required review items, a `next_stage`, and `closure_action_allowed`. Before treating the output as actionable, the executor must ensure the underlying results are current and perform the tool calls and customer communications described above.
