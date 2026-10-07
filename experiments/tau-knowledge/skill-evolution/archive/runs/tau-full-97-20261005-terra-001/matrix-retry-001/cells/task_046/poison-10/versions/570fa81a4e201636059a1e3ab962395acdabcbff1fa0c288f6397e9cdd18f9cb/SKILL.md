---
name: credit-card-closure-with-retention
version: 1.0.0
description: Safely process a verified customer's credit-card closure request, including mandatory eligibility checks, replacement-order review, abuse-prevention retention handling, and the final closure action. Use for personal or business credit-card closures; do not use it to close deposit accounts or to make a card downgrade without a closure request.
---

# Credit Card Closure With Retention

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety rules

Use this workflow only when the customer requests closure of a credit-card account. Never infer that a customer is verified merely because they supplied a name, email address, account number, or account details. For a business card, also verify that the authenticated customer has authority to act for the business/card account; account lookup alone does not establish that authority.

Use only account and user identifiers retrieved from authoritative tools during the current interaction. Do not close a different card owned by the customer. Do not make a closure, downgrade, waiver, credit, or any other account change unless all applicable prerequisite checks pass and the customer has given final confirmation for that specific action.

The customer's assertions about disputes, replacement cards, balance, or eligibility are useful context but are not authoritative eligibility checks.

## Inputs to obtain at runtime

Collect or retrieve:

- A successful two-of-four identity verification using date of birth, email, phone number, and address, and the matching user profile.
- The authenticated `user_id` and confirmation that it owns the requested `credit_card_account_id`.
- For business cards, authoritative confirmation of the customer's business authority.
- The requested card account, its current balance, opening date, rewards balance, and card type.
- An authoritative pending-dispute result for that account.
- The current timestamp from `get_current_time`.
- Replacement-order results obtained immediately before a possible closure.
- The customer's final decision after any applicable retention handling.

If an authoritative dispute check, business-authority check, or another required check is unavailable or ambiguous, explain that closure cannot be completed until it is confirmed. Do not substitute transaction history or customer attestation for an authoritative pending-dispute result. Escalate through the supported human-agent path if resolution is needed.

## Procedure

### 1. Verify identity, authority, ownership, and the requested card

1. Ask the customer to confirm any two of the four permitted identity fields: date of birth, email, phone number, and address. Retrieve the profile using an appropriate lookup and compare the supplied fields to the authoritative record.
2. Once two fields match, get the current timestamp with `get_current_time` and call `log_verification` with the complete authoritative profile fields and `time_verified`. The verification tool requires all of: `name`, `user_id`, `address`, `email`, `phone_number`, `date_of_birth`, and `time_verified`.
3. Retrieve accounts using `get_credit_card_accounts_by_user(user_id)` and have the customer identify the specific card if more than one could match. Confirm the selected account's `user_id` equals the verified user.
4. For a business card, obtain an authoritative authority check. If authority is not confirmed, do not continue to retention or closure.
5. Reconfirm the precise account and final requested action before any state-changing tool call.

### 2. Confirm closure eligibility before retention

All four conditions must pass. If any condition fails, tell the customer exactly what must be resolved and stop: **do not make a retention offer, log a retention reason, or close the account.**

1. **Pending disputes:** the account must have no active or pending transaction dispute.
2. **Replacement cards:** unlock and call `get_pending_replacement_orders_5765` with exactly `credit_card_account_id`. An empty orders collection passes. If any order is pending, shipped, unknown, or otherwise non-final, closure is blocked. Only an order collection where every order is delivered or cancelled passes. Retry or escalate an empty/ambiguous tool response rather than treating it as no orders.
3. **Account age:** calculate from the authoritative opening date and current date. The account must have been open for at least 60 days.
4. **Balance:** the current outstanding balance must be exactly `$0.00`. A remaining balance must be paid in full after pending transactions post before closure can proceed.

Use `scripts/evaluate_closure_eligibility.py` to make the date, balance, and replacement-status decision deterministic after collecting authoritative data. Its result is advisory validation; the executor remains responsible for obtaining the source data and applying the workflow.

### 3. Check prior retention attempts

Only after all eligibility checks pass:

1. Unlock `get_closure_reason_history_8293` and call it with exactly `credit_card_account_id`.
2. Determine whether this specific account has any closure-reason record within the past year.
3. If a record exists, skip all retention offers and reason logging. Inform the customer that the request will proceed to closure once they provide final confirmation.
4. If the response does not establish the relevant time period or is ambiguous, do not assume no prior attempt; resolve or escalate before offering retention.

### 4. Record and address the reason when retention is allowed

If there is no prior closure-reason record in the past year, ask for or confirm the customer's reason and map it to exactly one allowed value:

- `annual_fee`
- `not_using_card`
- `found_better_card`
- `unhappy_with_rewards`
- `simplifying_finances`
- `negative_experience`
- `other`

Unlock `log_credit_card_closure_reason_4521` and call it using **only** `credit_card_account_id`, `user_id`, and `closure_reason`. Do not add any parameters.

Then address the concern without pressure:

- **Annual fee:** If authoritative customer tenure is at least two years, offer a one-year fee waiver. If tenure is under two years, offer a permanent same-category no-annual-fee downgrade: `Bronze Rewards Card` for personal cards or `Business Bronze Rewards Card` for business cards. Do not use account opening date as a substitute for customer tenure.
- **Not using card:** remind the customer of relevant benefits and suggest an optional recurring subscription.
- **Found a better card:** ask which features matter and, if a supported comparable Rho-Bank card exists, offer help applying instead of closing.
- **Unhappy with rewards:** review available bonus-category enrollment and lawful ways to maximize rewards based on spending.
- **Negative experience:** apologize, gather details, and escalate service complaints when warranted. Do not promise a goodwill credit without an authorized tool and policy.

For a qualifying annual-fee waiver, unlock `apply_credit_card_account_flag_6147` and call it with exactly `credit_card_account_id`, `user_id`, `flag_type: "annual_fee_waived"`, `expiration_date` set to one year from the current date in `MM/DD/YYYY`, and `reason: "loyalty_benefit"`.

For an accepted downgrade, explain the benefit changes and that account history, account number, credit line, and reward value are preserved. Unlock `downgrade_credit_card_3847` and call it with exactly `credit_card_account_id`, `user_id`, and the permitted `target_card_type`. A downgrade takes effect immediately, while the existing physical card remains usable until the replacement arrives. A downgrade is an alternative to closure, not a closure action.

### 5. Make one retention offer if appropriate

If the customer still wants to close after the concern has been addressed, make one offer according to the account's authoritative tier classification:

- Entry-tier: 500 bonus points or a $5 statement credit.
- Mid-tier: 2,000 bonus points or a $20 statement credit.
- Premium and above: 5,000 bonus points or a $50 statement credit.

Do not guess a tier classification from a card name when it is not authoritatively available. If the customer declines, do not pressure them. If the customer accepts an offer, use only an authorized tool and policy to fulfill it; if none is available, do not represent the offer as applied.

### 6. Close the account

When retention is declined, skipped because of prior attempts, or not applicable, obtain explicit final confirmation to close the identified account. Reconfirm all closure prerequisites, particularly the balance, disputes, and replacement-order result immediately before closing.

Unlock `close_credit_card_account_7834`, then call it with exactly:

- `credit_card_account_id`
- `user_id`

Use the normal banking tool result as the closure outcome. Do not claim success if the tool fails or returns an ambiguous response. For a failure, explain the reported issue and escalate where appropriate.

### 7. Post-closure communication

After a confirmed successful closure, tell the customer:

- A confirmation email and final statement will arrive within several business days.
- Remaining rewards may be redeemed for 45 days after the closure request; after that, unredeemed rewards are permanently forfeited.
- A full annual-fee refund may be available if closure is within 37 days of the fee posting; do not promise a refund outside that window.
- Closing a card can reduce total available credit and affect credit utilization, which may affect the credit score, particularly for a high-limit or old account.

For cash-back cards, including Business Silver Rewards Card, the backend rewards balance is stored as points. If asked to value it, explain that 1 point equals `$0.01` when redeemed as a statement credit or credit to the customer's Rho-Bank checking account.

## Eligibility helper

`scripts/evaluate_closure_eligibility.py` reads one JSON object from standard input and emits one JSON object on standard output. It does not access bank systems or perform any account action.

Input schema:

```json
{
  "account_open_date": "MM/DD/YYYY or YYYY-MM-DD",
  "current_balance": "a decimal amount, optionally with $",
  "pending_disputes": false,
  "replacement_orders": [{"status": "delivered"}],
  "as_of": "current runtime timestamp or ISO date"
}
```

`replacement_orders` may be an empty array. `pending_disputes` must be the Boolean `true` or `false`, not a textual approximation. Missing or malformed required values produce `ok: false`, so they must be resolved rather than assumed to pass.

A runnable invocation using a JSON object populated from current authoritative runtime data is:

```sh
printf '%s' "$ELIGIBILITY_INPUT_JSON" | python3 scripts/evaluate_closure_eligibility.py
```

Before relying on a successful helper result, validate that `ok` is `true`, `eligible` is `true`, `blockers` is empty, `account_age_days` is at least 60, `balance_is_zero` is `true`, `pending_disputes` is `false`, and `replacement_orders_clear` is `true`. The caller must still ensure that the input is current and belongs to the verified account.

## Unsupported or blocked cases

- If balance is nonzero, disputes are pending, account age is below 60 days, or a replacement order is non-final, do not close or make retention offers.
- If the customer cannot be identity-verified, does not own the account, or lacks business authority, do not disclose additional account details or take action.
- If an essential named tool cannot be unlocked, required data is unavailable, or a tool result is ambiguous, do not fabricate a result. Explain the limitation and use the supported human-agent escalation path when needed.
- Never use a downgrade or a waiver tool as a substitute for the customer's confirmation.
