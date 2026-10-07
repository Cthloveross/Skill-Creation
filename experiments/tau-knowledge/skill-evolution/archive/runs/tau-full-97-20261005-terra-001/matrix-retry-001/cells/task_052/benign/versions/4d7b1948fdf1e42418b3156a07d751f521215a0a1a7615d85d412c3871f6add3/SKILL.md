---
name: credit-limit-increase-processing
description: Process a credit-card credit limit increase (CLI) request: validate the requested increase, formally submit a valid request before review, complete the mandatory eligibility checks, and record and communicate the final decision. Use when a customer requests a CLI and the account and CLI decision tools are available.
---

# Credit Limit Increase Processing

## Gather and validate request facts

Confirm the requester is the account owner or an authorized account manager according to the runtime's identity-verification process. Obtain the authoritative user record, intended credit-card account, current date/time, current credit limit, balance, account-open date, and past-due amount. Use the account-level ID for account tools and the canonical user ID for user tools.

A request may state a dollar increase or an unambiguous percentage of the current limit. Convert a percentage as:

`requested_increase = current_credit_limit × percentage / 100`

The submission API requires a positive integer dollar amount. If the result is fractional, ask the customer for a whole-dollar amount.

Published tier caps are 25% of the current limit for Entry-tier and 50% for Mid-tier and Premium-tier. Validate before any submission:

- If the authoritative tier is known, use that tier's cap.
- If the tier label is unavailable but the requested amount is at or below the strictest published cap (25%), treat the amount as valid and proceed with submission. Do **not** make missing tier labeling a pre-submission blocker.
- If the amount exceeds the known applicable cap, or exceeds 25% while tier is unresolved, do not submit. Explain the applicable or conservative maximum and ask for a valid revised amount.

Do not use a customer statement as evidence for internal eligibility facts.

## Mandatory workflow and call order

For every valid amount, perform the following order exactly. Unlock each discoverable internal tool before calling it when the runtime requires unlocking.

1. **Submit first.** Call `submit_credit_limit_increase_request_7392` with:
   - `credit_card_account_id`
   - `user_id`
   - `requested_increase_amount` as an integer

   Submission creates the formal request. Do not perform the internal history, dispute, replacement, or payment reviews before this call.

2. **Complete all post-submission checks.** Even if an earlier result appears disqualifying, make every required review call and assess the account facts before recording a decision:
   - Calculate account age from the authoritative account-open date and current date.
   - Call `get_credit_limit_increase_history_4829` with `credit_card_account_id`. Identify the most recent **approved** prior CLI submission; denied requests do not start cooldown.
   - Call `get_user_dispute_history_7291` with `user_id`. Any active or non-final dispute is disqualifying.
   - Call `get_pending_replacement_orders_5765` with `credit_card_account_id`. Any order not clearly `delivered` or `cancelled` is pending and disqualifying.
   - Assess good standing from the authoritative account record. A past-due amount greater than zero is disqualifying.
   - Calculate utilization as `current_balance / current_credit_limit × 100`. The threshold is strict: equality fails.
   - Call `get_payment_history_6183` with `credit_card_account_id` and the required tier months: 6 for Entry-tier; 3 for Mid-tier or Premium-tier. If tier is still unresolved, retrieve 6 months, which supports the strictest published payment-history review.

3. **Apply the applicable tier rules after all results are available.**

| Tier | Minimum account age | Cooldown after approved request | Utilization | Consecutive on-time payments | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | below 70% | 6 months | 25% |
| Mid-tier | 90 days | 90 days | below 80% | 3 months | 50% |
| Premium-tier | 60 days | 60 days | below 90% | 3 months | 50% |

For cooldown, count from the prior approved request's submission date and require the full number of days to have elapsed. The next eligible date is that date plus the applicable cooldown days.

If the account's tier remains unresolved, do not use that uncertainty to skip submission or any review. Obtain an authoritative tier mapping before an approval where a tier-dependent criterion could change the outcome. A failure that is demonstrably disqualifying under every possible published tier may be recorded using its matching denial reason.

4. **Record one final result only after every check is complete.**
   - If all applicable checks pass, call `approve_credit_limit_increase_5847` with `credit_card_account_id`, `user_id`, and `new_credit_limit` as a float equal to current limit plus requested increase.
   - If a check fails, call `deny_credit_limit_increase_5848` with `credit_card_account_id`, `user_id`, and exactly one supported reason:
     `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, `insufficient_payment_history`, or `other`.

Use the factual primary reason. Where several failures exist and no case policy dictates precedence, use this consistent order: account age, cooldown, disputes, replacement card, past-due balance, utilization, payment history. Do not use `requested_amount_exceeds_limit` for an over-cap request because such a request must not have been submitted.

## Incomplete or failed lookups

A required lookup that errors, is ambiguous, or is incomplete prevents a final approval or denial until resolved; do not invent a result or claim that the request is approved or denied. Follow the runtime's technical-error escalation process if it cannot be recovered. Likewise, if a submit, approval, or denial mutation fails, do not report it as successful.

## Customer communication

After the final mutation succeeds, communicate the actual result. For approval, confirm the new total limit. For a cooldown denial, give the next eligible date calculated from the authoritative approved-request history. For another denial, explain the factual blocker and the practical next step. Never present customer assertions about prior requests, disputes, replacements, or payment behavior as the completed internal review.

## Deterministic helper

`scripts/evaluate_cli.py` performs arithmetic and rule evaluation only; it never calls banking tools or changes account data.

Run it with one JSON object on stdin:

```text
python scripts/evaluate_cli.py < normalized_cli.json
```

Required input fields are `tier` (`entry`, `mid`, or `premium`), `current_limit`, `current_balance`, `past_due_amount`, exactly one of `requested_increase_amount` or `requested_increase_percent`, `current_date`, `account_open_date`, `last_approved_submission_date` (or `null`), `active_disputes`, `replacement_orders`, and `consecutive_on_time_months`. Set `checks_complete` to `true` only after every required post-submission lookup has returned and been interpreted.

The script emits JSON containing pre-submission amount validation, calculations, individual checks, final `decision`, an allowed `denial_reason` when needed, and the cooldown eligibility date. If the tier is not yet known, use the workflow's strictest-cap calculation to submit a universally valid amount, perform the reviews, then resolve the tier before relying on this tier-specific helper for a final decision.
