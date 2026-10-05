---
name: credit-limit-increase-processing
description: Process a verified customer's credit-limit increase (CLI) request for an active credit-card account. Use when the requested increase, account details, and internal CLI eligibility checks must be recorded, evaluated, and either approved or denied through the banking tools.
---

# Credit-Limit Increase Processing

## Scope and governing rules

Use this Skill for a customer-requested CLI. It supports the three tiers below:

| Tier | Minimum age | Approved-request cooldown | Maximum utilization | Consecutive on-time months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | strictly below 70% | 6 | 25% of current limit |
| Mid-tier | 90 days | 90 days | strictly below 80% | 3 | 50% of current limit |
| Premium-tier | 60 days | 60 days | strictly below 90% | 3 | 50% of current limit |

Known card mappings include Bronze Rewards Card and EcoCard as Entry-tier; Silver Rewards Card and Green Rewards Card as Mid-tier; and Gold Rewards Card, Platinum Rewards Card, and Diamond Elite Card as Premium-tier. If the account response does not provide a tier and its card type cannot be mapped from authoritative information, stop and obtain the tier; do not guess eligibility criteria.

The requested **dollar increase** must be valid before a formal CLI request may be submitted. A request stated as a percentage must be converted from the current limit to an exact whole-dollar increase. If it does not result in a whole number of dollars, ask the customer for a dollar amount rather than choosing a rounding rule.

## Required order of operations

1. **Identify and verify the customer.**
   - Locate the user and the relevant account using the normal account lookup tools.
   - Confirm at least two of email, date of birth, phone number, and address against the customer record.
   - After two fields match, get the current time and call `log_verification` with *all* required record fields and the verification timestamp. Do this before processing the sensitive account request.
   - If identity cannot be verified, do not disclose account details or process the CLI.

2. **Confirm the account and requested amount.**
   - Confirm the account belongs to the verified user, is active/current, has a positive current credit limit, and determine its tier.
   - Determine the requested dollar increase. A customer saying “10%” means 10% of the current limit, not a 10 percentage-point change in utilization.
   - Use `scripts/cli_rules.py` with the tier, limit, and requested dollar amount or percentage to calculate and validate the increase. The amount must be an integer number of dollars and no greater than the tier maximum.
   - If the requested amount exceeds the maximum, tell the customer the maximum allowed and ask whether they want to request that valid dollar amount instead. **Do not submit a CLI request that exceeds the tier maximum.** If the amount is absent, ambiguous, non-positive, or non-integral, obtain a valid dollar amount before continuing.

3. **Create the formal request before internal eligibility checks.**
   - Unlock `submit_credit_limit_increase_request_7392`, then call it with:
     ```json
     {"credit_card_account_id":"<account id>","user_id":"<user id>","requested_increase_amount":<integer dollars>}
     ```
   - Retain its confirmation/reference. The formal submission must precede the internal eligibility checks below.

4. **Perform every eligibility check and retain the results.** Unlock each discoverable tool before its first call.
   - **Account age:** Calculate calendar-day age from the account open date to the current date. Eligibility begins on the minimum-age day.
   - **Cooldown:** Unlock and call `get_credit_limit_increase_history_4829` with the account ID. Find the most recent **approved** CLI submission. Denied requests do not create a cooldown. The cooldown has elapsed only after the required number of full days since that submission; the next eligible date is submission date plus the tier cooldown days. If the result is unclear, do not infer that an approved request did not occur.
   - **Disputes:** Unlock and call `get_user_dispute_history_7291` with the user ID. Any dispute with a non-final active status, such as `open` or `under_review`, fails this check. Closed disputes do not.
   - **Replacement orders:** Unlock and call `get_pending_replacement_orders_5765` with the account ID. An empty order collection passes. Any order not clearly `delivered` or `cancelled` fails; this includes pending or shipped orders.
   - **Good standing:** Verify the account is current/active and the past-due amount is zero. A past-due balance fails.
   - **Utilization:** Calculate `current_balance / current_credit_limit * 100`. It must be strictly below the tier threshold; equality fails.
   - **Payment history:** Unlock and call `get_payment_history_6183` with the account ID and the tier-required number of months. Verify all requested consecutive months are on time. Missing, late, or non-consecutive required history fails.
   - The helper can evaluate the deterministic age, utilization, and structured result fields after the tool responses have been normalized.

5. **Record one decision.**
   - If every check passes, unlock and call `approve_credit_limit_increase_5847`:
     ```json
     {"credit_card_account_id":"<account id>","user_id":"<user id>","new_credit_limit":<current limit + requested increase>}
     ```
   - If a submitted request fails an eligibility requirement, unlock and call `deny_credit_limit_increase_5848` with account ID, user ID, and the corresponding reason:

     | Failed check | `denial_reason` |
     |---|---|
     | Minimum account age | `insufficient_account_age` |
     | Approved-request cooldown | `cooldown_period_active` |
     | Active dispute | `pending_disputes` |
     | Pending/non-final replacement | `pending_replacement_card` |
     | Past due/not current | `past_due_balance` |
     | Utilization at or above threshold | `high_utilization` |
     | Required on-time history absent | `insufficient_payment_history` |

     Use `other` only for a confirmed, documented condition not represented by an allowed specific code. A request that exceeds the amount maximum must not have been submitted; obtain a valid revised amount instead.
   - Do not approve or deny from incomplete, ambiguous, or failed read-only checks. Retry a transient read failure where appropriate; if required data remains unavailable, explain that the request cannot yet be finalized and follow the environment's escalation procedure rather than fabricating an eligibility outcome.

6. **Communicate the outcome.**
   - For approval, confirm the approved increase and resulting total credit limit.
   - For denial, explain the specific failed condition. For cooldown or account age, provide the calculated date when the relevant condition is satisfied when it is determinable. For utilization, explain that it must be below (not equal to) the tier threshold. Do not expose internal dispute details or unnecessary account data.

## Helper usage

`scripts/cli_rules.py` is a pure local calculation helper; it performs no banking action and does not replace required tool calls.

It reads one JSON object from standard input and emits one JSON object to standard output.

### Input schema

```json
{
  "tier": "entry|mid|premium",
  "current_limit": "4000.00",
  "requested_increase_amount": 400,
  "requested_percent": null,
  "current_balance": "1500.00",
  "account_open_date": "YYYY-MM-DD",
  "as_of_date": "YYYY-MM-DD",
  "last_approved_request_date": null
}
```

Provide exactly one of `requested_increase_amount` or `requested_percent`. Monetary values may be JSON numbers or decimal strings. `last_approved_request_date` may be `null` when there is no approved prior request.

Example runnable call (values are illustrative only):

```sh
printf '%s' '{"tier":"entry","current_limit":"4000.00","requested_percent":"10","current_balance":"1500.00","account_open_date":"2024-01-01","as_of_date":"2024-05-01","last_approved_request_date":null}' | python3 scripts/cli_rules.py
```

### Output interpretation and validation

The output includes `requested_increase_amount`, `maximum_increase_amount`, `amount_valid`, `account_age_days`, `account_age_eligible`, `utilization_percent`, `utilization_eligible`, `cooldown_eligible`, and `next_cooldown_eligible_date` when applicable. Before relying on it, ensure `errors` is empty, `amount_valid` is true, and the calculated requested increase is an integer. A true `cooldown_eligible` only evaluates the supplied prior **approved** request date; it does not replace reviewing the CLI history tool response and identifying that date correctly.

The script rejects unknown tiers, invalid dates, negative balances, non-positive limits, missing/duplicate amount inputs, non-integral percentage-derived dollar amounts, and malformed numeric values. Treat a helper error as a data issue to resolve, not as a reason to approve or deny.
