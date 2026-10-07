---
name: credit-limit-increase-workflow
description: Safely process a credit-limit increase (CLI) request for a verified cardholder or authorized account manager. Use for requests requiring tier-based amount validation, formal submission, complete eligibility review, and an approve/deny action through the declared banking tools.
---

# Credit Limit Increase Workflow

## Scope and prerequisites

Use this Skill only for a customer seeking a CLI. Do not infer a CLI tier from a marketing or product card name. A card-specific document may state a credit-limit range, but that does not establish whether the card is Entry-, Mid-, or Premium-tier.

Before any account-changing or decision action:

1. Identify the customer and the target card account using the normal account lookup tools.
2. Confirm that the requester is the account owner or an authorized account manager.
3. Verify identity by having the customer confirm **two of the four** identity fields (date of birth, email, phone number, address) against the account record. Do not disclose stored values in order to obtain confirmation. After two fields match, get the current timestamp and call `log_verification` with every required stored field and that timestamp.
4. Obtain a specific integer dollar increase amount and the customer’s confirmation to proceed. A percentage can be converted to dollars only after current limit is known; get confirmation of the resulting exact amount.
5. Establish the card tier from an authoritative source. If the tier is unavailable or ambiguous, explain that the per-request limit cannot be validated and ask the customer to provide the explicit tier or use a supported authoritative channel. **Do not submit a CLI request, approve, or deny merely because tier data is unavailable.**

Use `scripts/cli_policy.py` to calculate the tier rules and validate a requested amount. It is a calculator and does not call banking tools.

## Tier policy

| Tier | Minimum account age | Cooldown after approved request | Utilization requirement | On-time payment history | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | below 70% | 6 consecutive months | 25% of current limit |
| Mid-tier | 90 days | 90 days | below 80% | 3 consecutive months | 50% of current limit |
| Premium-tier | 60 days | 60 days | below 90% | 3 consecutive months | 50% of current limit |

An amount equal to the percentage cap is allowed. Utilization equal to its threshold is not allowed. If a published card-specific ceiling applies, also ensure the requested new total does not exceed it; that ceiling does not substitute for identifying the tier.

If the amount exceeds the applicable cap, tell the customer the maximum dollar increase and ask whether they wish to proceed with a specific valid amount. Do not submit the invalid request. If they decline or do not provide a valid amount, leave the request unsubmitted.

## Required tool order

Once identity, authorization, tier, exact amount, and amount validation are complete, perform the following in this order. Banking actions must be made through the declared normal banking tools, not through this script.

### 1. Submit first

Unlock and call `submit_credit_limit_increase_request_7392` with:

```json
{
  "credit_card_account_id": "<account id>",
  "user_id": "<user id>",
  "requested_increase_amount": 123
}
```

This formal submission must occur before the eligibility review. Record the response/reference where returned. Do not call the approval or denial tool before a successful submission. If submission fails or its status is unclear, do not retry blindly and do not make a decision; explain that processing could not be completed and follow supported error handling.

### 2. Complete every eligibility check

After a successful submission, unlock and call all applicable specialized tools. Do not stop checks after finding one failure: the workflow requires a complete audit review.

* Compare the account open date with the tier minimum using the current date. A customer qualifies on the day the minimum age is reached.
* Call `get_credit_limit_increase_history_4829` with the account ID. Review requests predating the submission just created. A cooldown blocks the CLI only when the most recent prior request was **approved** and fewer than the tier’s full cooldown days have elapsed. Denied requests do not trigger cooldown.
* Call `get_user_dispute_history_7291` with the user ID. Any active dispute (for example `open` or `under_review`) fails the disputes check; closed disputes do not.
* Call `get_pending_replacement_orders_5765` with the account ID. An empty list passes. A returned order blocks processing if any order is not clearly `delivered` or `cancelled` (such as pending or shipped).
* Read account standing from the account record. It must be current/active as applicable and have no past-due balance. A nonzero past-due amount fails this criterion.
* Calculate utilization as `current_balance / current_credit_limit * 100`. It must be strictly lower than the tier threshold. Treat a missing, zero, or unusable credit limit/balance as an unresolved review rather than inventing a value.
* Call `get_payment_history_6183` with the account ID and the exact tier-required month count. Verify that all required consecutive months are on time. Missing, late, or insufficient history fails this criterion.

If tool data is malformed, incomplete, or ambiguous, do not approve. Preserve the submitted request and communicate that the review cannot be completed through the available data; use a supported escalation path only when one exists. Do not manufacture an eligibility result.

### 3. Decide and record it

If all checks pass, compute `new_credit_limit = current_credit_limit + requested_increase_amount`, confirm it respects any documented product ceiling, then unlock and call `approve_credit_limit_increase_5847`:

```json
{
  "credit_card_account_id": "<account id>",
  "user_id": "<user id>",
  "new_credit_limit": 0.0
}
```

If any criterion fails, unlock and call `deny_credit_limit_increase_5848` using the appropriate allowed reason:

| Failed criterion | `denial_reason` |
|---|---|
| Minimum age | `insufficient_account_age` |
| Approved-request cooldown | `cooldown_period_active` |
| Active dispute | `pending_disputes` |
| Outstanding replacement | `pending_replacement_card` |
| Past-due / not-current standing | `past_due_balance` |
| Utilization at or over threshold | `high_utilization` |
| Required on-time history absent | `insufficient_payment_history` |
| Amount or applicable total limit is over an allowed cap | `requested_amount_exceeds_limit` |
| Another documented, supported failure | `other` |

Use the same account ID and user ID. Do not use `other` when a listed reason applies. Only one denial tool call is needed; select the most direct applicable reason while retaining all check results in the case context.

### 4. Customer communication

For approval, confirm the approved increase and the new total limit. For denial, give the relevant reason without exposing internal-only data. State a concrete reapplication date only when it can be calculated reliably (for example, the end of an approved-request cooldown); otherwise state the condition the customer must satisfy. For a pre-submission amount overage, explain the maximum and request a revised specific amount rather than characterizing it as a submitted denial.

## Calculator interface

Run `scripts/cli_policy.py` with JSON on standard input. It emits one JSON object on standard output.

Input schema:

```json
{
  "tier": "entry|mid|premium",
  "current_credit_limit": 4000,
  "requested_increase_amount": 1000,
  "current_balance": 1000,
  "account_age_days": 150,
  "days_since_last_approved_request": 200,
  "consecutive_on_time_months": 6,
  "product_max_credit_limit": 32500
}
```

Only `tier`, `current_credit_limit`, and `requested_increase_amount` are required. Optional review fields cause corresponding checks to be reported when supplied. `days_since_last_approved_request: null` means there is no prior approved request. Omit `product_max_credit_limit` unless an authoritative product-specific ceiling applies.

Example runnable invocation:

```sh
printf '%s' '{"tier":"entry","current_credit_limit":4000,"requested_increase_amount":1000}' | python3 scripts/cli_policy.py
```

Validate that `amount_valid` is true before submitting. After live tools return data, compare each `checks` result with the actual account and tool records; the calculator cannot establish identity, tier, authority, dispute status, replacement status, submission success, or payment-record semantics.
