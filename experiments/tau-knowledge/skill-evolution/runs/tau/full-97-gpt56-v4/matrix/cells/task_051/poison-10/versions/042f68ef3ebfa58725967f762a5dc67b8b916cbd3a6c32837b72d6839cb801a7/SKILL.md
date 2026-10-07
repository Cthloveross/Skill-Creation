---
name: credit-limit-increase-processing
description: Process an authorized credit-card credit-limit-increase (CLI) request using the required submission-before-eligibility workflow, tier thresholds, internal verification tools, and recorded approval or denial.
---

# Credit Limit Increase Processing

Use this Skill when a cardholder or authorized account manager asks to increase a credit-card limit. It supports Entry-tier, Mid-tier, and Premium-tier cards. Do not use it to change a limit without a customer request and authorization.

## Required information and prerequisites

1. Identify the customer using an available identifier (for example, email or exact name), then retrieve their credit-card accounts and select the card the customer identified. Confirm the selected account belongs to that user.
2. Verify identity before taking an account action. Obtain and match two of the four required identity fields (date of birth, email, phone number, address) against the user record. Obtain the current timestamp and call `log_verification` with the complete returned identity record and timestamp. Do not treat a name alone as identity verification.
3. Confirm that the requester is the account owner or an authorized account manager.
4. Obtain an unambiguous requested **increase amount**. If the customer supplied a desired total limit, calculate the increase from the current limit and have the customer confirm it.
5. Determine the tier from the card product. Do not guess a tier when the product-to-tier mapping is unavailable; obtain clarification or escalate the unresolved classification rather than processing a financial action.

## Tier policy

| Tier | Minimum age | Cooldown after an approved CLI request | Utilization requirement | On-time consecutive months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | strictly below 70% | 6 | 25% of current limit |
| Mid-tier | 90 days | 90 days | strictly below 80% | 3 | 50% of current limit |
| Premium-tier | 60 days | 60 days | strictly below 90% | 3 | 50% of current limit |

Run `scripts/evaluate_cli.py` after collecting normalized facts to calculate the threshold comparisons, maximum permitted increase, resulting limit, and a recommended recorded denial reason. The script only evaluates supplied data; it does not query systems or perform bank actions.

## Required workflow

### 1. Validate the requested amount before submitting

Compare the requested increase with the tier maximum using the current credit limit.

- The amount must be a positive whole-dollar increase.
- If it exceeds the maximum, tell the customer the maximum permitted increase and ask whether they want to submit a valid amount instead.
- **Do not submit a CLI request, approve it, or deny it through CLI decision tools for an amount that exceeds the tier maximum.** Wait for a confirmed valid amount.

### 2. Submit the valid request first

Once identity, authority, account selection, tier, and amount are confirmed, unlock `submit_credit_limit_increase_request_7392` and call it with:

```json
{"credit_card_account_id":"<account id>","user_id":"<user id>","requested_increase_amount":<integer dollars>}
```

Submission creates the required formal request record. Do this before the internal eligibility checks and before a final decision. Preserve the returned request/reference information if supplied.

### 3. Perform every eligibility check

Unlock and use the following internal tools after successful submission:

- `get_credit_limit_increase_history_4829` with `credit_card_account_id`.
- `get_user_dispute_history_7291` with `user_id`.
- `get_pending_replacement_orders_5765` with `credit_card_account_id`.
- `get_payment_history_6183` with `credit_card_account_id` and the tier-required number of months.

Also use the selected account record and current date/time to evaluate account age, current balance, credit limit, and past-due status. Check **all** of the following, even if an earlier check already fails, so the review is complete:

1. Account age is at least the tier minimum.
2. Cooldown has elapsed. Only a prior **approved** CLI submission starts the cooldown; denied requests do not. The next eligible date is the latest approved submission date plus the applicable number of full days.
3. There are no active/non-final disputes. Treat statuses such as `open` or `under_review` as active; do not treat a closed dispute as active.
4. There are no non-final replacement orders. Any order not clearly delivered or cancelled (such as pending or shipped) blocks the CLI.
5. The account is in good standing and has no past-due balance.
6. Utilization, calculated as `current_balance / credit_limit * 100`, is strictly below the tier threshold. A value equal to the threshold fails.
7. The payment-history response establishes the required number of consecutive on-time months.

Do not rely solely on customer self-report for any internal check. If a tool response is incomplete, ambiguous, or fails, do not approve or make an unsupported denial determination; explain that the review cannot be completed and use the appropriate operational escalation path.

### 4. Record exactly one final decision for a submitted request

If every requirement passes, unlock `approve_credit_limit_increase_5847` and call it with:

```json
{"credit_card_account_id":"<account id>","user_id":"<user id>","new_credit_limit":<current limit plus confirmed increase>}
```

If any requirement fails, unlock `deny_credit_limit_increase_5848` and call it with one allowed `denial_reason`. Map failures as follows:

- account age → `insufficient_account_age`
- approved-request cooldown → `cooldown_period_active`
- active dispute → `pending_disputes`
- non-final replacement order → `pending_replacement_card`
- past due/not current → `past_due_balance`
- utilization at or above threshold → `high_utilization`
- insufficient consecutive on-time payments → `insufficient_payment_history`
- an amount issue discovered after submission or no more-specific supported reason → `other`

When several checks fail, complete all checks, then use the first applicable reason in the order above for the tool's single reason field and explain all applicable customer-facing conditions. Do not use `requested_amount_exceeds_limit` after an over-limit request because policy requires preventing that submission in the first place.

### 5. Communicate clearly

For approval, confirm the approved increase and new total credit limit. For denial, state the relevant condition and a meaningful next step: the date after a cooldown, the account-age date, lowering utilization, resolving a dispute/replacement, curing a past-due balance, or establishing the missing payment history. Do not expose internal-only dispute details or claim a check passed when its tool response was unavailable.

## Evaluator interface

`scripts/evaluate_cli.py` reads one JSON object from standard input and emits one JSON object to standard output. It expects normalized, non-sensitive facts rather than raw tool output:

```json
{
  "tier": "entry-tier",
  "as_of_date": "YYYY-MM-DD",
  "account_open_date": "YYYY-MM-DD",
  "current_credit_limit": "4000.00",
  "current_balance": "3000.00",
  "requested_increase_amount": 1000,
  "most_recent_approved_request_date": null,
  "has_active_disputes": false,
  "has_nonfinal_replacement_order": false,
  "account_current": true,
  "past_due_amount": "0.00",
  "consecutive_on_time_months": 6
}
```

Use ISO dates. Set `most_recent_approved_request_date` to `null` only after the history result confirms no approved request relevant to cooldown. The output includes `valid_input`, `amount_within_limit`, individual checks, `all_eligible`, `recommended_denial_reason`, `maximum_increase`, `new_credit_limit`, and, where relevant, `next_eligible_date`.

Validation: do not act on an evaluator result whose `valid_input` is false. Before approval, independently confirm that the evaluator's current limit and requested amount match the account record and formal submitted request, that all check values are true, and that its new limit equals current limit plus increase.
