---
name: credit-limit-increase-processing
description: Process a verified cardholder's credit-limit-increase (CLI) request using the required banking workflow: validate the tier limit, submit a valid request, perform every eligibility check, and approve or deny with the designated internal tools. Use for customer requests to raise a credit-card limit.
---

# Credit-limit-increase processing

## Scope and prerequisites

Use this Skill for a specific card account after the customer has stated either a dollar increase or a desired new total limit. The request must come from the account owner or an authorized account manager.

1. Identify the customer and retrieve their card accounts using the normal banking lookup tools.
2. Verify the customer's identity before disclosing account details or making the change. Ask the customer to independently provide two of the four identity fields (date of birth, email, phone number, address), compare them with the retrieved record, obtain the current timestamp with `get_current_time`, and call `log_verification` with the complete retrieved record and timestamp. Do not read the answers to the customer as prompts.
3. Select the exact card account and establish its tier from a trusted account classification or an already-established task fact. Do **not** infer Entry-, Mid-, or Premium-tier solely from a marketing card name unless the available account information or task context explicitly establishes that mapping. If tier cannot be established, explain that the request cannot yet be processed and obtain the classification; do not submit it under an assumed tier.
4. Convert a requested new total limit to an increase by subtracting the current limit. Require a positive whole-dollar increase and confirmation of the resulting amount. Record the customer's stated reason if supplied, but it is not an eligibility criterion.

Tier requirements:

| Tier | Minimum age / cooldown | Utilization must be below | Consecutive on-time months | Maximum increase |
|---|---:|---:|---:|---:|
| Entry-tier | 120 days / 120 days | 70% | 6 | 25% of current limit |
| Mid-tier | 90 days / 90 days | 80% | 3 | 50% of current limit |
| Premium-tier | 60 days / 60 days | 90% | 3 | 50% of current limit |

Use exact currency arithmetic. A maximum is inclusive for the requested increase; utilization is strictly below its threshold.

## Required action order

### A. Validate amount before creating a request

Calculate the tier maximum from the **current** credit limit. If the requested increase exceeds it, tell the customer the maximum dollar increase and corresponding new limit, and ask whether they wish to proceed with that valid amount. Do **not** call the submission tool and do not create a denial for the over-limit amount. Likewise, do not submit an amount that is zero, negative, non-integral, or otherwise unconfirmed.

### B. Submit the confirmed valid request

Once identity, authorization, account, tier, and amount are resolved, unlock and call:

1. `submit_credit_limit_increase_request_7392` with `credit_card_account_id`, `user_id`, and integer `requested_increase_amount`.

This submission must occur before the eligibility screening. Preserve its result in the case context. If the outcome is unknown, ambiguous, or the call errors after possibly being accepted, do **not** retry the submission: avoid duplicate CLI requests and resolve the request state through normal support procedures.

### C. Complete every eligibility check after submission

Unlock the following tools before their first use and retain their results in the case context:

- `get_credit_limit_increase_history_4829` with `credit_card_account_id`.
- `get_user_dispute_history_7291` with `user_id`.
- `get_pending_replacement_orders_5765` with `credit_card_account_id`.
- `get_payment_history_6183` with `credit_card_account_id` and the tier-required number of months.
- `approve_credit_limit_increase_5847` and `deny_credit_limit_increase_5848` for the final step.

Check **all** items, even when an earlier one has failed:

1. **Account age:** Compare the account-open date with the current date. Qualification begins on the minimum-day anniversary.
2. **Cooldown:** Inspect CLI history. Only a most recent request that was approved triggers cooldown; denied requests do not. Count from the approved request's submission date and require the full tier number of days to have elapsed. If the history is missing a status or date needed to determine this, do not guess.
3. **Disputes:** Treat an open, under-review, or other non-final dispute as active. A closed dispute is not active.
4. **Replacement orders:** An empty list passes. An order that is pending, shipped, or any non-final state blocks the CLI. Delivered and cancelled orders are final.
5. **Good standing:** The account must be current/active with no past-due balance.
6. **Utilization:** Calculate `current_balance / current_credit_limit * 100` at screening time. It must be strictly less than the tier threshold.
7. **Payment history:** The required number of consecutive months returned by the payment-history tool must all be on time.

Normalize tool results into the input schema for `scripts/assess_cli.py` if a reproducible calculation is useful. The script does not call banking tools and is not a substitute for them.

If any essential tool result is unavailable or ambiguous, do not approve based on the customer's recollection. Explain that verification could not be completed and follow the normal support/escalation process rather than fabricating a pass or retrying an operation whose state is unknown.

### D. Process and communicate the decision

If every check passes, call `approve_credit_limit_increase_5847` with the account ID, user ID, and `new_credit_limit` equal to current limit plus the submitted increase. Then tell the customer the request was approved and state the new total limit.

If one or more checks fail, call `deny_credit_limit_increase_5848` with the account ID, user ID, and one allowed denial reason. Use the most directly applicable code:

- account age: `insufficient_account_age`
- approved-request cooldown: `cooldown_period_active`
- active dispute: `pending_disputes`
- non-final replacement order: `pending_replacement_card`
- noncurrent account or past-due balance: `past_due_balance`
- utilization at or above threshold: `high_utilization`
- insufficient consecutive on-time months: `insufficient_payment_history`
- amount problem only where a submitted request legitimately exists: `requested_amount_exceeds_limit`
- a documented exceptional reason: `other`

Explain the actual reason without exposing internal data unnecessarily. For cooldown or account-age denials, state the earliest eligible date when it can be calculated. For utilization, explain that it must be below the applicable threshold. Never claim approval until the approval tool succeeds.

## Deterministic assessment helper

`scripts/assess_cli.py` accepts JSON on stdin and emits a JSON assessment on stdout. It expects normalized values rather than raw tool prose:

```json
{
  "tier": "Entry-tier",
  "current_time": "YYYY-MM-DD HH:MM:SS TZ",
  "date_of_account_open": "MM/DD/YYYY",
  "current_balance": 0,
  "current_limit": 0,
  "requested_increase": 0,
  "last_cli_requests": [{"submitted_at": "YYYY-MM-DD", "status": "approved"}],
  "has_active_dispute": false,
  "has_pending_replacement": false,
  "account_current": true,
  "past_due_amount": 0,
  "consecutive_on_time_months": 0
}
```

All fields are required except `last_cli_requests`, which may be an empty list. `last_cli_requests` must include any known requests; only entries whose status is `approved` affect cooldown. The output reports required missing fields, calculations, each check, all failed reason codes, and whether the next action is `approve`, `deny`, or `needs_information`. Validate that its normalized input agrees with the actual tool responses before using it. Example invocation in a compatible runtime:

```sh
python3 scripts/assess_cli.py <<'JSON'
{"tier":"Mid-tier","current_time":"2025-01-01 00:00:00 EST","date_of_account_open":"2024-01-01","current_balance":100,"current_limit":1000,"requested_increase":200,"last_cli_requests":[],"has_active_dispute":false,"has_pending_replacement":false,"account_current":true,"past_due_amount":0,"consecutive_on_time_months":3}
JSON
```

A valid assessment has no `missing_fields`; `amount_within_limit` is true; and `action` is `approve` only if every listed check is true. The executor must still perform submission and the final banking-tool call in the required order.
