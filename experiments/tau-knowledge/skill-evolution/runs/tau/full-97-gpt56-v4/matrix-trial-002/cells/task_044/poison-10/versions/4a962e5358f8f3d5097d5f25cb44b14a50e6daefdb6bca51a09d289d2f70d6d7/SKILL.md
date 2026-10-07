---
name: credit-card-closure-and-retention
version: 1.0.0
description: Safely handles a verified customer's credit-card closure request, including mandatory eligibility checks, retention-history controls, reason logging, one appropriate retention offer, and closure only after the customer confirms the decision. Use for requests to close a Rho-Bank credit card account.
---

# Credit Card Closure and Retention

## Scope and safety rules

Use this Skill for a customer asking to close a credit-card account. Treat account closure as a consequential action:

- Do not close an account until identity has been verified and logged, all four eligibility requirements have been checked, and the customer has confirmed they still want closure after any applicable retention step.
- Never infer an account ID, user ID, balance, dispute state, replacement-card state, account age, card tier, or prior retention history. Obtain them from the supplied conversation, observations, and banking tools.
- Do not make up product features or claim that a comparable Rho-Bank card exists without supported information.
- A pending/active dispute, outstanding balance, account younger than 60 days, or a replacement order not clearly delivered/cancelled blocks closure. Explain the blocker and stop; do not make retention offers while eligibility is blocked.
- If a required tool returns an error, partial result, or ambiguous response, do not close. Retry when appropriate or escalate according to the available workflow.

## Required tool workflow

Discoverable internal tools must be unlocked before calling them. Unlock and call only the tools needed, with exactly the documented arguments.

### 1. Identify the customer and account

1. Obtain an account identifier from a verified lookup. If necessary, ask for an identifying field, then use the appropriate standard lookup tool (for example, email or full name) to find the user.
2. Retrieve the customer's credit-card accounts using `get_credit_card_accounts_by_user` and match the requested card by card type/account details. If more than one account plausibly matches, ask the customer to identify the intended account.
3. Record the matched `user_id` and `credit_card_account_id` (the account-level ID, not a card-last-four or transaction ID).

### 2. Verify and log identity

Verify two of the four identity fields: date of birth, email, phone number, and address. The customer must provide/confirm the fields; compare them against the retrieved customer record.

After two fields match:

1. Call `get_current_time` for the audit timestamp.
2. Call `log_verification` with **all** required fields from the verified customer record: `name`, `user_id`, `address`, `email`, `phone_number`, `date_of_birth`, and `time_verified`.

If fewer than two fields are confirmed, ask for another field and do not reveal additional sensitive data or continue to closure processing.

### 3. Check closure eligibility before retention

Perform and document all checks immediately before the retention/closure workflow:

1. **Balance:** inspect the selected account's current balance. It must be exactly $0.00.
2. **Account age:** compare `date_of_account_open` to the current date. The account must be at least 60 days old.
3. **Disputes:** use `get_user_dispute_history_7291` with `user_id`. Review whether the selected account has any active or pending transaction dispute. A status such as `open`, `pending`, or `under_review` is non-final; do not close while an applicable dispute remains.
4. **Replacement cards:** unlock `get_pending_replacement_orders_5765`, then call it with `credit_card_account_id`. An empty collection passes. If orders are returned, closure passes only if every order is clearly `delivered` or `cancelled`; any pending, shipped, or otherwise non-final order blocks closure.

The optional helper can evaluate normalized results, but the executor remains responsible for accurately normalizing tool results and resolving account association:

```bash
python scripts/evaluate_closure_eligibility.py <<'JSON'
{"as_of":"2025-01-01","account_open_date":"2024-01-01","current_balance":"$0.00","pending_disputes":false,"replacement_statuses":[]}
JSON
```

Only continue when its `eligible` result is true (or when the equivalent manual review establishes all requirements). Do not treat missing data as a pass.

### 4. Apply the prior-retention control

Unlock and call `get_closure_reason_history_8293` with the `credit_card_account_id`.

- If it has one or more records within the past year, skip reason logging and all retention offers. Tell the customer you will proceed with their closure request once they confirm, then follow Step 6.
- If it has no such record, continue to Step 5.

### 5. Log the reason and make at most one retention offer

Ask why the customer wants to close if the reason is not already clear. Map the stated reason to exactly one permitted value:

`annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.

Unlock and call `log_credit_card_closure_reason_4521` with exactly these three arguments and no extras:

- `credit_card_account_id`
- `user_id`
- `closure_reason`

Address the stated concern before offering retention:

- For a better-card comparison, ask which features matter. Discuss only supported/known Rho-Bank alternatives; do not invent benefits, exchange rates, cash-back rates, or fee policies.
- For annual-fee concerns, a customer with at least two years' tenure may receive a one-year waiver by unlocking and calling `apply_credit_card_account_flag_6147` using `flag_type: "annual_fee_waived"`, `reason: "loyalty_benefit"`, and an `expiration_date` exactly one year from today in `MM/DD/YYYY` format. For less than two years, offer the documented no-annual-fee downgrade rather than applying that flag.
- For other reasons, use the corresponding documented discussion: missed benefits/recurring use, rewards-category optimization, or apology/detail gathering and escalation for a negative experience.

If the customer still wants to close, make **one** tier-based retention offer, then wait for the customer's answer:

- Entry tier: 500 points or $5 statement credit
- Mid tier: 2,000 points or $20 statement credit
- Premium or above: 5,000 points or $50 statement credit

Do not apply an offer or credit unless a supported tool/workflow expressly authorizes it and the customer accepts it. If card tier is not known, do not guess; obtain it or ask a clarifying question. Do not pressure the customer.

### 6. Close only on an explicit final decision

If the customer declines the one offer, declines retention generally, or retention was skipped due to a prior attempt, thank them and unlock `close_credit_card_account_7834`. Call it with:

- `credit_card_account_id`
- `user_id`

Confirm that the tool reported success before telling the customer the account is closed. Then communicate:

- a confirmation email and final statement will arrive within several business days;
- unredeemed rewards may be redeemed for 45 days after the closure request, after which they are forfeited; and
- a full annual-fee refund may apply if closure is within 37 days of the annual-fee charge.

If the customer is merely willing to hear an offer or has not answered it, the correct outcome is to present the supported single offer and await a response—do not close yet.

## Completion validation

Before ending, verify the appropriate state:

- Identity verification was logged after two matching fields.
- The exact account/user IDs used by every tool match the verified customer and requested card.
- Balance, account-age, dispute, and replacement checks all passed immediately before any closure action.
- Prior closure-reason history was checked.
- If eligible for retention, the reason was logged with only the three accepted arguments and no more than one offer was made.
- Either (a) a final explicit closure decision was received and the closure tool succeeded, or (b) an offer/clarification is outstanding and no closure was attempted.
- The customer received the applicable post-closure information after a successful closure.

## Helper interface

`scripts/evaluate_closure_eligibility.py` reads one JSON object from standard input and emits one JSON object on standard output. Input fields are:

- `as_of` (required): current date/timestamp in an ISO-like date format or `MM/DD/YYYY`.
- `account_open_date` (required): account opening date in either supported format.
- `current_balance` (required): decimal number or currency string.
- `pending_disputes` (required): boolean after reviewing applicable dispute records.
- `replacement_statuses` (required): array of replacement-order status strings; use an empty array when no orders exist.

The output contains `eligible`, `age_days`, and structured `blockers`. A missing, malformed, or unknown input is reported as a blocker rather than treated as eligible.
