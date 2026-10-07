---
name: credit-limit-increase-processing
description: Process a credit-card credit-limit-increase (CLI) request using the required submit-first review workflow, tier-specific limits, eligibility checks, decision tools, and customer communication. Use when a customer requests a CLI and the normal banking tools are available.
---

# Credit Limit Increase Processing

## Scope and prerequisites

Use this Skill for a customer-requested increase to an existing credit-card account. The executor must obtain the account owner, the intended card account, current limit/balance, tier, and a specific requested **increase** amount. Do not treat a requested new total limit as an increase without clarifying which amount the customer wants added.

Use authoritative account and tool results rather than customer recollection for eligibility. The customer's reason may be recorded as context but is not an eligibility criterion in this workflow.

The applicable tier rules are:

| Tier | Minimum age | Approved-request cooldown | Utilization must be below | Consecutive on-time months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | 70% | 6 | 25% of current limit |
| Mid-tier | 90 days | 90 days | 80% | 3 | 50% of current limit |
| Premium-tier | 60 days | 60 days | 90% | 3 | 50% of current limit |

Map a card to a tier only when the account/card records establish that mapping. If its tier cannot be determined, do not guess a tier or a limit; obtain the needed authoritative information or route the case for assistance.

## Required order of operations

1. **Locate and validate the account.** Identify the user and retrieve their credit-card accounts. Confirm that the selected account belongs to that user and is the card for which they are requesting the increase. Obtain the current credit limit, current balance, and account-open date from the account record. Get the current timestamp for the review record.
2. **Validate the requested amount before submission.** The requested increase must be a positive whole-dollar amount because the submission tool accepts an integer. Calculate the tier maximum from the current credit limit. An amount equal to the maximum is allowed; an amount over it is not.
   - Run `scripts/cli_policy.py` to calculate the amount maximum and date/utilization checks consistently, or perform equivalent exact decimal arithmetic.
   - If the requested amount exceeds the maximum, do **not** submit a CLI request and do not call an approval/denial mutation. Tell the customer the maximum permitted increase and ask whether they want to submit a new, valid amount.
   - If the amount, account, tier, or current limit is unavailable or ambiguous, resolve that information before submitting.
3. **Submit the valid request before performing eligibility checks.** Unlock `submit_credit_limit_increase_request_7392`, then call it with `credit_card_account_id`, `user_id`, and `requested_increase_amount`. Retain its result as the formal request record. A valid request is submitted even if a later eligibility check will lead to denial.
4. **Perform every required eligibility check after submission.** Unlock and call all relevant tools below. Do not stop after discovering one failing condition; complete the review/audit checks before deciding.
   - `get_credit_limit_increase_history_4829` with `credit_card_account_id`. Only an **approved** prior CLI request triggers cooldown. Denied requests do not. Find the most recent approved request submission date and deny for cooldown if fewer than the tier's required full days have elapsed. The next eligibility time is that submission timestamp plus the cooldown days.
   - `get_user_dispute_history_7291` with `user_id`. Treat a dispute with an active/nonfinal status (such as `open` or `under_review`) as pending. Closed/resolved disputes alone are not pending.
   - `get_pending_replacement_orders_5765` with `credit_card_account_id`. A pending or otherwise nonfinal order blocks the CLI. An empty collection, or a collection in which every order is delivered or cancelled, does not.
   - `get_payment_history_6183` with `credit_card_account_id` and the tier's required `months`. Confirm that all required consecutive months are on time. A vague or incomplete response is not proof of qualifying payment history.
   - Verify account age from the account-open date and current time; the age is eligible on the day the tier minimum is reached.
   - Verify good standing from authoritative account status/past-due data. Any past-due amount fails this criterion. Do not replace this check with a customer statement.
   - Verify utilization using an authoritative utilization value, or calculate `current_balance / current_credit_limit * 100` from authoritative account data. It must be strictly below the tier threshold; exactly at the threshold fails.
5. **Record and apply the decision.** Use only the normal decision tool matching the outcome:
   - If all checks pass, unlock and call `approve_credit_limit_increase_5847` with `credit_card_account_id`, `user_id`, and `new_credit_limit` as a float equal to current limit plus requested increase.
   - If one or more verified requirements fail, unlock and call `deny_credit_limit_increase_5848` with the account/user IDs and one permitted `denial_reason`: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, or `insufficient_payment_history` as applicable. `requested_amount_exceeds_limit` applies only if a request was somehow already submitted contrary to the required pre-validation; normally an excessive amount is never submitted. If no listed reason accurately represents a verified block, use `other` only when required to record that documented block.
6. **Communicate the result.** For an approval, state that it was approved and provide the new total credit limit. For a denial, state the applicable reason and a concrete next step. Include the date/time they may submit again for a cooldown denial, the threshold or remediation where appropriate, and never expose internal-only checks or invent a future eligibility date when one cannot be calculated.

## Missing, failed, or ambiguous data

A successful tool call is not itself proof that a requirement passed; interpret the returned statuses, dates, and monetary fields. If a required tool fails, a response is incomplete, a timestamp cannot be interpreted, or authoritative good-standing/utilization data is absent, do not guess or approve. Explain that the review cannot be completed from the available records and use the permitted support/escalation process if available. Do not repeat a mutation whose outcome is reported as unknown.

When several verified criteria fail, still run all required checks. For the single denial reason field, select the first verified failing criterion in the workflow order (account age, cooldown, disputes, replacement order, good standing, utilization, payment history) and explain any additional verified blockers in the customer response where appropriate.

## Discoverable tool procedure

Before the first call to each specialized tool, call `unlock_discoverable_agent_tool` using its exact name. Then call it through `call_discoverable_agent_tool`, passing a JSON string with exactly the documented arguments. Tool names used by this Skill are:

- `submit_credit_limit_increase_request_7392`
- `get_credit_limit_increase_history_4829`
- `get_user_dispute_history_7291`
- `get_pending_replacement_orders_5765`
- `get_payment_history_6183`
- `approve_credit_limit_increase_5847`
- `deny_credit_limit_increase_5848`

The replacement-order tool is named `get_pending_replacement_orders_5765`. It should be unlocked and called with `credit_card_account_id` even though its source guidance was written for a different account workflow.

## Helper script

`scripts/cli_policy.py` reads one JSON object from stdin and writes one JSON object to stdout. It performs deterministic tier thresholds, dollar-limit arithmetic, dates, and utilization calculations; it does not call banking tools and never performs an account action.

Input schema:

```json
{
  "tier": "premium-tier",
  "current_credit_limit": "5000.00",
  "requested_increase": "2500",
  "now": "YYYY-MM-DD HH:MM:SS EST",
  "account_open_date": "MM/DD/YYYY",
  "last_approved_submission_at": "YYYY-MM-DD",
  "current_balance": "0.00"
}
```

Only `tier`, `current_credit_limit`, and `requested_increase` are required. Omit unknown optional fields rather than supplying guesses. The output reports `null` for a check that cannot be calculated and lists input/parse errors. Example runnable invocation:

```bash
printf '%s' '{"tier":"premium-tier","current_credit_limit":"5000.00","requested_increase":"2500","now":"2025-01-01 10:00:00 EST","account_open_date":"2024-01-01","current_balance":"100.00"}' | python3 scripts/cli_policy.py
```

Before using a helper result in a decision, validate that `errors` is empty, `amount_within_limit` is `true`, and any calculated eligibility field required for that check is not `null`. The executor must separately validate status-based results and payment history from banking tools.
