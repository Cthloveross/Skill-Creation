---
name: credit-limit-increase-processing
description: Process a credit-limit-increase (CLI) request for a known credit-card account, including tier limits, mandatory post-submission eligibility checks, approval/denial actions, and customer communication.
---

# Credit Limit Increase Processing

Use this Skill when a cardholder asks to increase a credit limit and agent banking tools are available. Do not use it for provisional-credit or account-closure workflows.

## Policy rules

CLI tiers and requirements are:

| Tier | Minimum account age | Cooldown after an **approved** CLI request | Utilization must be below | Consecutive on-time payments | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry | 120 days | 120 days | 70% | 6 months | 25% of current limit |
| Mid | 90 days | 90 days | 80% | 3 months | 50% of current limit |
| Premium | 60 days | 60 days | 90% | 3 months | 50% of current limit |

Treat Bronze Rewards Card as Entry tier for this workflow. The utilization comparison is strict: equality with the threshold is ineligible. A denied prior CLI does not create a cooldown; calculate the cooldown from the most recent *approved request's submission date*, not its approval date.

The account must also have no active dispute, no replacement order in a non-final status, and be current with no past-due balance. A replacement order is blocking unless every returned order is delivered or cancelled.

## Required workflow

1. **Identify the account safely.** Obtain the account owner and the exact credit-card account. If the supplied name/email matches multiple users or the user has multiple plausible accounts, ask the customer to disambiguate before acting. Confirm the requested account is the intended one; do not expose unrelated account details.
2. **Normalize the request.** Obtain a definite dollar increase. A customer may state a percentage; calculate it from the current credit limit and clearly state the resulting dollar amount. Use `scripts/cli_rules.py` to calculate the amount and maximum. A stated percentage is an unambiguous requested amount when it produces a monetary value; ask a follow-up only if the amount cannot be determined or is not a positive whole-dollar increase.
3. **Perform the amount gate before any submission.** Determine the applicable tier and current limit. If the amount exceeds the tier maximum, do **not** submit a request. Tell the customer the maximum dollar increase and ask whether they want to proceed with that amount. Do not approve or deny through CLI decision tools at this point.
4. **Submit a valid request first.** For an in-range amount, unlock and call `submit_credit_limit_increase_request_7392` with `credit_card_account_id`, `user_id`, and the positive integer `requested_increase_amount`. A successful submission creates the audit record; do not skip it because the customer appears ineligible.
5. **After submission, check every required criterion before deciding.** Unlock and use:
   - `get_credit_limit_increase_history_4829` with the card account ID. Inspect status and submission dates, and apply cooldown only to approved requests.
   - `get_user_dispute_history_7291` with the user ID. Treat open, under_review, or another non-final/active dispute status as blocking.
   - `get_pending_replacement_orders_5765` with the card account ID. Treat pending, shipped, or any status other than delivered/cancelled as blocking.
   - `get_payment_history_6183` with the card account ID and the tier-required number of months. Verify all requested consecutive months are on time.

   Also use the account data and current time to calculate account age, utilization (`current_balance / credit_limit * 100`), account status, and past-due amount. Check age, cooldown, disputes, replacement orders, good standing/no past due, utilization, and payment history even if an earlier check already failed. If a required lookup is unavailable, ambiguous, or malformed, do not fabricate a result; retain the submitted request and escalate/transfer for a technical-system issue rather than approving it.
6. **Record exactly one decision after the checks.** If every condition passes, unlock and call `approve_credit_limit_increase_5847` with the account ID, user ID, and `new_credit_limit = current_credit_limit + requested_increase_amount`. Otherwise unlock and call `deny_credit_limit_increase_5848` with the account ID, user ID, and the most applicable allowed reason:
   - `insufficient_account_age`
   - `cooldown_period_active`
   - `pending_disputes`
   - `pending_replacement_card`
   - `past_due_balance`
   - `high_utilization`
   - `insufficient_payment_history`
   - `requested_amount_exceeds_limit` (normally prevented by the pre-submission amount gate)
   - `other` only when none of the listed reasons fit.

   Do not call approve after a deny, retry a request/decision after an unknown result, or make a decision based solely on a customer's statement.
7. **Communicate succinctly.** For approval, confirm the dollar increase and new total limit. For denial, state the applicable reason and a useful next step (for example, the cooldown-end date when it can be calculated). Correct misconceptions politely: Bronze/Entry tier has a 120-day cooldown, not 60 days. Do not disclose internal tool records or unrelated personal data.

## Tool unlocking sequence

The named CLI tools are discoverable agent tools. Before each first use, call `unlock_discoverable_agent_tool` for the exact tool name, then invoke it using `call_discoverable_agent_tool` with a JSON-string `arguments` payload. The Skill does not execute banking actions automatically; the executor must make the tool calls in the workflow above.

## Calculator helper

Run the packaged helper with JSON on standard input; it emits JSON on standard output.

Example input shape (illustrative only):
```json
{"tier":"entry","current_credit_limit":4000,"current_balance":1500,"requested_percent":10}
```

The output contains normalized requested amount, maximum allowable increase, proposed new limit, utilization, and local amount/utilization conclusions. It does not replace live account, history, dispute, replacement-order, payment-history, or decision-tool checks.

Suggested runtime call:
```text
python3 scripts/cli_rules.py <<'JSON'
{"tier":"entry","current_credit_limit":4000,"current_balance":1500,"requested_percent":10}
JSON
```

Before using a helper result, ensure its tier and monetary inputs came from the current account and customer request. Validate that `amount_within_limit` is true before submitting and that the requested amount is a positive whole dollar. For final approval, independently confirm all externally checked fields are eligible and use the helper's `new_credit_limit` only if it equals the live current limit plus the submitted increase.
