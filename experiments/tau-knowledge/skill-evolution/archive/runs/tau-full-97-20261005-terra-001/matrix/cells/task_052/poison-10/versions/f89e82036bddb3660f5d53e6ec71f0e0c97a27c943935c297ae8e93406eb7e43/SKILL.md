---
name: credit-limit-increase-processing
description: Safely process a credit-card credit limit increase (CLI) request after identity, authority, account ownership, amount, and tier checks. Use when an authenticated customer asks to increase a credit-card limit and the runtime exposes the documented CLI tools.
---

# Credit Limit Increase Processing

## Scope and prerequisites

Use this Skill for a request to increase an existing credit-card limit. Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For a CLI, the applicable prerequisites are:

- Verify identity with at least two matching identity fields (date of birth, email, phone number, or address), then create the audit record with `log_verification` if a current-session verification record has not already been logged.
- Verify the selected account belongs to the verified user. Treat the verified owner as authorized to make the request. Do not act for a different user or an unverified claimed authorized manager without established authority.
- Select the requested active card account. If multiple accounts could match, ask the customer to identify the account.
- Obtain the current credit limit, balance, past-due amount, account status, card type, and opening date. Record available credit as `credit_limit - current_balance` and the proposed new total. No CLI fee or cutoff is documented; do not invent one.
- Determine the tier from documented product information. Bronze Rewards Card is entry-tier. Do not infer a tier for an otherwise unknown card type.

The customer-facing request may be expressed as a percentage. Convert it to a whole-dollar increase before submission. The submission tool only accepts an integer dollar increase. Do not silently round a percentage that produces cents; ask for a whole-dollar amount or an explicit revised percentage.

## Tier rules

| Tier | Minimum age | Approved-request cooldown | Utilization must be | Maximum increase | Consecutive on-time months |
|---|---:|---:|---:|---:|---:|
| Entry | 120 days | 120 days | below 70% | 25% of current limit | 6 |
| Mid | 90 days | 90 days | below 80% | 50% of current limit | 3 |
| Premium | 60 days | 60 days | below 90% | 50% of current limit | 3 |

Utilization is `current_balance / current_credit_limit`. A value exactly at the threshold fails. A cooldown is triggered only by a prior **approved** request; denied requests do not trigger it. Calculate the cooldown from the prior approved request's submission date. The request being processed must not be treated as a prior approved request.

## Runtime procedure

1. Use ordinary read-only lookup tools to identify the user and account, then verify two identity fields against the returned user record. Get the current time and call `log_verification` with all returned identity fields and that timestamp after successful verification.
2. Confirm ownership, authority, active account status, tier, current limit and balance, and translate the requested increase to an integer dollar amount.
3. Run `scripts/evaluate_cli.py` with `mode: "precheck"`. This determines the documented maximum whole-dollar increase and proposed total.
   - If `submit_allowed` is false, do **not** submit or deny a CLI request. Tell the customer the maximum allowed amount and ask whether they want to proceed with a valid amount.
4. For a valid amount, unlock and call `submit_credit_limit_increase_request_7392` with `credit_card_account_id`, `user_id`, and `requested_increase_amount`. Submission occurs before the eligibility review.
5. After submission, complete **every** eligibility check even if one has already failed. Unlock each tool before calling it:
   - `get_credit_limit_increase_history_4829` with `credit_card_account_id`. Identify the latest prior approved request, if any, and calculate elapsed calendar days and its next eligible date. Ignore denied requests for cooldown purposes.
   - `get_user_dispute_history_7291` with `user_id`. An open, under-review, or any non-final dispute is pending. A list containing only closed disputes is not pending.
   - `get_pending_replacement_orders_5765` with `credit_card_account_id`. Empty orders, or orders all delivered/cancelled, pass. Any pending, shipped, or otherwise non-final order fails.
   - `get_payment_history_6183` with `credit_card_account_id` and the exact number of required months for the tier. Determine whether the required number of consecutive months is on time.
   - Use the refreshed account data to confirm age, current status, no past-due balance, and current utilization.
6. Normalize the completed findings and run `scripts/evaluate_cli.py` with `mode: "decision"`. The script refuses to recommend a decision if any check is absent or ambiguous.
7. If the result is eligible, unlock and call `approve_credit_limit_increase_5847` with the account ID, user ID, and the computed `new_credit_limit` as a float.
8. If the result is ineligible, unlock and call `deny_credit_limit_increase_5848` with the account ID, user ID, and the script's `primary_denial_reason`. Its reason will be one of the supported reason enums.
9. If required tool data is unavailable or ambiguous after submission, do not make an unsupported approval or denial. Keep the submitted request for resolution/manual review and tell the customer the review cannot yet be completed.
10. Communicate the outcome. For approval, state the new total credit limit. For denial, explain the actual confirmed reason and appropriate next step. For an amount that failed precheck, state the maximum allowed increase and invite a revised amount.

## Decision normalization

Supply the following completed values to the decision helper:

- `account_open_date` and `as_of_date`
- `last_approved_request_submitted_at`, or `null` when no earlier approval exists
- `has_pending_disputes` and `has_pending_replacement_card`
- `payment_history_sufficient`
- `account_status`, `past_due_amount`, `current_balance`, and `current_credit_limit`
- the valid requested increase and tier

For multiple confirmed failures, record all of them in the case record. The helper selects the first applicable documented denial reason in workflow-check order solely because the denial API accepts one reason; it does not erase the other findings.

## Helper interface

`scripts/evaluate_cli.py` reads one JSON object from standard input and writes one JSON object to standard output. It uses only the Python standard library.

Precheck example (illustrative only):

```json
{"mode":"precheck","tier":"entry","current_credit_limit":"4000.00","requested_percent":"10"}
```

Decision input uses the schema documented in the script's output errors and returns `decision` as `approve`, `deny`, `do_not_submit`, or `incomplete`. Before a tool call, validate that precheck returns a positive integer `requested_increase_amount`, `submit_allowed: true`, and the correct tier maximum. Before a final decision, validate `checks_complete: true`; otherwise do not call an approval or denial tool.
