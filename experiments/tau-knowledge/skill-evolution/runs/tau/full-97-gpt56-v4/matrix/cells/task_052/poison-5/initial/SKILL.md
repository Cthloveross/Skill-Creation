---
name: credit-limit-increase-processing
description: Process a credit-card credit-limit-increase (CLI) request when a customer, account, requested increase, and normal banking/discoverable tools are available. Applies tier-specific amount limits, submits a valid request before reviewing eligibility, then approves or denies with the required audit action and customer communication.
---

# Credit Limit Increase Processing

Use this Skill for a customer request to increase a credit-card limit. It follows the required sequence: validate the requested increase first; submit a valid request; perform every eligibility check; retrieve payment history; then record exactly one approval or denial decision.

## Required runtime facts

Obtain or confirm:

- the customer `user_id` and the intended `credit_card_account_id`;
- card tier (Entry, Mid, or Premium), current credit limit, balance, account-open date, account status, and past-due amount;
- a requested **dollar increase**. If the customer gives a percentage, calculate it from the current credit limit and state the dollar amount being processed. Clarify an ambiguous percentage before acting;
- the current timestamp for date calculations.

Use account lookup tools to locate the account. If the runtime requires identity verification before account actions, obtain confirmation of two identity fields and call `log_verification` with all required account-profile fields and the current timestamp. Do not treat profile data displayed by a lookup as customer confirmation.

Card tier policy:

| Tier | Minimum age | Cooldown after approved CLI | Utilization must be below | Payment months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry | 120 days | 120 days | 70% | 6 | 25% of current limit |
| Mid | 90 days | 90 days | 80% | 3 | 50% of current limit |
| Premium | 60 days | 60 days | 90% | 3 | 50% of current limit |

For known card products, classify Bronze Rewards Card as Entry tier. If the tier cannot be established from supported information, do not guess; explain that the request cannot be processed until the card tier is confirmed.

## 1. Validate amount before submission

Calculate the maximum permitted dollar increase from the current limit. For a percentage request, calculate `current_limit × percentage / 100`; preserve cents only if the banking system supports them, otherwise obtain a whole-dollar amount consistent with the customer’s request.

If the requested increase exceeds the tier maximum, **do not submit a CLI request**. Tell the customer the maximum permitted increase and ask whether they want to request that amount or a lower amount. Do not deny a request that was never allowed to be submitted.

For a valid request, retain:

- `requested_increase_amount` as the validated dollar increase;
- `new_credit_limit = current_credit_limit + requested_increase_amount`.

`scripts/cli_policy.py` can calculate these values and evaluate collected observations. It does not make banking actions.

## 2. Submit before eligibility review

For a valid amount, unlock and call `submit_credit_limit_increase_request_7392` using:

```json
{"credit_card_account_id":"<account>","user_id":"<user>","requested_increase_amount":<integer>}
```

A submission is required before any eligibility decision. If submission fails or returns an ambiguous outcome, do not retry blindly and do not approve or deny until the record status is known.

## 3. Complete every eligibility check

After a successful submission, unlock and call all applicable tools, retaining their results for the decision record:

1. `get_credit_limit_increase_history_4829` with `credit_card_account_id`.
   - Apply cooldown only when the most recent relevant request was **approved**. Denied requests do not trigger cooldown.
   - The next eligible submission date is the approved request submission date plus the tier cooldown days. A full cooldown must have elapsed.
2. `get_user_dispute_history_7291` with `user_id`.
   - Any active/non-final dispute status (such as `open` or `under_review`) fails the pending-disputes check. Closed disputes do not by themselves fail it.
3. `get_pending_replacement_orders_5765` with `credit_card_account_id`.
   - An empty collection passes. Any order not clearly `delivered` or `cancelled` fails the replacement-card check.
4. Check account standing from the account record. It must be current/active as applicable and have no past-due balance. A past-due amount above zero fails this check.
5. Calculate utilization as `current_balance / current_credit_limit × 100`. It must be strictly below the tier threshold; equality fails.
6. Determine account age from the account-open date and current date. The account must be at least the tier minimum age; the day the minimum is reached passes.
7. Unlock and call `get_payment_history_6183` with `credit_card_account_id` and exactly the tier’s required `months` value. The returned months must show the required consecutive on-time payment history.

Do not stop checking merely because one criterion has failed: complete all required checks for the audit record unless a tool failure makes a fact unknowable. If a required result is unavailable, malformed, or ambiguous, do not invent a pass. Record a defensible denial with `other` if a decision must be recorded, and explain that the eligibility review could not be completed; otherwise follow supported escalation procedures.

## 4. Record one decision

If every check passes, unlock and call `approve_credit_limit_increase_5847`:

```json
{"credit_card_account_id":"<account>","user_id":"<user>","new_credit_limit":<current_limit_plus_increase>}
```

If any check fails, unlock and call `deny_credit_limit_increase_5848` with the account, user, and the applicable permitted reason:

- account age: `insufficient_account_age`
- approved-request cooldown: `cooldown_period_active`
- active dispute: `pending_disputes`
- non-final replacement order: `pending_replacement_card`
- past-due/not-current account: `past_due_balance`
- utilization at or over threshold: `high_utilization`
- insufficient required consecutive on-time payments: `insufficient_payment_history`
- amount was somehow submitted despite exceeding policy: `requested_amount_exceeds_limit`
- unavailable/ambiguous required evidence or another supported failure: `other`

Use the primary applicable reason if several fail, while retaining all failed checks in the case record. Never call both approval and denial for the same submission.

## 5. Customer response

For approval, confirm the dollar increase and the resulting new total credit limit. For denial, plainly state the applicable reason and a concrete next step where supported (for example, the cooldown end date, resolving a dispute/replacement order, curing past due, lowering utilization, or building payment history). Do not expose internal-only eligibility details beyond an appropriate customer explanation.

## Script interface

Run the policy helper with JSON on stdin:

```json
{
  "card_tier":"entry",
  "current_credit_limit":4000,
  "requested":{"kind":"percent","value":10},
  "current_balance":1500,
  "account_open_date":"2023-05-10",
  "current_time":"2025-11-14 03:40:00 EST",
  "last_approved_request_date":null,
  "has_active_disputes":false,
  "has_nonfinal_replacement_order":false,
  "past_due_amount":0,
  "payment_history_consecutive_on_time_months":6
}
```

It emits JSON with normalized requested amount, maximum, proposed new limit, metrics, pass/fail checks, and a permitted recommended denial reason. Supply facts from live account and tool responses; missing facts remain unevaluated and must be resolved before approval.
