---
name: credit-card-account-closure
version: 1.0.0
description: Safely process a verified customer's request to close one Rho-Bank credit card account. Use this for eligibility checks, required retention handling, and execution of a credit-card closure through approved banking tools.
---

# Credit Card Account Closure

Use this Skill for **one specifically identified credit-card account at a time**. Do not infer that a request to close several cards authorizes closure of every card; identify and process each requested card separately.

The executor performs all banking actions using the normal runtime tools. The packaged script only evaluates supplied facts; it never performs tool calls or closes an account.

## Required prerequisites

Before a closure can proceed, establish all of the following:

1. **Identity verification:** Verify two of the four profile fields (date of birth, email, phone number, address) against the authenticated customer's profile. After successful verification, call `log_verification` with every required profile field and the current timestamp from `get_current_time`.
2. **Correct account and ownership:** Look up the customer's credit-card accounts and select the requested account by its card type/account ID. Ensure its `user_id` belongs to the verified customer.
3. **Closure eligibility:** The target account must have a $0.00 outstanding balance, no active or pending dispute, be open at least 60 days, and have no pending replacement-card order. Do not treat missing or ambiguous results as passing.
4. **Immediately-before-close replacement check:** Run the replacement-order check again immediately before submitting the close request. If time has passed or account state may have changed, refresh the other eligibility checks too.

If a prerequisite is missing, ask only for the needed information or explain the blocking condition. Do not make retention offers or submit a closure while eligibility is blocked.

## Runtime workflow

### 1. Verify and identify

1. Obtain a user ID or locate the customer with an approved profile lookup.
2. Retrieve their credit-card accounts and identify the one the customer named. If there are multiple possible matches, ask the customer which account they mean.
3. Verify at least two profile fields and log the successful verification. A customer-provided field may be compared against the retrieved profile; never claim verification based merely on a lookup.

### 2. Check closure eligibility

Use current account data to verify the balance is exactly `$0.00` and calculate account age from `date_of_account_open` and the current date.

Unlock and call these discoverable tools as applicable:

- `get_user_dispute_history_7291` with `{"user_id":"..."}`. Review the results for disputes belonging to the target account. Any active, open, pending, or under-review dispute blocks closure. If account linkage or status is ambiguous, do not close; resolve or escalate the ambiguity.
- `get_pending_replacement_orders_5765` with `{"credit_card_account_id":"..."}`. An empty collection passes. If any order is not clearly `delivered` or `cancelled`, closure is blocked.

Explain the specific blocker without offering retention. For example: the customer must pay a remaining balance, wait until disputes resolve, wait until 60 days after opening, or complete/cancel the replacement process.

Use `scripts/evaluate_closure.py` to consistently evaluate the facts gathered from those calls. Its result is a decision aid, not a substitute for fresh tool results.

### 3. Enforce retention-attempt controls

Only after eligibility passes, unlock and call `get_closure_reason_history_8293` using the target `credit_card_account_id`.

- If there is a closure-reason record within the past year, do **not** make a retention offer. Tell the customer you will proceed with the closure request, then continue to Step 6.
- If no such recent record exists, obtain a reason if it has not already been supplied. Normalize it to exactly one allowed value:
  - `annual_fee`
  - `not_using_card`
  - `found_better_card`
  - `unhappy_with_rewards`
  - `simplifying_finances`
  - `negative_experience`
  - `other`

Unlock and call `log_credit_card_closure_reason_4521` with **only** `credit_card_account_id`, `user_id`, and `closure_reason`. Do not add explanatory fields or any other parameters.

### 4. Address the stated concern and make one offer when permitted

Address the concern before an offer, using only the documented options:

- **Annual fee:** A customer with documented tenure of at least two years may be offered a one-year annual-fee waiver. If accepted, unlock/call `apply_credit_card_account_flag_6147` with `flag_type: "annual_fee_waived"`, `reason: "loyalty_benefit"`, and an `expiration_date` one calendar year from the current date in `MM/DD/YYYY` format. If documented tenure is under two years, offer a permanent no-annual-fee downgrade instead. Determine whether the account is personal or business and, with customer consent, call `downgrade_credit_card_3847` using respectively `Bronze Rewards Card` or `Business Bronze Rewards Card`. Do not infer customer tenure from the card opening date.
- **Not using card:** Remind the customer of relevant benefits and suggest a recurring subscription to keep it active.
- **Found better card:** Ask what features they prefer and offer help applying for a comparable Rho-Bank card only if one is supported by available information.
- **Unhappy with rewards:** Check available bonus-category enrollment and discuss documented reward-maximization options.
- **Negative experience:** Apologize and gather details. Escalate to a supervisor if warranted. Do not invent a goodwill amount or apply a credit without an approved customer-facing offer and authority.
- **Simplifying finances/other:** Acknowledge the goal; do not invent a product-change benefit.

If the customer still wants to close and has no recent retention history, make **one** tier-based retention offer:

- Entry tier: 500 bonus points **or** a $5 statement credit
- Mid tier: 2,000 bonus points **or** a $20 statement credit
- Premium and above: 5,000 bonus points **or** a $50 statement credit

A documented, executable option is a statement credit: after the customer accepts it, unlock `apply_statement_credit_8472` and call it with `user_id`, `credit_card_account_id`, positive dollar `amount`, and `reason: "retention_offer"`. Do not close an account after a retention offer is accepted unless the customer makes a new, clear closure request. If the customer chooses bonus points but no approved points-award tool is available, do not fabricate a tool call; offer the documented statement-credit alternative or follow the supported escalation path.

If the offer is declined, or a recent closure-reason record required retention to be skipped, thank the customer and proceed without pressure.

### 5. Submit the closure

Immediately before closing, refresh the pending-replacement result and confirm that it remains clear. Refresh balance, dispute, and age checks if their state could have changed. If every prerequisite still passes:

1. Unlock `close_credit_card_account_7834`.
2. Call it with exactly the verified `credit_card_account_id` and matching `user_id` required by the tool.
3. Inspect the returned result and state that closure was completed only when the tool confirms success. If it fails or is ambiguous, do not claim closure; explain that it could not be completed and use the supported escalation route if needed.

### 6. Required closure communication

After successful closure, tell the customer:

- A confirmation email and final statement will arrive within several business days.
- Unredeemed rewards may be redeemed for 45 days after the closure request; afterward they are forfeited.
- If an annual fee posted recently, a full refund may apply when closure occurs within 37 days of the fee charge.
- Closing a credit card can affect credit utilization and therefore may affect their credit score.

Do not promise an annual-fee refund without confirming the fee date and an approved refund process.

## Deterministic eligibility helper

`scripts/evaluate_closure.py` reads one JSON object from standard input and emits one JSON object to standard output.

Input schema:

```json
{
  "current_date": "YYYY-MM-DD or timestamp",
  "identity_verified": true,
  "account": {
    "account_id": "string",
    "user_id": "string",
    "date_of_account_open": "YYYY-MM-DD",
    "current_balance": "$0.00 or numeric string"
  },
  "account_disputes": [{"status": "closed"}],
  "replacement_orders": [{"status": "delivered"}],
  "closure_reason_history_recent": false,
  "closure_reason_text": "simplifying my finances"
}
```

`account_disputes` must contain only disputes confirmed to belong to the target account. `replacement_orders` must be the current response for that account. Set `closure_reason_history_recent` to `true` or `false` only after the history tool has been called; omit it or use `null` when it is not yet known.

Output includes `closure_eligible`, a list of `blockers`, age and balance interpretation, the next workflow stage, and a normalized permitted closure reason when recognizable.

Example runnable invocation:

```bash
python3 scripts/evaluate_closure.py <<'JSON'
{"current_date":"2025-01-15","identity_verified":true,"account":{"account_id":"account-id","user_id":"user-id","date_of_account_open":"2024-01-01","current_balance":"0.00"},"account_disputes":[],"replacement_orders":[],"closure_reason_history_recent":false,"closure_reason_text":"simplifying my finances"}
JSON
```

Validate that `closure_eligible` is `true` before advancing to reason-history handling. Validate again from refreshed facts before invoking the closure tool. A false result or any `missing_or_ambiguous_*` blocker means the executor must not close the account.
