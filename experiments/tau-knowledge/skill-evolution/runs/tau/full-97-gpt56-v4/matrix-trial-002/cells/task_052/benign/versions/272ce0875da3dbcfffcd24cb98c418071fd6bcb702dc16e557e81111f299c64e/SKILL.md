---
name: credit-limit-increase-processing
description: Process a credit-limit-increase (CLI) request for a verified cardholder. Use when a customer asks to raise a credit limit and the agent must validate tier rules, submit the formal request, perform every required eligibility check, and approve or deny it with the designated internal tools.
---

# Credit-limit-increase processing

Use this Skill for a customer-requested CLI. It implements the required ordering: validate the requested amount **before** submission; submit a valid request; complete all eligibility checks; then record exactly one decision and communicate it.

## Safety, identity, and account selection

1. Identify the customer and retrieve their credit-card accounts. Match the requested card to one account. If multiple plausible accounts remain, ask the customer to identify the correct account; never choose based on a partial match.
2. Before any state-changing CLI action, verify the cardholder using two of the four identity fields (date of birth, email, phone number, and address). The customer must supply/confirm the fields; do not reveal stored values as a challenge. Retrieve the user record, obtain the current timestamp with `get_current_time`, and call `log_verification` with the complete retrieved identity record and timestamp after two fields match.
3. Obtain a precise requested increase amount. A percentage is acceptable only after obtaining the current limit and converting it to dollars. The submission tool requires an integer dollar increase. If a percentage produces a fractional-dollar increase, ask for a whole-dollar amount. Confirm the customer intends the resulting amount if that has not already been made clear.
4. Determine the card tier from an authoritative account or program record before making a tier-specific eligibility decision. Do not treat a product name alone as proof of a tier. If the tier is not available, an increase at or below 25% of the current limit is within every documented maximum and can pass amount validation, but the missing tier must be resolved after submission before a decision. Do not guess a tier or approve/deny from an ambiguous mapping.

Use `scripts/cli_rules.py` for tier calculations and deterministic pass/fail checks. It reads one JSON object from standard input and emits one JSON object to standard output; see **Helper interface** below.

## Rules to apply

| Tier | Minimum age | Cooldown after approved request | Utilization must be below | Consecutive on-time months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | 70% | 6 | 25% of current limit |
| Mid-tier | 90 days | 90 days | 80% | 3 | 50% of current limit |
| Premium-tier | 60 days | 60 days | 90% | 3 | 50% of current limit |

Additional Bronze Rewards Card information states an approved total limit is in the $3,000–$32,500 range. Where that program cap applies, do not process a requested new total above $32,500; explain the allowed maximum and obtain a revised amount before any submission.

Treat a utilization equal to the threshold as failing. Calculate utilization as `current_balance / current_credit_limit * 100`; do not treat available credit as a balance. Account age qualifies on the minimum day.

A cooldown applies only if the **most recent prior** CLI request was approved. Measure it from that request's **submission date**, not its approval date. Exclude the request just created in the workflow below from the prior-request check. If the most recent prior request was denied, it does not create a cooldown; do not substitute an older approved request for it.

## Required tool preparation

Unlock these agent tools before using them:

- `submit_credit_limit_increase_request_7392`
- `get_credit_limit_increase_history_4829`
- `get_pending_replacement_orders_5765`
- `get_user_dispute_history_7291`
- `get_payment_history_6183`
- `approve_credit_limit_increase_5847`
- `deny_credit_limit_increase_5848`

Call a discovered agent tool only after it has been unlocked, using `call_discoverable_agent_tool` and a JSON-string `arguments` value. Calls in this list are recommendations for the live agent; the helper script never performs banking actions.

## End-to-end procedure

### A. Validate the amount before submission

1. Read the current credit limit and calculate the requested dollar increase and proposed new total.
2. If the authoritative tier is available, run the helper with that tier, current limit, and requested amount. It returns the maximum permitted increase and whether the amount is within the tier percentage rule. If the tier is not available, an increase at or below 25% of the current limit is within every documented tier maximum; do not delay submission of such an amount solely for tier mapping.
3. If the requested increase exceeds the known applicable tier maximum—or, when no tier is available, exceeds the 25%-of-limit amount that is valid for every tier—do **not** submit a request. Tell the customer the applicable known maximum and ask whether they want to proceed with that amount. Process only a newly confirmed valid amount.
4. If an applicable product total-limit cap would be exceeded, do **not** submit. Offer the difference between the cap and current limit if positive; otherwise explain that no increase is available.

### B. Submit the valid request

After identity is logged and the customer has confirmed a valid whole-dollar increase, submit it:

```json
{
  "credit_card_account_id": "<selected account id>",
  "user_id": "<verified user id>",
  "requested_increase_amount": 123
}
```

using `submit_credit_limit_increase_request_7392`. Retain the returned request identifier/date if supplied. Submission creates the formal request and is required before eligibility verification. Do not submit an excessive or unconfirmed amount.

### C. Complete every eligibility check after submission

Check every item even if an earlier item fails, so the audit is complete. Gather results rather than approving early.

1. **Account age:** Compare the account-open date with the current date using calendar-day differences and the selected tier minimum. If the tier mapping is unavailable, calculate against each documented minimum and retain the results pending mapping.
2. **Cooldown:** Call `get_credit_limit_increase_history_4829` with the account ID. Inspect request statuses and dates. Ignore the newly submitted pending request, then identify the most recent remaining request by submission date. Only if that request was approved, calculate days since its submission date against the tier cooldown. If it was denied, this check passes regardless of older approvals. Do not use a customer's approximate recollection when precise history is available. When tier is unavailable, calculate all documented cooldown outcomes but do not select a decision reason until mapping is resolved.
3. **Disputes:** Call `get_user_dispute_history_7291` with the user ID. Any dispute with a non-final active status, such as `open` or `under_review`, fails this requirement. Closed/resolved disputes do not by themselves fail it.
4. **Replacement cards:** Call `get_pending_replacement_orders_5765` with the account ID. An empty list passes. Any order not clearly `delivered` or `cancelled` fails; pending or shipped orders block processing.
5. **Good standing:** Review the selected account. It must be current and have no past-due balance. A positive past-due amount fails.
6. **Utilization:** Calculate from the current balance and current limit and compare strictly below the tier threshold. If tier mapping is unavailable, record results for all documented thresholds.
7. **Payment history:** Call `get_payment_history_6183` with the account ID and the tier-required number of months. If tier mapping is unavailable, request 6 months, which covers every documented requirement, and verify all six most-recent months are on time. Missing, late, or insufficient returned months fails for the applicable requirement.

If a required lookup is unavailable, malformed, or ambiguous—including a missing tier mapping needed to select a tier-specific result—do not approve or deny based on an assumption. Preserve the submitted request, explain that processing cannot be completed yet, and transfer/escalate for a technical/system-data issue rather than recording an inaccurate eligibility denial.

### D. Record one decision

If every check passes, calculate `new_credit_limit = current_credit_limit + requested_increase_amount` and call `approve_credit_limit_increase_5847`:

```json
{
  "credit_card_account_id": "<selected account id>",
  "user_id": "<verified user id>",
  "new_credit_limit": 0.0
}
```

If any check fails, call `deny_credit_limit_increase_5848` once, with the account ID, user ID, and one permitted reason. When several checks fail, use the first failure in this order, while retaining all gathered findings in the case context:

1. `insufficient_account_age`
2. `cooldown_period_active`
3. `pending_disputes`
4. `pending_replacement_card`
5. `past_due_balance`
6. `high_utilization`
7. `insufficient_payment_history`

Use `requested_amount_exceeds_limit` only if an amount-limit issue must be formally denied (normally it is caught before submission). Use `other` only for a documented applicable condition with no more specific enum; do not use it for a tool outage or unknown fact.

### E. Customer communication

For approval, confirm the approved increase and new total limit. For denial, state the applicable reason in customer-friendly terms and the concrete next step (for example, wait through the remaining cooldown, reduce utilization, or restore on-time payment history). Do not expose internal tool output, dispute details, or other sensitive account data. Do not claim eligibility or a decision until the corresponding decision tool has succeeded.

## Helper interface

Run from the package root, for example:

```sh
printf '%s' '{"tier":"Entry-tier","current_limit":"4000","requested_percent":"10","account_age_days":200,"days_since_prior_approved_request":121,"utilization_percent":"37.5","on_time_months":6}' | python3 scripts/cli_rules.py
```

Input is a JSON object with:

- Required: `tier` (`Entry-tier`, `Mid-tier`, or `Premium-tier`), `current_limit` (positive number), and exactly one of `requested_increase_amount` or `requested_percent`.
- Optional eligibility facts: `account_age_days`, `days_since_prior_approved_request`, `utilization_percent`, `on_time_months`, and `prior_request_was_approved` (defaults to `true` only when a days-since value is supplied).

Output includes normalized requested amount, proposed new limit, maximum increase, rule values, individual check values (`true`, `false`, or `null` when not supplied), and `all_supplied_checks_pass`. Amounts are decimal strings to avoid floating-point currency errors. The script rejects invalid tiers, nonpositive limits, missing/conflicting request forms, negative facts, and percentage requests that do not resolve to an exact whole-dollar submission amount.
