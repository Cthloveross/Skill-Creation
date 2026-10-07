---
name: credit-card-closure-with-retention
version: 1.0.0
description: Handle an authenticated customer's credit-card closure request, including identity verification, closure eligibility checks, replacement and dispute review, required retention workflow, and safe closure processing. Use for requests to close a credit card account.
---

# Credit Card Closure With Retention

Use this Skill when a customer asks to close a credit-card account. It supports normal banking-tool execution; it does not itself execute account actions.

## Required facts and rules

Closure can proceed only when all of the following are true:

1. The requested account has an outstanding balance of exactly `$0.00`.
2. The account has been open for at least 60 days.
3. The customer has no active or pending credit-card disputes.
4. There is no pending replacement card order. An order is blocking unless its status is clearly `delivered` or `cancelled`.
5. The customer has been identity verified and the verification has been logged.

Do not infer eligibility from a prior interaction or stale data. Check replacement orders immediately before a closure attempt. If a required lookup is unavailable, malformed, or ambiguous, do not close the account; explain the limitation and escalate or retry only when appropriate.

## Tool preparation

Unlock a discoverable agent tool before calling it. The workflow can require these tools:

- `get_user_dispute_history_7291`
- `get_pending_replacement_orders_5765`
- `get_closure_reason_history_8293`
- `log_credit_card_closure_reason_4521`
- `apply_credit_card_account_flag_6147` (only for a qualifying annual-fee waiver)
- `close_credit_card_account_7834`

Use `call_discoverable_agent_tool` with a JSON-string `arguments` value after unlocking each tool. Use only the documented arguments; do not add speculative fields.

## Workflow

### 1. Identify the authenticated customer and requested account

1. Locate the user using an identifier the customer provides (such as their name or email), then retrieve their profile and card accounts.
2. Identify exactly one requested account by its card type/name and confirm it belongs to the located user. If several accounts match, ask the customer which account to close.
3. Keep the account-level identifier (`credit_card_account_id` / account ID) separate from a card name, transaction ID, or user ID.

Never close another account simply because it has a similar name or balance.

### 2. Verify and log identity

Obtain confirmation of at least two of these four profile fields: date of birth, email, phone number, and address. Compare the supplied values to the retrieved profile.

After at least two fields match, call `get_current_time`, then call `log_verification` with **all** required profile values:

```json
{
  "name": "<profile full name>",
  "user_id": "<authenticated user id>",
  "address": "<profile address>",
  "email": "<profile email>",
  "phone_number": "<profile phone>",
  "date_of_birth": "<profile DOB in MM/DD/YYYY>",
  "time_verified": "<timestamp returned by get_current_time>"
}
```

If fewer than two fields match, do not disclose account details or process closure. Ask for another verification field or use the approved escalation path if verification cannot be completed.

### 3. Confirm closure eligibility

Perform and assess every check before any retention offer or closure action:

- **Balance and age:** Read the requested account’s current balance and opening date from the account lookup. Calculate age against the current date. A nonzero balance or account age under 60 days blocks closure.
- **Disputes:** Call `get_user_dispute_history_7291` with:
  ```json
  {"user_id":"<user id>"}
  ```
  Treat active, open, pending, or under-review disputes as blocking. Closed/resolved disputes do not block unless the response clearly says they remain active.
- **Replacement orders:** Immediately before the prospective closure, call `get_pending_replacement_orders_5765` with:
  ```json
  {"credit_card_account_id":"<account id>"}
  ```
  An empty `orders` collection passes. If any returned order is not clearly `delivered` or `cancelled`, closure is blocked.

If blocked, clearly identify only the blocking condition(s), tell the customer what must be resolved (pay the balance, wait until the account is old enough, resolve the dispute, or wait for/cancel the replacement), and do not make retention offers or call the closure tool.

### 4. Apply the retention protocol after eligibility passes

First check for a prior retention/closure attempt by calling `get_closure_reason_history_8293` with:

```json
{"credit_card_account_id":"<account id>"}
```

If there is a record for this account within the past year, skip retention offers and proceed to the customer’s closure decision. Do not pressure the customer.

If there is no such recent record:

1. Ask why the customer wants to close if the reason has not already been provided.
2. Normalize the response to exactly one permitted reason:
   - `annual_fee`
   - `not_using_card`
   - `found_better_card`
   - `unhappy_with_rewards`
   - `simplifying_finances`
   - `negative_experience`
   - `other`
3. Log it with exactly these arguments:
   ```json
   {
     "credit_card_account_id":"<account id>",
     "user_id":"<user id>",
     "closure_reason":"<permitted reason>"
   }
   ```
4. Address the concern once. For `found_better_card`, ask which features or rewards attracted the customer. If a comparable internal product is known and available to offer, offer help applying for it; do not claim an unavailable product or benefit.
5. If the customer still wants to close, make one retention offer appropriate to the documented card tier:
   - Entry tier: 500 bonus points or a $5 statement credit
   - Mid tier: 2,000 bonus points or a $20 statement credit
   - Premium and above: 5,000 bonus points or a $50 statement credit

Do not invent a card tier. If the tier cannot be determined from approved account/product information, obtain the tier through an approved source or explain that a tier-based offer cannot be determined. Do not apply a retention incentive unless its applicable tool and authorization are explicitly available.

For an annual-fee concern only, a customer with at least two years of tenure may be offered a one-year annual-fee waiver. If accepted and authorized, call `apply_credit_card_account_flag_6147` using the account and user IDs, `flag_type` `annual_fee_waived`, `reason` `loyalty_benefit`, and an `expiration_date` exactly one year from the current date in `MM/DD/YYYY` format. For a customer with less than two years’ tenure, offer the documented no-annual-fee downgrade path rather than a waiver.

If the customer declines the offer, requests closure again, or retention is skipped due to recent history, accept their decision without pressure.

### 5. Recheck replacement status and close only with a clear decision

Before the state-changing closure call, repeat the pending replacement-order check because it must be immediate. If it now blocks closure, stop and explain.

Only after the customer has clearly requested/confirmed closure, all eligibility checks pass, and the replacement recheck passes, call `close_credit_card_account_7834` with:

```json
{
  "credit_card_account_id":"<account id>",
  "user_id":"<authenticated user id>"
}
```

Do not retry a closure call if its outcome is unknown. Report the returned result accurately. If successful, tell the customer that a confirmation email and final statement will arrive within several business days.

### 6. Required post-closure communication

When closure is submitted or completed, tell the customer:

- Remaining rewards may be redeemed for 45 days after the closure request; afterward, unredeemed rewards are forfeited.
- For cash-back cards, stored reward points represent cash back at `1 point = $0.01` when redeemed as a statement credit or checking-account credit. State the converted amount only when the relevant point balance is known for the requested account.
- A full annual-fee refund may apply when closure occurs within 37 days of the annual-fee posting; after that, no refund is available.
- Closing a card can affect credit utilization and available credit, which may affect credit score.

Do not confuse rewards or balances belonging to another card account with those of the account being closed.

## Failure handling

- If the customer is not verified, stop before any sensitive action.
- If an account lookup produces no exact requested account, ask for clarification.
- If a tool reports invalid identifiers, re-check that account-level and user-level IDs are not swapped.
- If a dispute or replacement response is empty in an ambiguous/failed way rather than clearly successful, do not treat it as a pass.
- If the customer requests a human after the workflow or a system limitation prevents safe completion, transfer with the most applicable supported reason and a concise summary of completed checks. For a completed closure requiring follow-up, use `request_completed_customer_wants_human_followup`; for a closure request that cannot be safely completed by the workflow, use `account_closure_request`.

## Completion checklist

Before reporting closure success, confirm: identity verification logged; exact account selected; balance, age, disputes, and replacement status passed; recent closure-reason history checked; reason logged and required retention handling completed or properly skipped; replacement status rechecked immediately before closure; and closure tool returned a successful result.
