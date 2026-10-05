---
name: credit-limit-increase-processing
description: Verify a cardholder, submit and process a credit-limit increase (CLI) request using the required banking tools. Use for a requested increase or desired total limit when the account tier, account record, and required eligibility data can be obtained.
---

# Credit-limit increase processing

## Scope and required inputs

Use this Skill only for an account owner or authorized account manager requesting a CLI. Obtain and retain:

- the customer's requested **increase amount** (or convert an unambiguous requested new total to `new_total - current_limit`),
- a verified `user_id` and `credit_card_account_id`,
- card tier, current limit, account opening date, balance/status data, and the current time.

The requested increase must be a positive whole-dollar integer because the submission tool requires an integer amount. Do not round a customer request without their confirmation. The customer reason may be recorded as context, but it is not an eligibility criterion in the supplied policy.

### Identity gate

Before accessing or acting on a selected account, verify two of the four identity fields: date of birth, email, phone number, and mailing address. Match customer-provided values against the user record; a lookup result itself is not customer confirmation. Do not disclose stored values to solicit confirmation. Once two fields match, call `log_verification` with the complete record values and a freshly obtained `get_current_time` timestamp.

If fewer than two fields have been confirmed, ask for one remaining field. Do not submit, approve, or deny a CLI while verification is incomplete. Treat an out-of-scope/non-answer response as not verified.

## Tier rules

Use these CLI tiers only when the card/account record or applicable product information establishes the tier:

| Tier | Minimum age | Cooldown | Utilization must be | On-time months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| entry | 120 days | 120 days | below 70% | 6 | 25% of current limit |
| mid | 90 days | 90 days | below 80% | 3 | 50% of current limit |
| premium | 60 days | 60 days | below 90% | 3 | 50% of current limit |

Gold Rewards Card is a premium-tier card. Do not infer a tier for another product merely from its name. If the tier cannot be established, stop before submission and obtain an authoritative tier classification.

Run `scripts/evaluate_cli.py` to calculate the maximum increase, age/cooldown dates, utilization, and a deterministic preliminary outcome. It does not replace tool checks or trigger banking actions.

## Required procedure

Follow the ordering below exactly once identity is verified and the intended account is identified.

1. **Check the requested amount before submitting.** Get the current account record and tier. Calculate the maximum increase from its current credit limit. If the request is above the maximum, do **not** submit a request and do not call the denial tool. Tell the customer the maximum permissible increase and ask whether they want that amount or another valid amount. This pre-submission restriction takes precedence over later denial handling.
2. **Submit the valid request before eligibility review.** Unlock and call `submit_credit_limit_increase_request_7392` with `credit_card_account_id`, `user_id`, and `requested_increase_amount`. Do not substitute the new total for the increase. If submission fails or is ambiguous, do not proceed to approval or denial; resolve the submission status first.
3. **Check every criterion after successful submission.** Preserve the results for the audit trail, including checks that occur after the first failure.
   - Account age: compare the opening date to current time and the tier minimum. A threshold date qualifies.
   - Cooldown: unlock/call `get_credit_limit_increase_history_4829` with the account ID. Inspect the most recent **approved** request; denied requests do not create a cooldown. If an approved request is too recent, calculate its next eligible date as submission date plus the tier cooldown.
   - Disputes: unlock/call `get_user_dispute_history_7291` with `user_id`. Any non-final/open or under-review dispute is active and fails this criterion. Closed disputes alone pass.
   - Replacement cards: unlock/call `get_pending_replacement_orders_5765` with account ID. Fail if any order is not clearly `delivered` or `cancelled`; an empty order list passes.
   - Good standing: use an authoritative account result that explicitly reports whether the account is current/past due. A zero balance is not by itself proof that there is no past-due balance.
   - Utilization: calculate `current_balance / credit_limit * 100` from contemporaneous account data. It must be strictly below the tier threshold. A zero credit limit is invalid data, not a passing utilization check.
   - Payment history: unlock/call `get_payment_history_6183` using the account ID and the tier's required month count. Confirm that the response contains that many consecutive months and every required month is on time.
4. **Make exactly one final decision after all checks have been attempted.** If every required check passes, unlock/call `approve_credit_limit_increase_5847` with `new_credit_limit = current_credit_limit + requested_increase_amount`. Preserve cents where applicable and provide a numeric float as required by the tool.

   If one or more checks fail, unlock/call `deny_credit_limit_increase_5848` once using the most specific applicable permitted reason. Use this priority if multiple checks fail: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, `insufficient_payment_history`, then `other`. Use `requested_amount_exceeds_limit` only for a previously submitted request where an amount failure must be recorded; normally oversized requests are caught before submission.

If a required post-submission data source is unavailable, malformed, or does not establish the result, do not approve on an assumption. Record that review cannot be completed and obtain the authoritative data or use the organization’s approved escalation path. Do not use `other` to deny merely because a tool has failed unless policy or an authorized reviewer directs it.

## Tool-use sequence

Discoverable agent tools must be unlocked before calling them. The tools and exact arguments are:

- `submit_credit_limit_increase_request_7392`: `{credit_card_account_id, user_id, requested_increase_amount}`
- `get_credit_limit_increase_history_4829`: `{credit_card_account_id}`
- `get_user_dispute_history_7291`: `{user_id}`
- `get_pending_replacement_orders_5765`: `{credit_card_account_id}`
- `get_payment_history_6183`: `{credit_card_account_id, months}`
- `approve_credit_limit_increase_5847`: `{credit_card_account_id, user_id, new_credit_limit}`
- `deny_credit_limit_increase_5848`: `{credit_card_account_id, user_id, denial_reason}`

Use the regular read-only account/user tools to identify the verified owner, account, dates, limits, balances, and any explicit standing field. Never fabricate a tool response or a missing account-status field.

## Customer communication

For a pre-submission oversized request, state the maximum increase and invite a revised amount. After approval, confirm the new total credit limit. After denial, state the customer-appropriate reason and, where applicable, the next action: the account-age threshold date, cooldown end date, reducing utilization, resolving a dispute/replacement, becoming current, or building the required on-time-payment history. Do not expose internal eligibility implementation or sensitive account data unnecessarily.

## Helper interface and validation

Run the packaged helper by passing one JSON object on stdin, for example:

```json
{"tier":"premium","current_limit":"5000.00","current_balance":"0.00","requested_increase":2500,"opened_on":"2023-03-20","now":"2025-11-14","last_approved_request_on":null,"payment_history_pass":true,"has_active_dispute":false,"has_pending_replacement":false,"is_past_due":false}
```

It emits one JSON object with computed thresholds, individual checks, a decision state, and the applicable denial reason. Validate that `input_errors` is empty, the computed maximum agrees with the account value, all check values are non-null before treating `decision` as final, and that the approval total equals current limit plus requested increase. A result of `needs_data` is not approval authority.
