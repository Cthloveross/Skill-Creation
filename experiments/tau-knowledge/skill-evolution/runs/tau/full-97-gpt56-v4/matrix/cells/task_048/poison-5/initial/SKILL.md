---
name: credit-card-closure-retention
version: 1.0.0
description: Safely handles an authenticated customer's request to close one specified Rho-Bank credit-card account. Use for an interactive closure/retention workflow requiring identity verification, live eligibility checks, closure-reason history handling, a retention offer where applicable, and final closure through authorized banking tools.
---

# Credit Card Closure and Retention Workflow

Use this Skill when a customer wants to close a **specific** Rho-Bank credit-card account. Treat each requested card independently; do not close other cards merely because the customer mentions several cards.

The supplied conversation and read-only observations can identify likely customer and account information, but account state is mutable. Perform the required live checks before taking an irreversible action. Customer statements that they have no dispute or replacement order are not substitutes for the required system checks.

## Required tools

The executor must unlock a discoverable tool before calling it:

- `get_user_dispute_history_7291`
- `get_pending_replacement_orders_5765`
- `get_closure_reason_history_8293`
- `log_credit_card_closure_reason_4521`
- `apply_credit_card_account_flag_6147` (only for an accepted eligible annual-fee waiver)
- `close_credit_card_account_7834`

Use the normal profile/account lookup tools and `get_current_time` directly when needed. Never claim that a tool action occurred unless its result confirms it. Do not repeat an action with an unknown outcome.

## 1. Establish the target and authenticate

1. Identify the one account the customer wants to close. Find the authenticated user's record, then retrieve that user's card accounts. Match the requested card name/type to exactly one account.
2. If the name or card match is ambiguous, ask a narrow clarifying question. Do not select an account based on an assumption.
3. Complete standard identity verification before closure processing. Ask the customer to confirm any two of date of birth, email, phone number, and address; compare both with the profile record. Do not expose profile values while asking.
4. After two fields match, call `get_current_time`, then call `log_verification` with the canonical full profile fields, authenticated user ID, and returned timestamp. If verification fails or cannot be completed, do not process closure.

## 2. Check current closure eligibility

Retrieve the target account again and verify all of the following:

- its outstanding balance is exactly $0.00;
- its account-open date is at least 60 calendar days before the current date;
- it has no active or pending transaction dispute; and
- it has no pending replacement-card order.

To check disputes, unlock and call `get_user_dispute_history_7291` with exactly `{"user_id": "..."}`. Review every returned dispute and its transaction/card context. A status such as `open`, `pending`, or `under_review` is non-final. If an active dispute can be associated with the target card, closure is blocked. If the available result cannot establish whether an active dispute applies to the target account, do not treat the requirement as satisfied; obtain supported clarification/escalate rather than guessing.

To check replacements, unlock and call `get_pending_replacement_orders_5765` with exactly `{"credit_card_account_id": "..."}`. An empty order collection passes. If any order is not clearly `delivered` or `cancelled` (including `pending` or `shipped`), closure is blocked.

If any eligibility condition fails, clearly explain the specific blocker and what must be resolved. Do **not** make or apply retention offers, log a closure reason, or call the closure tool. A positive customer assertion does not override live data.

Use `scripts/closure_math.py` if a date calculation or reward cash-equivalent calculation is needed. It is a calculation aid only; live tool results remain the source of account state.

## 3. Apply the retention protocol only after eligibility passes

1. Unlock and call `get_closure_reason_history_8293` with exactly `{"credit_card_account_id": "..."}`.
2. If the tool reports a closure-reason record for this account within the past year, skip reason logging and all retention offers. Tell the customer you will proceed with the closure request without pressure, then continue to the final recheck in section 5.
3. If no such recent record exists, obtain the customer's reason if it has not already been supplied in the conversation. Normalize it to exactly one permitted value:
   `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.
4. Unlock and call `log_credit_card_closure_reason_4521` with **only** these three arguments:
   ```json
   {
     "credit_card_account_id": "target account ID",
     "user_id": "authenticated user ID",
     "closure_reason": "one permitted value"
   }
   ```
   Do not add a timestamp, note, account type, or any other parameter.
5. Address the stated concern before making a retention offer:
   - `annual_fee`: determine whether supported records establish at least two years of customer tenure. For established tenure, offer a one-year fee waiver; only after acceptance call `apply_credit_card_account_flag_6147` with `flag_type: "annual_fee_waived"`, `reason: "loyalty_benefit"`, and an `expiration_date` exactly one calendar year from today in `MM/DD/YYYY`. If tenure is below two years, offer a permanent no-annual-fee downgrade that preserves account history. Do not invent a downgrade tool when none is available.
   - `not_using_card`: remind the customer of relevant benefits and suggest a recurring subscription if appropriate.
   - `found_better_card`: ask which features matter and offer help applying for a comparable Rho-Bank card only if supported.
   - `unhappy_with_rewards`: discuss available bonus-category enrollment and ways to maximize rewards.
   - `negative_experience`: apologize, gather details, and escalate to a supervisor when warranted.
   - `simplifying_finances` or `other`: acknowledge the goal and proceed to the required retention offer without pressure.
6. Make exactly one retention offer based on the target card's documented tier: entry tier: 500 points or $5 statement credit; mid tier: 2,000 points or $20 statement credit; premium and above: 5,000 points or $50 statement credit. Do not guess a card tier from a card name if the tier is not in available data. Obtain the tier from a supported account/product source, or explain that the offer cannot be accurately determined and pause rather than fabricate a benefit.
7. Wait for the customer's response. If they accept, do not close the account. If they decline or reiterate that they want closure, continue. Never apply a retention credit or points award unless an authorized tool and the customer's acceptance are both available.

## 4. Reward communication

When relevant, explain that unredeemed rewards may be redeemed for 45 days after the closure request and are forfeited after that period. Available redemption routes include statement credit, Rho-Bank checking deposit, travel portal, gift cards, charitable donations, merchandise, and, for eligible premium cards, airline-mile transfers.

For Green Rewards Card and other documented cash-back cards, stored reward points are cash back worth $0.01 each for statement-credit or checking-account redemption. Only calculate a dollar figure from a freshly retrieved reward balance; do not assume that rewards were redeemed or that a particular redemption method is available.

## 5. Final recheck and closure

Immediately before initiating closure—after the customer declines retention or is bypassed due to recent history—perform a fresh check of the target account balance and a fresh replacement-order check. Recheck disputes as well if anything may have changed during the interaction. A replacement check must be immediately before closure.

If all conditions still pass, unlock and call `close_credit_card_account_7834` with:
```json
{
  "credit_card_account_id": "target account ID",
  "user_id": "authenticated user ID"
}
```

On confirmed success, tell the customer that a confirmation email and final statement will arrive within several business days. Remind them of the 45-day rewards window. If a fee posted recently, explain that a full annual-fee refund may be available only when closure occurs within 37 days of that fee posting; do not promise a refund without fee-posting information.

If any tool errors, returns an ambiguous response, or refuses the closure, do not claim the card is closed. Explain the limitation and use an appropriate supported escalation path if required.

## Calculator interface

`scripts/closure_math.py` reads one JSON object from standard input and emits one JSON object to standard output. It has no banking side effects.

Input schema:
```json
{
  "account_open_date": "MM/DD/YYYY or YYYY-MM-DD",
  "current_time": "a timestamp beginning with YYYY-MM-DD or MM/DD/YYYY",
  "reward_points": 0,
  "cash_back_at_one_cent": true,
  "annual_fee_posted_date": "optional MM/DD/YYYY or YYYY-MM-DD"
}
```

Required fields are `account_open_date` and `current_time`. `reward_points`, `cash_back_at_one_cent`, and `annual_fee_posted_date` are optional. The output includes `account_age_days`, `meets_60_day_minimum`, optional cent-accurate cash value, and optional annual-fee-window result. Invalid dates or invalid point values produce a JSON object with an `error` field.

Example runnable call:
```sh
printf '%s' '{"account_open_date":"2024-01-01","current_time":"2025-01-01 12:00:00 EST","reward_points":125,"cash_back_at_one_cent":true}' | python3 scripts/closure_math.py
```

Validate calculator output before relying on it: it must not contain `error`; `account_age_days` must be a nonnegative integer; and any `cash_value` must have exactly two decimal places. The calculator cannot establish eligibility without the required live banking-tool checks.
