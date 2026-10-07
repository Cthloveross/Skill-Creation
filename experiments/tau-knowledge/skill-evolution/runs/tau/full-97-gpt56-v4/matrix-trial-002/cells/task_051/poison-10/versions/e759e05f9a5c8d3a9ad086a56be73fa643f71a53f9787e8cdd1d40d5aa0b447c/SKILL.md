---
name: credit-limit-increase-processing
description: Process a confirmed credit-card credit-limit-increase request: verify identity and ownership, validate tier limits, submit the request, complete all required eligibility checks, then record an approval or permitted denial using the normal banking tools.
---

# Credit Limit Increase Processing

Use this Skill when an account owner asks to increase a credit-card limit and has supplied a specific increase amount (or confirms a converted amount from a requested total). Do not use it for a general explanation of CLI policy only.

## Required prerequisites

Before **any** banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements as applicable.

1. Obtain and confirm two of the four identity fields: date of birth, email, phone number, and address.
2. Look up the matching customer and credit-card account. Confirm that the account belongs to the verified user and that the customer is the account owner or authorized account manager.
3. Call `log_verification` only after two fields have been confirmed. Supply all returned customer fields and the current timestamp.
4. Confirm the card tier, current limit, current balance, account status, past-due amount, requested increase amount, and customer confirmation of that amount. A request expressed as a desired new total must be converted to `desired_total - current_limit`; do not proceed if it is zero or negative.

If identity, authority, ownership, amount, or account data cannot be confirmed, do not submit or decide a request. Ask for the missing information or use an appropriate supported escalation path.

## Tier policy

Map the card product to its documented tier. Do not guess a tier when the product is ambiguous.

| Tier | Minimum age | Cooldown | Utilization requirement | On-time months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | strictly below 70% | 6 consecutive | 25% of current limit |
| Mid-tier | 90 days | 90 days | strictly below 80% | 3 consecutive | 50% of current limit |
| Premium-tier | 60 days | 60 days | strictly below 90% | 3 consecutive | 50% of current limit |

Calculate utilization as `current_balance / current_credit_limit * 100`. A balance exactly at the threshold fails. Calculate maximum increase from the **current** credit limit; retain exact currency arithmetic and do not round up a maximum.

Before submitting anything, compare the confirmed requested increase with the applicable maximum. If it exceeds the maximum, tell the customer the maximum and ask whether they want to submit a revised, valid amount. Do not submit the excessive request. If the customer declines or does not provide a valid replacement amount, end without a banking action.

## Required tool workflow

Tool names below are normal banking tools documented for this workflow. Unlock each discoverable agent tool before its first call, then call it through `call_discoverable_agent_tool` with a JSON arguments string.

After all prerequisites and the pre-submission amount check pass, perform these steps in this exact order:

1. **Submit first.** Unlock and call `submit_credit_limit_increase_request_7392` with:
   ```json
   {"credit_card_account_id":"<account_id>","user_id":"<user_id>","requested_increase_amount":<integer_dollars>}
   ```
   Do not perform CLI eligibility checks before this formal submission.
2. **Check every eligibility item for the audit record**, even when one earlier item fails:
   - Determine account age from `date_of_account_open` and the current date.
   - Unlock and call `get_credit_limit_increase_history_4829` with `credit_card_account_id`. Apply the tier cooldown only to the most recent **approved** request. Denied requests do not start the cooldown. If a qualifying approved request is within the cooldown, compute and retain the date when the full cooldown elapses.
   - Unlock and call `get_user_dispute_history_7291` with `user_id`. Treat statuses such as `open` and `under_review` as active; a closed dispute is not active.
   - Unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id`. Treat any order not clearly `delivered` or `cancelled` as pending.
   - Check good standing from the account record: it must be current/active as applicable and have no past-due balance.
   - Calculate utilization from the current balance and current limit.
   - Unlock and call `get_payment_history_6183` with `credit_card_account_id` and the tier-required number of months. Verify the required number of consecutive months are all on time.
3. Use `scripts/evaluate_cli.py` if useful to make the date, threshold, maximum, and denial mapping deterministic. The script is advisory only; compare its normalized inputs with actual tool results and never let it execute bank actions.
4. **Record one decision.** If every check passes, unlock and call `approve_credit_limit_increase_5847` with:
   ```json
   {"credit_card_account_id":"<account_id>","user_id":"<user_id>","new_credit_limit":<current_limit_plus_requested_increase>}
   ```
   If any check fails, unlock and call `deny_credit_limit_increase_5848` with the same account and user identifiers plus one allowed `denial_reason`. Use the first applicable reason in this deterministic order: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, `insufficient_payment_history`, `requested_amount_exceeds_limit`, then `other`.

Never approve merely because the customer has a stated purpose for the increase. Do not call approve or deny if submission itself did not succeed; explain that processing could not be completed and escalate only when supported.

## Customer communication

After a successful approval record, state that the increase was approved and give the resulting total limit. After a denial record, explain the applicable reason without exposing internal-only checks. For an account-age, cooldown, utilization, or payment-history denial, provide the documented reapplication condition or date when it can be determined. For pending disputes or a replacement card, explain that it must be resolved, delivered, or cancelled before reapplying.

## Helper input and output

`scripts/evaluate_cli.py` reads one JSON object from stdin and emits one JSON object to stdout. It does not access banking systems. Input fields are:

```json
{
  "tier":"entry|mid|premium",
  "as_of_date":"YYYY-MM-DD",
  "account_open_date":"YYYY-MM-DD",
  "current_credit_limit":"decimal string or number",
  "current_balance":"decimal string or number",
  "requested_increase":"decimal string or number",
  "approved_request_dates":["YYYY-MM-DD"],
  "has_active_dispute":false,
  "has_pending_replacement":false,
  "past_due_amount":"decimal string or number",
  "payment_months_on_time":6
}
```

It emits tier thresholds, computed maximum and new limit, utilization, individual eligibility booleans, an optional cooldown eligible date, and the prescribed decision/denial reason. Dates must be calendar dates, monetary fields must be nonnegative, and the requested increase must be an integer number of dollars for submission. Invalid or missing fields produce `{"ok": false, "error": "..."}`; obtain corrected data rather than treating such an error as a denial.

Example runnable call (replace all placeholder values with live, verified data):

```sh
python3 scripts/evaluate_cli.py <<'JSON'
{"tier":"entry","as_of_date":"YYYY-MM-DD","account_open_date":"YYYY-MM-DD","current_credit_limit":"0","current_balance":"0","requested_increase":"0","approved_request_dates":[],"has_active_dispute":false,"has_pending_replacement":false,"past_due_amount":"0","payment_months_on_time":6}
JSON
```

Before recording the bank decision, validate that the script output is `ok: true`, its requested amount and account figures match the live records, `new_credit_limit` equals current limit plus requested increase, and its result matches the checked tool evidence.