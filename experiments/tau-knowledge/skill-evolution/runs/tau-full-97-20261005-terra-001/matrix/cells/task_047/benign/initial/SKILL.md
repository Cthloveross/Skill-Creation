---
name: credit-card-closure-workflow
description: Safely process a verified customer's request to close a credit card account. Use for credit-card closure requests requiring eligibility checks, required retention handling, and the final closure action.
---

# Credit Card Closure Workflow

Use this Skill to process a requested credit-card account closure without closing the wrong account, bypassing eligibility requirements, or applying retention actions without consent. All account facts and tool responses must be obtained at runtime; do not reuse identifiers or values from a prior case.

## Required runtime inputs

Obtain or identify:

- The authenticated customer's `user_id`.
- The specific `credit_card_account_id` the customer wants to close.
- The customer's confirmed closure reason, when retention is applicable.
- Current time, for the verification audit record and date-based checks.
- Current account balance and account-open date.

If multiple cards exist, identify the requested card by its displayed card type and confirm with the customer before taking an account-specific action. Never infer a requested account from transaction history alone.

## 1. Verify identity before account action

Use standard verification. The available `log_verification` tool requires confirmation of at least two of these four profile values: date of birth, email, phone number, and address.

1. Retrieve the customer profile with an appropriate read-only user lookup.
2. Have the customer provide at least two verification values, and compare each to the retrieved profile.
3. A profile value learned solely from the lookup is **not** customer confirmation. Do not count it as a verified field.
4. Once two fields match, obtain the current timestamp using `get_current_time` if a current timestamp is not already available, then call `log_verification` with all required profile fields and `time_verified`.
5. If two matching fields cannot be obtained, do not perform closure, retention, downgrade, fee waiver, or statement-credit actions. Explain that identity verification remains incomplete. Escalate only if specialist handling is needed; an identity-verification failure requiring specialist handling uses `account_ownership_dispute`.

## 2. Collect and validate closure eligibility

After identity is logged, retrieve the target account using `get_credit_card_accounts_by_user` and check all of the following for that exact account:

- Outstanding balance is exactly `$0.00`.
- The account has been open at least 60 calendar days.
- There are no active or pending transaction disputes associated with the target account.
- There are no pending replacement-card orders for the target account.

### Mandatory live checks

Use the following specialized tools through the discoverable-agent sequence: first call `unlock_discoverable_agent_tool` with the exact tool name, then call `call_discoverable_agent_tool` using that same name and a JSON-string `arguments` value.

1. **Disputes:** unlock and call `get_user_dispute_history_7291` with `{"user_id":"<user_id>"}`. Review statuses and transaction/card context. A dispute with an open, pending, or under-review-like status blocks closure if it belongs to the target account. If the account association cannot be determined, treat eligibility as unresolved and do not close until clarified.
2. **Replacement cards:** unlock and call `get_pending_replacement_orders_5765` with `{"credit_card_account_id":"<credit_card_account_id>"}` immediately before progressing toward closure. An empty order collection passes. If orders are returned, only `delivered` and `cancelled` are final; any other or unknown status blocks closure.

Customer statements about disputes or replacements do not replace these live checks. A failed, incomplete, ambiguous, or inaccessible eligibility tool result is not a pass. Retry where appropriate; if a system failure prevents completion, transfer with `technical_system_error` and summarize the failed check.

If any eligibility condition fails, tell the customer exactly what must be resolved and do not make retention offers or submit closure. Examples: pay the remaining balance, wait until the account reaches 60 days, resolve the dispute, or have the replacement delivered/cancelled.

Use `scripts/assess_closure.py` to consistently calculate the age/balance/order portions of the assessment after translating live results into its documented JSON input. Its output is a decision aid only; live tool responses and the policy above remain authoritative.

## 3. Determine whether retention must be skipped

Only after the eligibility checks pass, unlock and call `get_closure_reason_history_8293` with:

```json
{"credit_card_account_id":"<credit_card_account_id>"}
```

Interpret the response for closure-reason records from the past year for this specific account.

- If such a record exists, skip reason logging and all retention offers. Tell the customer you will proceed with the closure request.
- If no such record exists, follow the retention steps below before closing.
- If the history response is unavailable or its timeframe cannot be determined, do not assume there was no prior attempt. Resolve the issue before applying retention or closing.

## 4. Required retention path when no recent record exists

### Log the reason

Ask for the reason if it is not already clear. Map it to exactly one allowed value:

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
  "credit_card_account_id":"<credit_card_account_id>",
  "user_id":"<user_id>",
  "closure_reason":"<allowed_reason>"
}
```

Do not add notes, timestamps, or extra fields to this call.

### Address the stated concern

Provide the applicable non-coercive assistance:

- **Annual fee:** For a customer relationship of at least two years, offer a one-year annual-fee waiver. If accepted, unlock and call `apply_credit_card_account_flag_6147` with the account ID, user ID, `flag_type: "annual_fee_waived"`, `reason: "loyalty_benefit"`, and an `expiration_date` exactly one calendar year from today in `MM/DD/YYYY` form. For less than two years, offer a same-category no-annual-fee downgrade instead: `Bronze Rewards Card` for personal cards or `Business Bronze Rewards Card` for business cards. Explain benefit changes and obtain consent before unlocking/calling `downgrade_credit_card_3847` with its exact documented arguments.
- **Not using card:** Review relevant benefits and suggest a recurring subscription only as an optional way to keep the card active.
- **Found better card:** Ask which features the other card offers. If a comparable Rho-Bank product can be supported from available information, offer help applying instead of closing; do not claim unavailable products or benefits exist.
- **Unhappy with rewards:** Discuss available bonus-category enrollment and lawful ways to maximize rewards based on spending patterns.
- **Negative experience:** Apologize, gather details, and escalate a serious service issue when warranted. Do not promise a goodwill credit unless it is authorized and the customer accepts it.

### Make one retention offer and await the decision

If the customer still wants to close after the concern is addressed, make one tier-based retention offer and wait for an explicit response:

- Entry tier: 500 bonus points or a $5 statement credit.
- Mid tier: 2,000 bonus points or a $20 statement credit.
- Premium and above: 5,000 bonus points or a $50 statement credit.

Do not apply an offer merely because it was presented. If the customer explicitly accepts a statement-credit offer, unlock `apply_statement_credit_8472` and call it with a JSON string containing exactly `user_id`, `credit_card_account_id`, a positive numeric `amount`, and `reason: "retention_offer"`. Confirm the tool result before telling the customer it was applied. A customer who accepts retention is not proceeding with closure.

If a selected benefit cannot be fulfilled with an authorized documented tool, do not invent a tool, arguments, or confirmation. Explain the limitation and use an appropriate supported escalation path when needed.

If the customer declines the offer, or retention was skipped because of a recent closure-reason record, thank them and proceed without pressure.

## 5. Submit the closure

Immediately before closure, ensure the live eligibility conclusions remain valid, particularly the replacement-order result. Unlock `close_credit_card_account_7834`, then call it with this JSON-string argument structure:

```json
{
  "credit_card_account_id":"<credit_card_account_id>",
  "user_id":"<user_id>"
}
```

Do not say the account is closed unless the tool reports success. If the closure tool errors, do not retry blindly or claim completion; communicate that processing could not be completed and transfer with `technical_system_error` if the problem cannot be resolved.

## 6. Required successful-closure communication

After a successful result, tell the customer:

- A confirmation email and final statement will arrive within several business days.
- Unredeemed rewards may be redeemed for 45 days after the closure request; remaining rewards are forfeited afterward.
- A full annual-fee refund may be available if an annual fee posted and the closure is within 37 days of that charge.
- Closing a card can affect available credit, utilization, and potentially credit score.

Do not promise an annual-fee refund unless the actual fee-posting date and eligibility have been confirmed.

## Tool and result validation checklist

Before any irreversible action, verify all of the following:

1. The logged verification represents two customer-supplied profile fields that matched.
2. `user_id` on the target account matches the verified customer.
3. Target balance is exactly zero and age is at least 60 days.
4. Dispute and replacement checks are successful, current, and unblocked.
5. Closure-reason history was checked and the required retention path was either completed/declined or correctly skipped.
6. Every discoverable tool is unlocked before it is called and receives only documented arguments.
7. Closure completion is based on the close tool's success response, not on intent or a customer-facing message.

## Helper script interface

Run from the package root with JSON on standard input and read JSON from standard output:

```text
python3 scripts/assess_closure.py <<'JSON'
{
  "now": "YYYY-MM-DD ...",
  "identity_verified": true,
  "account": {"current_balance": "$0.00", "date_of_account_open": "YYYY-MM-DD"},
  "disputes": [{"status": "closed", "applies_to_target": true}],
  "replacement_orders": [{"status": "delivered"}]
}
JSON
```

`disputes` must contain only records whose association with the target account is known, with `applies_to_target` explicitly set. For an active dispute of unknown association, do not omit it: resolve the association manually and do not close in the meantime. The script returns `eligible`, `blockers`, `account_age_days`, and individual check results. Missing or malformed required data is reported as a blocker rather than assumed favorable.
