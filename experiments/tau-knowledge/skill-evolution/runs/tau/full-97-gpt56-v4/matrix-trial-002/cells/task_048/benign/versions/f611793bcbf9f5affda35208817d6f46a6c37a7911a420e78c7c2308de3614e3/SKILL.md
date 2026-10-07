---
name: credit-card-closure-workflow
description: Safely process a verified customer's request to close one Rho-Bank credit card, including eligibility checks, required retention handling, closure, and required customer communication. Use when a customer asks to close a credit-card account.
---

# Credit Card Closure Workflow

Process one specifically identified credit-card account at a time. Do not infer that a request to close several cards authorizes closing every card; identify and process each account separately.

## Required inputs and assumptions

Obtain or look up at runtime:

- The authenticated customer's `user_id` and profile.
- The exact target `credit_card_account_id`; confirm it belongs to that user and matches the card the customer named.
- Two confirmed identity fields out of date of birth, email, phone number, and address.
- The customer's stated closure reason and whether they ultimately want to continue after any applicable retention offer.
- Current time, account opening date, balance, dispute results, replacement-order results, and prior closure-reason history.

Never use an account ID, user ID, balance, or eligibility result from a prior case. Treat missing, contradictory, or ambiguous data as a stop condition until clarified or escalated.

## Procedure

### 1. Identify the customer and target account

1. Locate the customer with an available lookup (name, email, or user ID) and use `get_credit_card_accounts_by_user`.
2. Match the requested card name/type to exactly one account owned by that user. If there are multiple possible matches, ask which account to close. If no match exists, explain that it cannot be located.
3. Do not close any other account merely because the customer mentioned multiple cards.

### 2. Verify identity and record it

1. Ask the customer to confirm enough profile information to satisfy **two of four** identity fields: date of birth, email, phone number, or address. A name alone is not one of the four verification fields.
2. Compare every field the customer supplies against the profile. If a supplied field does not match, do not continue with closure.
3. Call `get_current_time` and then `log_verification` only after two fields have matched. Supply all required profile fields to `log_verification` (`name`, `user_id`, `address`, `email`, `phone_number`, `date_of_birth`, and the returned `time_verified`).
4. If identity cannot be verified, do not disclose account-specific details or perform account actions.

### 3. Verify every closure eligibility condition before retention

Use the account record and current time to verify the account is at least 60 days old and has an outstanding balance of exactly $0.00. Then unlock and use the required internal tools:

- `get_user_dispute_history_7291` with `user_id`. Block closure if any dispute is active, open, pending, under review, or otherwise not fully resolved. A historical dispute that is clearly closed/resolved does not block closure.
- `get_pending_replacement_orders_5765` with `credit_card_account_id`. Block closure if any replacement order is non-final (for example pending or shipped). Proceed only if there are no orders or every returned order is clearly delivered or cancelled.

If any condition fails, explain the specific condition to resolve and do not make a retention offer, log a closure reason, or call the closure tool. If a tool response is unavailable or ambiguous, do not assume eligibility; tell the customer the closure cannot be completed until the check is confirmed, and use the appropriate support path if needed.

### 4. Apply the retention protocol only after eligibility succeeds

1. Unlock and call `get_closure_reason_history_8293` with the target `credit_card_account_id`.
2. If it returns a closure-reason record for that account within the past year, skip all retention offers and proceed to closure once the customer confirms they still want to close.
3. Otherwise, obtain the reason if it has not already been clearly provided. Normalize it to exactly one allowed value:
   - `annual_fee`
   - `not_using_card`
   - `found_better_card`
   - `unhappy_with_rewards`
   - `simplifying_finances`
   - `negative_experience`
   - `other`
4. Unlock and call `log_credit_card_closure_reason_4521` with **only** `credit_card_account_id`, `user_id`, and `closure_reason`.
5. Address the concern appropriately. For annual-fee concerns, only offer a one-year annual-fee waiver to a customer with at least two years' tenure; use `apply_credit_card_account_flag_6147` only after the customer accepts, with `flag_type: "annual_fee_waived"`, `reason: "loyalty_benefit"`, and an `expiration_date` exactly one year from the current date in `MM/DD/YYYY` format. For shorter tenure, offer a permanent no-annual-fee downgrade instead. Do not apply a waiver without acceptance.
6. If the customer still wishes to close, make one retention offer based on tier:
   - Entry: 500 points or $5 statement credit.
   - Mid-tier: 2,000 points or $20 statement credit.
   - Premium and above: 5,000 points or $50 statement credit.

If the customer declines, do not pressure them. If an applicable offer was already stated and the customer clearly declined it in the conversation, do not repeat it; treat that as the decision to continue. Do not invent or apply a points/credit retention benefit unless a supported action and explicit acceptance are available.

### 5. Close the account

After verified identity, all eligibility checks, required reason handling (unless skipped due to prior history), and a clear customer decision to continue:

1. Unlock `close_credit_card_account_7834`.
2. Call it with exactly the verified `credit_card_account_id` and `user_id`.
3. Report success only if the tool confirms success. Do not retry a closure call if its outcome is unknown; instead escalate as a technical-system issue to prevent a duplicate or contradictory action.

### 6. Customer communication after confirmed closure

Tell the customer:

- A confirmation email and final statement will arrive within several business days.
- Unredeemed rewards may be redeemed for 45 days after the closure request; after that they are forfeited.
- A full annual-fee refund may apply if closure occurs within 37 days after the annual-fee charge.
- Closing a card can affect credit utilization, available credit, and potentially the credit score.
- If the target card supplies a savings APY bonus, closure or unlinking ends that card's stated Green Account eligibility bonus. Explain this as an account impact, not as a reason to override the customer's closure decision.

Do not claim an annual-fee refund, rewards redemption, APY outcome, or closure completion unless supported by the applicable policy or tool result.

## Failure handling

- **Identity mismatch or insufficient verification:** request another accepted verification field; do not continue.
- **Nonzero balance, under-60-day account, unresolved dispute, or pending replacement:** name the blocker and stop the closure workflow.
- **Customer changes their mind or accepts an available alternative:** do not close the account.
- **Tool access/technical error or unknown mutation outcome:** do not guess or repeat a potentially completed mutation. Transfer/escalate with a concise account-specific summary, using `technical_system_error` where applicable.
- **Request for a human:** transfer using the applicable supported reason, normally `account_closure_request` if the closure cannot be completed through the workflow.

## Runtime tool sequence

Discoverable tools must be unlocked before calling them. The usual safe sequence is:

1. `get_user_dispute_history_7291`
2. `get_pending_replacement_orders_5765`
3. `get_closure_reason_history_8293`
4. `log_credit_card_closure_reason_4521`
5. Optional accepted annual-fee waiver: `apply_credit_card_account_flag_6147`
6. `close_credit_card_account_7834`

Calls that mutate records (logging, flags, closure) require confirmed prerequisites and must use runtime case data, never hardcoded identifiers.
