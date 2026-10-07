---
name: credit-limit-increase-processing
description: Process a confirmed credit-card credit-limit-increase (CLI) request using tier limits, required post-submission eligibility checks, and the prescribed approval, denial, pending, and human-escalation handling.
---

# Credit Limit Increase Processing

Use this Skill when a customer asks to increase a credit-card limit and provides, or can provide, an account identifier and requested **increase amount**. An increase is not a requested total limit.

## Policy and ordering rules

Follow these steps in the listed order. Do not batch steps whose preceding results are required.

1. Resolve the customer and specific card account.
2. Determine the card tier and collect current account facts.
3. Validate the requested increase is a positive whole-dollar amount within the tier maximum.
4. If valid, submit the CLI request.
5. Complete **all Step 2 basic-eligibility checks and receive their usable results**.
6. Only after Step 2 is complete, retrieve and evaluate payment history (Step 3).
7. Make an approval or denial decision only when every mandatory fact is known.
8. Communicate the resulting approval, denial, or pending review status.

A missing, failed, partial, contradictory, or ambiguous response is not evidence that a requirement passes or fails. Do not approve or deny a submitted request until the mandatory data issue is resolved.

## Tier policy

| Tier | Minimum age | Approved-request cooldown | Utilization | Consecutive on-time payments | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | below 70% | 6 months | 25% of current limit |
| Mid-tier | 90 days | 90 days | below 80% | 3 months | 50% of current limit |
| Premium-tier | 60 days | 60 days | below 90% | 3 months | 50% of current limit |

`Gold Rewards Card` is premium-tier. For a different card product, obtain a reliable tier classification; do not infer tier from a similar name.

Boundary interpretation:

- Account age passes at or after the minimum day.
- Utilization must be strictly below the tier threshold.
- The request may equal, but may not exceed, the maximum increase.
- Only the most recent prior **approved** CLI request starts a cooldown. A denied CLI does not.
- The cooldown passes on or after the prior approved submission date plus the required full days.

## Procedure

### 1. Resolve the account and pre-submission facts

Use the supplied customer identifier with an available user lookup, then call `get_credit_card_accounts_by_user` with the canonical `user_id`. Confirm the intended card account if more than one account is returned.

Obtain and retain:

- canonical `user_id` and `credit_card_account_id`;
- card type and verified tier;
- account-open date, current credit limit, and current balance;
- a reliable current date from `get_current_time` for date calculations; and
- authoritative account-standing information showing whether the account is current with no past-due balance.

A zero balance alone does not prove the account has no past-due amount. If an authoritative standing result is unavailable, it remains unknown.

Use `scripts/cli_policy.py` as a deterministic aid. It reads one JSON object from stdin and writes one JSON object to stdout. Example:

```text
python scripts/cli_policy.py < normalized_cli_facts.json
```

Before submitting, inspect only `can_submit`, `maximum_increase_amount`, and input errors. The script performs no banking action and does not replace normal agent tools.

### 2. Validate the amount before submission

The requested amount must be a positive integer dollar increase and no more than the tier maximum calculated from the current limit.

If the amount exceeds the maximum, do **not** submit, approve, or deny that request. Tell the customer the maximum increase and request confirmation of a revised valid amount. Refresh facts and validate the revised request.

If the tier, current limit, or amount cannot be determined reliably, obtain the missing information before submission.

### 3. Submit a valid request

Unlock and call `submit_credit_limit_increase_request_7392` through the normal discoverable-agent-tool flow:

```json
{
  "credit_card_account_id": "<canonical account id>",
  "user_id": "<canonical user id>",
  "requested_increase_amount": 2500
}
```

Replace the example amount with the customer-confirmed valid amount. Wait for successful submission and retain its request/reference ID. If submission is unsuccessful or ambiguous, resolve that problem before any decision activity.

### 4. Step 2 — complete basic eligibility sequentially

After successful submission, perform every required basic check, including checks that appear likely to fail. **Wait for the successful usable result of each call before moving on. Do not initiate the payment-history call in this step or in parallel with these checks.**

1. **Cooldown:** unlock/call `get_credit_limit_increase_history_4829` with:
   ```json
   {"credit_card_account_id":"<canonical account id>"}
   ```
   Wait for the result. Identify the most recent *prior approved* CLI and its submission date; ignore denied requests and the newly submitted request.
2. **Disputes:** after the cooldown result is available, unlock/call `get_user_dispute_history_7291` with:
   ```json
   {"user_id":"<canonical user id>"}
   ```
   Wait for the result. `open` and `under_review` disputes are active. Treat any status not clearly final/closed as unresolved until clarified.
3. **Replacement cards:** after the dispute result is available, unlock/call `get_pending_replacement_orders_5765` with:
   ```json
   {"credit_card_account_id":"<canonical account id>"}
   ```
   Wait for the result. An empty order collection passes. Any order not clearly `delivered` or `cancelled` is pending.
4. Evaluate account age, good standing, and utilization from authoritative current facts. Compute utilization as `(current_balance / current_credit_limit) * 100` only with an authoritative positive limit and balance, unless an authoritative utilization percentage is supplied.

Step 2 is complete only when the cooldown, dispute, and replacement tool results have all been received and interpreted, and the age, standing, and utilization facts have been evaluated or explicitly identified as unavailable.

### 5. Step 3 — payment history only after Step 2 results

Only after all three Step 2 tool results are available, unlock and call `get_payment_history_6183`:

```json
{
  "credit_card_account_id":"<canonical account id>",
  "months":3
}
```

Use `months: 6` for entry-tier and `months: 3` for mid-tier or premium-tier. Wait for its result. The required number of consecutive months must all be on time; insufficient history or a late payment in that required period fails payment history.

Normalize the complete results and run `scripts/cli_policy.py` again. Validate that every item in `checks` is `pass`, `fail`, or deliberately `unknown`; never convert unknown into pass/fail by inference.

### 6. Record a decision or preserve pending status

If the calculator returns `decision: "approve"`, unlock/call `approve_credit_limit_increase_5847` with the computed total new limit:

```json
{
  "credit_card_account_id":"<canonical account id>",
  "user_id":"<canonical user id>",
  "new_credit_limit":<proposed_new_credit_limit>
}
```

If it returns `decision: "deny"`, unlock/call `deny_credit_limit_increase_5848`:

```json
{
  "credit_card_account_id":"<canonical account id>",
  "user_id":"<canonical user id>",
  "denial_reason":"<calculator denial_reason>"
}
```

The helper emits only supported denial reasons: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, and `insufficient_payment_history`.

If the calculator returns `incomplete`, do not use approval or denial tools. Explain that the request remains pending because the required review could not be completed from available authoritative information, naming the unavailable category without inventing facts.

Offer escalation for an unresolved submitted request. If the customer affirmatively accepts, call `transfer_to_human_agents` using an applicable supported reason and a meaningful summary. The summary must include the request/reference ID when available, canonical account ID, canonical user ID, requested increase, completed checks and their outcomes, the specific unavailable or conflicting evidence, and that the CLI request remains pending.

### 7. Customer communication

- **Approval:** confirm approval and the new total credit limit.
- **Denial:** explain the applicable reason and practical next step.
- **Pending:** clearly say that no approval or denial has been made, the request remains pending, and the required review input that is unavailable.
- **Oversized request before submission:** state the maximum allowed increase and request a revised amount; it is neither submitted nor denied.

## Helper input/output contract

`scripts/cli_policy.py` accepts this JSON object. Currency values may be JSON numbers or strings such as `"$5000.00"`.

```json
{
  "card_tier":"premium-tier",
  "card_type":"Gold Rewards Card",
  "current_credit_limit":5000,
  "requested_increase_amount":2500,
  "account_open_date":"2023-03-20",
  "as_of_date":"2025-11-14",
  "last_approved_request_submitted_date":null,
  "current_balance":0,
  "utilization_percent":null,
  "has_active_disputes":false,
  "has_pending_replacement":false,
  "is_current_no_past_due":true,
  "consecutive_on_time_months":3
}
```

It emits `can_submit`, maximum/proposed amounts, ordered check states, `decision`, a permitted `denial_reason` if applicable, and `next_action`. Validate that the output has no `error`, `can_submit` is true before submission, and that no unknown check exists before a decision tool is used.
