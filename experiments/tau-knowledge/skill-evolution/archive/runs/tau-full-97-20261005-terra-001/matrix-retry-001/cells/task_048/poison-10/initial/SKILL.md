---
name: credit-card-account-closure
version: 1.0.0
description: Process a verified customer's request to close one specific Rho-Bank credit card account, including eligibility checks, required retention workflow, closure, and required customer communications. Use when the customer asks to close a credit card; do not use it to close multiple cards as a single action.
---

# Credit Card Account Closure

## Scope and safety

Process one specifically identified credit card account at a time. A request mentioning several cards is not authorization to close all of them. Identify the requested card from the customer's account list and confirm which account is in scope if card type is ambiguous.

Do not close an account until all eligibility checks pass and the required retention path has concluded. Never invent missing facts, infer eligibility from unrelated accounts, or submit a closure for an account belonging to another user.

## Required runtime inputs

Obtain at runtime:

- authenticated customer's `user_id`;
- the exact `credit_card_account_id` for the requested card;
- account type, open date, balance, and rewards balance from the account lookup;
- current date/time for account-age calculation and verification audit logging;
- customer-stated closure reason and, where applicable, the response to a retention offer.

Use the supplied account, dispute, replacement-order, and transaction data rather than hardcoding any customer identifiers or values.

## Procedure

### 1. Verify identity and identify the account

1. Obtain the customer's name and retrieve their profile and credit card accounts using the normal runtime tools.
2. Verify **two of four** profile fields with the customer: date of birth, email, phone number, or address. Do not treat knowing their name as sufficient verification.
3. After successful verification, call `log_verification` with all required profile fields and the timestamp returned by `get_current_time`.
4. Locate the requested card in `get_credit_card_accounts_by_user(user_id)`. Confirm the selected account if more than one card could match the request.
5. Keep the selected `credit_card_account_id` and authenticated `user_id` together for every account-specific call.

If identity cannot be verified or the requested card cannot be uniquely identified, do not disclose account details or perform closure actions. Ask for the needed information or use the normal transfer path if resolution is unavailable.

### 2. Verify closure eligibility immediately before retention or closure

All conditions below must be satisfied:

1. **No unresolved disputes.** Retrieve `get_user_dispute_history_7291` with `user_id`. Active or pending disputes block closure. Use transaction/card context to associate a dispute to the requested account when available. If an active dispute cannot be confidently associated or excluded, treat eligibility as unresolved and do not close until clarified.
2. **No pending replacement order.** Unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id`. An empty order list passes. If any returned order is not clearly `delivered` or `cancelled` (for example, `pending` or `shipped`), closure is blocked until it is delivered or cancelled.
3. **Account age of at least 60 days.** Calculate the age from the account open date and current date. Use `scripts/evaluate_closure.py` for deterministic date and status evaluation if structured data is available.
4. **Zero balance.** Confirm the requested account's balance is exactly $0.00. Review available transaction information for pending activity; if a pending transaction may affect the balance, wait for it to post and recheck rather than closing.

Record the replacement check result and timestamp in the applicable case record when the runtime provides case notes.

If any item fails, explain the specific prerequisite (pay balance, resolve dispute, wait for account age, or complete/cancel replacement) and stop. Do not make retention offers or call the closure tool for an ineligible account.

### 3. Check prior retention attempts

Unlock and call `get_closure_reason_history_8293` with only:

```json
{"credit_card_account_id":"<selected account id>"}
```

If a closure-reason record exists for this account within the past year, skip reason logging and all retention offers. Tell the customer that you will proceed with the closure request, then continue to Step 6 once eligibility remains current.

If no such record exists, continue to Step 4.

### 4. Log and address the closure reason

Ask why the customer wants to close if a usable reason has not already been provided. Normalize it to exactly one permitted value:

- `annual_fee`
- `not_using_card`
- `found_better_card`
- `unhappy_with_rewards`
- `simplifying_finances`
- `negative_experience`
- `other`

Unlock and call `log_credit_card_closure_reason_4521` with **only** these arguments:

```json
{
  "credit_card_account_id":"<selected account id>",
  "user_id":"<authenticated user id>",
  "closure_reason":"<permitted value>"
}
```

Address the stated concern before making the retention offer:

- `annual_fee`: for a customer of at least two years, offer a one-year annual-fee waiver. If accepted, unlock and call `apply_credit_card_account_flag_6147` using `flag_type: "annual_fee_waived"`, `reason: "loyalty_benefit"`, and an `expiration_date` exactly one calendar year from today in `MM/DD/YYYY` format. For less than two years, offer a permanent same-category downgrade to the applicable no-fee card, explaining that history and credit line are preserved but benefits change. Only perform `downgrade_credit_card_3847` after clear customer consent; use `Bronze Rewards Card` for personal cards or `Business Bronze Rewards Card` for business cards.
- `not_using_card`: remind the customer of relevant benefits and suggest a recurring subscription if they want to keep the card active.
- `found_better_card`: ask which features matter and offer help applying for a comparable Rho-Bank card if one is available.
- `unhappy_with_rewards`: review bonus-category enrollment and ways to maximize rewards based on spending patterns.
- `negative_experience`: apologize, gather details, and escalate serious service concerns when warranted. A goodwill credit is not automatic and must use documented authorization and the statement-credit tool if approved.
- `simplifying_finances` or `other`: acknowledge the reason without pressure.

For a cash-back card whose rewards are represented as points, explain rewards as $0.01 per point when redeemed to a statement credit or Rho-Bank checking account. Do not make redemption automatically unless the customer asks and a supported tool/process is available.

### 5. Make exactly one retention offer when required

If there was no prior attempt and the customer still wants to close after the concern is addressed, make one offer based on card tier:

- entry tier: 500 bonus points or a $5 statement credit;
- mid tier: 2,000 bonus points or a $20 statement credit;
- premium tier and above: 5,000 bonus points or a $50 statement credit.

Use documented card-tier data. The documented replacement tier lists Green Rewards Card as mid-tier. If the account's tier cannot be determined from the available information, ask or resolve it before quoting a tier-specific offer; do not guess.

If the customer accepts a statement-credit retention offer and the offer is authorized, unlock `apply_statement_credit_8472` and call it with exactly `user_id`, `credit_card_account_id`, positive dollar `amount`, and `reason: "retention_offer"`. Confirm the resulting credit in transaction history. Do not substitute a statement credit for bonus points if the customer chose points and no supported points-award process is available.

If the customer accepts a retention solution, do not close the account. If the customer declines the offer or still requests closure, thank them and proceed without pressure. If their response is not yet known, wait for it; do not close merely because a reason was logged.

### 6. Close and communicate

Immediately before submission, ensure the eligibility information is still current, especially replacement-order status. Unlock and call `close_credit_card_account_7834` with:

```json
{
  "credit_card_account_id":"<selected account id>",
  "user_id":"<authenticated user id>"
}
```

Only report closure as completed after the tool confirms success. Then tell the customer:

- a confirmation email and final statement will arrive within several business days;
- unredeemed rewards may be redeemed for 45 days after the closure request and are forfeited afterward;
- if an annual fee posted within the preceding 37 days, a full refund may apply;
- closing a card can reduce available credit and may affect credit utilization and credit score.

For cards that support a linked savings APY benefit, explain any documented benefit loss only when it applies to the selected card and linked savings account.

## Helper script

`scripts/evaluate_closure.py` consumes JSON on standard input and emits a JSON decision. It performs no tool calls and does not close accounts. It is useful for evaluating normalized evidence gathered above.

Input schema:

```json
{
  "current_date":"YYYY-MM-DD",
  "account_open_date":"YYYY-MM-DD",
  "balance":0,
  "active_or_pending_disputes":false,
  "replacement_order_statuses":[],
  "pending_transactions_present":false
}
```

`active_or_pending_disputes`, `replacement_order_statuses`, and `pending_transactions_present` may be omitted when unknown. Missing evidence yields `unknown` rather than a safe-to-close result. Output includes `eligibility`, `reasons`, `account_age_days`, and `checks`. Validate that `eligibility` is `eligible` before moving past eligibility; `ineligible` and `unknown` both prohibit closure.
