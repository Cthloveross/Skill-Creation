---
name: credit-limit-increase-processing
description: Process a verified credit-card account owner's confirmed credit-limit-increase (CLI) request. Use when an agent must validate tier limits, formally submit the request, complete the required post-submission review, and record an approval or policy-coded denial.
---

# Credit Limit Increase Processing

## Scope and banking controls

Use this Skill only for a CLI request from the account owner or an authorized account manager. Before any banking action, verify customer identity, authority, account ownership, product eligibility, available credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For a CLI, establish all applicable prerequisites before submission:

- identity is verified by confirmation of two of date of birth, email, phone number, or address, and is audit-logged;
- the verified user owns the selected credit-card account and is the owner or authorized manager;
- the account/card, current limit, current balance, standing, account-open date, applicable tier, and request amount are known from authoritative records; and
- the customer has explicitly confirmed a valid whole-dollar increase amount.

Do not use unverified identity data or an account that does not belong to the verified user. If a supplied case trace already contains a successful identity verification and audit record for the same user, do not repeat identity questions or logging solely because the request later changes to a compliant amount. Resolve missing identity, authority, ownership, account, tier, or amount information before taking a banking action.

## Governing workflow and clarification handling

Perform the workflow in this exact order:

1. Validate the confirmed requested increase against the applicable tier maximum.
2. Formally submit a valid request.
3. Complete **every** required eligibility check after submission.
4. Record one final approval or denial.
5. Communicate the result and next steps.

When a conversation has multiple amount discussions or clarification records, use the latest explicit customer confirmation that resolves the amount. An earlier percentage or rejected/excessive amount is superseded by a later explicit compliant dollar amount. Do not reconfirm a superseded amount and do not escalate merely because the original request exceeded the limit when the customer has subsequently accepted a valid amount.

A percentage is not itself a submission amount. Calculate it using the verified current limit, state the resulting dollar maximum and total limit, and obtain an explicit dollar confirmation if it is not already present. Do not submit an excessive request. An excessive request should normally be adjusted before submission, rather than denied as a formal CLI request.

## Tier policy

| Tier | Minimum account age | Cooldown after approved request | Utilization requirement | On-time payment history | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | strictly below 70% | 6 consecutive months | 25% of current limit |
| Mid-tier | 90 days | 90 days | strictly below 80% | 3 consecutive months | 50% of current limit |
| Premium-tier | 60 days | 60 days | strictly below 90% | 3 consecutive months | 50% of current limit |

Use a tier explicitly established by the product record or applicable policy. A card/product-specific clarification that expressly identifies the tier is sufficient. Do not infer an unavailable tier from a generic card name alone.

Calculate utilization as:

`current_balance / current_credit_limit * 100`

The threshold is exclusive: utilization equal to the stated threshold fails. The cooldown concerns the most recent **approved** CLI request; denied requests do not start a cooldown. The cooldown ends on the approved-request submission date plus the tier's required full number of days.

## Runtime procedure

### 1. Establish the verified request context

1. Locate the user and their credit-card accounts using the supplied identity information and authoritative account lookup tools.
2. If verification is not already audit-logged for this request context, obtain confirmation of two identity fields, call `get_current_time`, and then call `log_verification` with the complete authoritative identity record and timestamp.
3. Confirm that the account's `user_id` is the verified user and that the requester has authority for it.
4. Record the account ID, user ID, card type, tier, open date, current limit, balance, account status, and past-due amount.
5. Read the full clarification history. Select the latest explicit confirmed compliant amount, rather than an earlier tentative amount or percentage.

### 2. Validate and submit before reviewing eligibility

Compute the maximum increase from the verified current limit and tier. Confirm that the final amount is a positive whole-dollar value at or below that maximum. State the corresponding proposed total limit.

Once the amount is valid and confirmed, unlock `submit_credit_limit_increase_request_7392` and call it before any eligibility-history, dispute, replacement-order, or payment-history lookup:

```json
{
  "credit_card_account_id": "<verified account id>",
  "user_id": "<verified user id>",
  "requested_increase_amount": 1000
}
```

The number above illustrates the integer type only; substitute the actual confirmed amount. Do not use a string for `requested_increase_amount`. Confirm that submission succeeded. If it fails or is ambiguous, resolve its status before proceeding, so that no duplicate request or unsupported decision is recorded.

### 3. Complete all post-submission checks

After a successful submission, complete all checks below even when one known fact already means the request will fail. This produces the required complete audit review. Unlock a discoverable tool immediately before its first use, then call it with the exact scope shown.

1. **Account age:** Calculate full days from the authoritative account-open date to the current date and compare it to the tier minimum.
2. **Cooldown:** Unlock and call `get_credit_limit_increase_history_4829`:
   ```json
   {"credit_card_account_id":"<verified account id>"}
   ```
   Locate the most recent approved request and apply only that request to the tier cooldown.
3. **Disputes:** Unlock and call `get_user_dispute_history_7291`:
   ```json
   {"user_id":"<verified user id>"}
   ```
   A dispute that is open, under review, or otherwise non-final fails this criterion; closed disputes do not.
4. **Replacement order:** Unlock and call `get_pending_replacement_orders_5765`:
   ```json
   {"credit_card_account_id":"<verified account id>"}
   ```
   An empty result passes. Any order not clearly delivered or cancelled fails.
5. **Good standing:** Verify that the account is current/active as applicable and has no positive past-due balance.
6. **Utilization:** Calculate and compare utilization against the strict tier threshold using the authoritative balance and limit captured at review time.
7. **Payment history:** Unlock and call `get_payment_history_6183`:
   ```json
   {"credit_card_account_id":"<verified account id>","months":<tier-required months>}
   ```
   Use `6` for entry-tier and `3` for mid-tier or premium-tier. Verify all months in the required consecutive period are on time.

Do not treat absent, malformed, partial, or ambiguous results as passing. Resolve tool/data errors through normal operational handling before recording a final decision.

### 4. Record the final decision

After the complete review, use exactly one final decision tool.

If every criterion passes, unlock and call `approve_credit_limit_increase_5847`:

```json
{
  "credit_card_account_id":"<verified account id>",
  "user_id":"<verified user id>",
  "new_credit_limit":<current credit limit plus confirmed increase>
}
```

If any criterion fails, unlock and call `deny_credit_limit_increase_5848`:

```json
{
  "credit_card_account_id":"<verified account id>",
  "user_id":"<verified user id>",
  "denial_reason":"<policy reason>"
}
```

Use the matching allowed denial reason:

- account age: `insufficient_account_age`
- approved-request cooldown: `cooldown_period_active`
- active/non-final dispute: `pending_disputes`
- pending/non-final replacement order: `pending_replacement_card`
- non-current account or past-due balance: `past_due_balance`
- utilization at or above the tier threshold: `high_utilization`
- insufficient consecutive on-time payment history: `insufficient_payment_history`
- a formally submitted amount that exceeded a limit only under an exceptional supported process: `requested_amount_exceeds_limit`
- another documented ineligible condition with no listed reason: `other`

For example, an entry-tier account at 70% utilization or more requires `high_utilization` after the mandatory submission and complete review, unless another recorded reason is selected under the operational decision policy. Do not escalate simply because an entry-tier request is eligible for standard policy review.

### 5. Communicate the recorded outcome

For an approval, tell the customer the increase was approved and state the new total limit. For a denial, explain the customer-facing reason without exposing internal-only data. Give actionable next steps: the calculated eligibility date for age/cooldown, reduction below the applicable utilization threshold for utilization, completion/delivery/cancellation for replacement orders, or additional consecutive on-time payments for payment history.

## Deterministic helper

`scripts/assess_cli.py` evaluates normalized values only; it does not call banking tools, unlock tools, submit a request, or record a decision. It reads one JSON object from standard input and writes one JSON object to standard output.

Input schema:

```json
{
  "tier":"entry|mid|premium",
  "now":"ISO date/time or MM/DD/YYYY",
  "account_open_date":"ISO date/time or MM/DD/YYYY",
  "current_credit_limit":4000,
  "current_balance":3000,
  "requested_increase_amount":1000,
  "submission_recorded":true,
  "is_current":true,
  "past_due_amount":0,
  "approved_request_dates":[],
  "active_disputes":false,
  "replacement_order_statuses":[],
  "consecutive_on_time_months":6
}
```

Its output includes policy thresholds, calculated amount and utilization, individual checks, a status, and a proposed denial reason. Validate the normalized values against authoritative tool results before using it. `ready_to_deny` is not permission to skip the required post-submission tool calls; it is only available once their results have been supplied.

Example runtime call (replace placeholders with live normalized values):

```sh
printf '%s' '{"tier":"<tier>","now":"<date>","account_open_date":"<date>","current_credit_limit":<number>,"current_balance":<number>,"requested_increase_amount":<integer>,"submission_recorded":true,"is_current":true,"past_due_amount":<number>,"approved_request_dates":[],"active_disputes":false,"replacement_order_statuses":[],"consecutive_on_time_months":<integer>}' | python3 scripts/assess_cli.py
```
