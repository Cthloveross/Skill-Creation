---
name: credit-limit-increase-processing
description: Process a credit-card credit limit increase request after the customer has agreed to a valid increase amount. Use for tier-specific maximum-increase validation, mandatory post-submission eligibility checks, and the required approval or denial record.
---

# Credit Limit Increase Processing

Use this Skill to process a CLI request for the account owner. It preserves the required sequence: validate the agreed amount first, submit a valid request, check **every** eligibility condition, then record one final decision.

## Required runtime facts

Obtain or retain the following from the live account and tool responses:

- `user_id`, `credit_card_account_id`, card tier or recognized card type
- Current credit limit, current balance, account open date, account status, and past-due amount
- Current timestamp
- Customer's final agreed increase amount in whole dollars
- CLI history, dispute history, replacement-order result, and payment-history result

Use the platform's applicable identity/authorization process before acting for a customer. If identity verification is required by that process, confirm two of the supported identity fields before calling `log_verification`; do not invent or log unverified fields.

## Tier rules

| Tier | Minimum age | Cooldown after an approved CLI request | Utilization must be below | Consecutive on-time months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | 70% | 6 | 25% of current limit |
| Mid-tier | 90 days | 90 days | 80% | 3 | 50% of current limit |
| Premium-tier | 60 days | 60 days | 90% | 3 | 50% of current limit |

Bronze Rewards Card is an entry-tier card. Supply `card_tier` directly when possible; the helper also recognizes the documented entry-tier card-type names.

A request amount is valid only when it is a positive whole-dollar amount no greater than the applicable percentage of the current limit. Since the submission tool accepts an integer dollar amount, the largest permitted whole-dollar request is the percentage maximum rounded down to whole dollars.

For cooldown evaluation, use the most recent **approved** CLI request's submission timestamp. Denied requests do not start a cooldown. The customer is eligible when the entire tier cooldown has elapsed. Utilization equal to the threshold is ineligible because the requirement is strictly below the threshold.

## Mandatory execution procedure

1. Identify the account requested by the customer and determine the tier, current limit, and final agreed increase amount. Do not use a tentative or superseded amount.
2. Run the helper in `preflight` mode using the live tier, limit, and agreed amount. If it is invalid or exceeds the maximum:
   - do **not** submit a CLI request;
   - explain the maximum allowed and ask the customer to choose a valid amount.
   - If the customer revises the amount, start this amount-validation step again.
3. For a valid amount, unlock and call `submit_credit_limit_increase_request_7392` first:
   ```text
   credit_card_account_id: account ID
   user_id: customer ID
   requested_increase_amount: validated integer dollar amount
   ```
   Submission creates the required formal record; do not perform the eligibility tool calls before it.
4. After successful submission, complete every eligibility check, even if an earlier check will lead to denial. Unlock each discoverable tool before calling it:
   - `get_credit_limit_increase_history_4829` with `credit_card_account_id`.
   - `get_user_dispute_history_7291` with `user_id`. Any open, under-review, pending, or otherwise non-final dispute is active. Closed/resolved disputes do not block the request.
   - `get_pending_replacement_orders_5765` with `credit_card_account_id`. An empty result passes. Any order not clearly `delivered` or `cancelled` blocks processing, including pending or shipped orders.
   - `get_payment_history_6183` with `credit_card_account_id` and the tier's required month count. Confirm that the required number of consecutive months are on time.
   - From the current account record, calculate account age, confirm the account is current with no past-due balance, and calculate utilization as `current_balance / current_credit_limit * 100`.
5. Normalize the tool results into the `evaluate` input described below and run the helper. The helper makes all tier boundary comparisons deterministically and reports each check.
6. If all checks pass, unlock and call `approve_credit_limit_increase_5847` with:
   ```text
   credit_card_account_id: account ID
   user_id: customer ID
   new_credit_limit: helper's new_credit_limit
   ```
7. If all checks were completed and one or more fail, unlock and call `deny_credit_limit_increase_5848` with the account ID, user ID, and the helper's `denial_reason`. This is always one of the permitted reason enums. The helper selects a stable primary reason but still reports all failures.
8. If an eligibility lookup is unavailable, malformed, or incomplete, retry/obtain the missing verification data. Do not approve on incomplete evidence and do not mislabel an unknown result as a passed check. Keep the submitted request pending while verification is incomplete.
9. Communicate the recorded decision. For an approval, state the new total limit. For a denial, explain the applicable reason and next steps. For `cooldown_period_active`, state the helper's `eligible_on` timestamp. For utilization, advise reducing the balance below the tier threshold; for a replacement, explain that delivery or cancellation is required.

## Helper interface

Run from the package root with a runtime-generated JSON document:

```text
python3 scripts/cli_decision.py < /path/to/cli_facts.json
```

The script reads one JSON object on standard input and writes one JSON object on standard output. It uses only the Python standard library and does not call banking tools or change account state.

### `preflight` input

```json
{
  "mode": "preflight",
  "card_tier": "entry-tier | mid-tier | premium-tier",
  "card_type": "optional documented card type when card_tier is absent",
  "current_credit_limit": "decimal amount",
  "requested_increase_amount": "integer dollar amount"
}
```

`requested_increase_amount` must be a JSON integer, not a decimal string. A successful result includes `max_increase_amount`, `new_credit_limit`, and `valid_amount: true`. An unsuccessful result includes `errors`; use it to obtain a corrected customer amount rather than submitting.

### `evaluate` input

Start with all `preflight` fields and add:

```json
{
  "mode": "evaluate",
  "current_time": "timestamp or date",
  "account_open_date": "timestamp or date",
  "current_balance": "decimal amount",
  "account_status": "ACTIVE, CURRENT, or other live status",
  "past_due_amount": "decimal amount",
  "most_recent_approved_request_at": "timestamp/date or null",
  "disputes": [{"status": "status from dispute lookup"}],
  "replacement_orders": [{"status": "status from replacement lookup"}],
  "consecutive_on_time_months": "integer derived from payment history"
}
```

An empty `disputes` or `replacement_orders` array is valid and means none were returned. Omit neither key: omission means that lookup was not verified. `most_recent_approved_request_at: null` means the history contains no approved request. A successful complete result has `action` equal to `approve` or `deny`; use its `checks` array as the audit summary. `action: obtain_missing_verification` identifies facts that must be collected before a decision.

## Output validation before banking action

- Confirm `valid_amount` is true before submission.
- Confirm the evaluation's `complete` is true before approval or denial.
- Confirm an approval result has `eligible: true` and use exactly its calculated `new_credit_limit`.
- Confirm a denial result has `eligible: false` and a `denial_reason` in the denial tool's documented enum.
- Preserve the submitted amount, account ID, user ID, tool outcomes, and final decision in the normal case/audit record.
