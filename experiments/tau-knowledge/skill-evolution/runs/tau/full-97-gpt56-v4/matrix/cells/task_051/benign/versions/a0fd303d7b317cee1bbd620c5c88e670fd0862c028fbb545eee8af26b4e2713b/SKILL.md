---
name: credit-limit-increase-processing
description: Process a credit-card credit limit increase (CLI) request after the customer identifies an account and confirms a requested dollar increase. Use for tier-based CLI amount validation, mandatory request submission, complete eligibility review, approval or denial, and customer communication.
---

# Credit Limit Increase Processing

Use this Skill to process a CLI request with the required order of operations. The executor, not the Python helper, performs all bank actions through the declared banking tools.

## Inputs needed

Obtain or look up at runtime:

- The authenticated/requesting customer's `user_id`.
- The specific `credit_card_account_id`, card tier, current credit limit, current balance, account opening date, account status, and past-due amount.
- A confirmed requested **increase** in whole dollars. If the customer gives a desired total limit, convert it to `desired_total - current_limit` and ask for confirmation if necessary.
- Current time from `get_current_time`.

Do not use account lookup data as proof that the caller has authenticated. Follow any independently applicable identity-verification procedure before disclosing or changing account information. This CLI workflow itself does not replace such a procedure.

## Tier rules

| Tier | Minimum account age | Cooldown after an approved request | Utilization requirement | Consecutive on-time months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | strictly below 70% | 6 | 25% of current limit |
| Mid-tier | 90 days | 90 days | strictly below 80% | 3 | 50% of current limit |
| Premium-tier | 60 days | 60 days | strictly below 90% | 3 | 50% of current limit |

Determine tier from authoritative account/card information. Bronze Rewards Card is Entry-tier. Do not infer a tier for an unrecognized card type; obtain a reliable tier classification before proceeding.

Utilization is `current_balance / current_credit_limit * 100`. A utilization equal to the threshold fails because the requirement is “below.” A nonpositive or unavailable credit limit is invalid data and must be resolved rather than used to calculate a decision.

## Mandatory workflow

### 1. Validate the amount before any submission

1. Calculate the maximum permitted increase from the current limit and tier.
2. Ensure the requested increase is a positive whole-dollar amount and is no greater than that maximum.
3. If it exceeds the maximum, tell the customer the maximum increase and corresponding new total, and ask whether they want to proceed with a compliant amount. **Do not submit a request** until the customer confirms a valid amount.
4. If the amount is unclear, not a whole-dollar increase, or the tier/current limit is unavailable, obtain the missing information first.

Use `scripts/evaluate_cli.py` with the known facts to calculate the amount check and eventual decision. The helper emits recommendations only and never calls a bank tool.

### 2. Submit the valid request first

After the customer confirms a valid amount, unlock and call the required internal tool:

1. `unlock_discoverable_agent_tool` with `submit_credit_limit_increase_request_7392`.
2. `call_discoverable_agent_tool` using that exact name and JSON arguments:
   ```json
   {"credit_card_account_id":"<account_id>","user_id":"<user_id>","requested_increase_amount":<integer>}
   ```

Record the submission outcome. Do not perform eligibility checks before this submission; the request must exist before review. If submission fails or is ambiguous, do not approve or deny based on an assumed submission—resolve the failure through the applicable operational path.

### 3. Perform every eligibility check after submission

Even when one check fails, perform and record all of the following checks before making the decision:

1. **Account age, standing, past due, and utilization:** retrieve current account data (for example, with `get_credit_card_accounts_by_user`) and ensure the selected account is current/active, has no past-due balance, is old enough, and has utilization strictly below the tier threshold.
2. **Cooldown:** unlock `get_credit_limit_increase_history_4829`, then call it with:
   ```json
   {"credit_card_account_id":"<account_id>"}
   ```
   Consider only the most recent **approved** CLI request. Denied requests do not start a cooldown. Compare its submission date with current time; the customer is eligible on or after the last approved request date plus the tier cooldown days.
3. **Disputes:** unlock `get_user_dispute_history_7291`, then call it with:
   ```json
   {"user_id":"<user_id>"}
   ```
   Treat open, under-review, or otherwise nonfinal disputes as active/pending. A clearly closed dispute is not pending.
4. **Replacement cards:** unlock `get_pending_replacement_orders_5765`, then call it with:
   ```json
   {"credit_card_account_id":"<account_id>"}
   ```
   A pending, shipped, or other nonfinal order blocks the CLI. Proceed only if there are no orders or every returned order is delivered or cancelled.
5. **Payment history:** unlock `get_payment_history_6183`, then call it with the tier-required number of months:
   ```json
   {"credit_card_account_id":"<account_id>","months":<6 for Entry-tier; 3 otherwise>}
   ```
   Confirm all requested months are consecutive and on time. Missing, partial, late, or ambiguous history does not meet this requirement.

If any lookup fails, is incomplete, or cannot be interpreted reliably, do not invent a result. Resolve the data problem through the appropriate operational procedure; do not approve on incomplete eligibility evidence.

### 4. Decide and record it

Provide the collected normalized facts to `scripts/evaluate_cli.py`. It returns every failed requirement and a single supported denial code using this precedence: account age, cooldown, disputes, replacement card, past due, utilization, payment history, then amount.

If every requirement passed, unlock `approve_credit_limit_increase_5847` and call:
```json
{"credit_card_account_id":"<account_id>","user_id":"<user_id>","new_credit_limit":<current_limit + requested_increase>}
```
Use the precise new total, not the increase amount, as `new_credit_limit`.

If any requirement failed after a submitted request, unlock `deny_credit_limit_increase_5848` and call:
```json
{"credit_card_account_id":"<account_id>","user_id":"<user_id>","denial_reason":"<one permitted code>"}
```
Permitted reasons are: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, `insufficient_payment_history`, `requested_amount_exceeds_limit`, and `other`.

Never approve and deny the same submitted request. If the decision call fails or its state is unknown, do not repeat it blindly; report/escalate according to operational policy.

### 5. Communicate clearly

For approval, confirm that the request was approved and state the new total credit limit. For denial, explain the relevant customer-facing reason and actionable next step. For a cooldown denial, state the calculated next eligible date. Do not expose internal-only eligibility process details beyond an appropriate explanation.

## Helper script

Run the deterministic evaluator with JSON on stdin:

```json
{
  "tier":"entry",
  "current_limit":4000,
  "requested_increase":1000,
  "account_open_date":"2024-01-01",
  "now":"2024-06-01 12:00:00 EST",
  "approved_request_dates":[],
  "has_active_disputes":false,
  "has_pending_replacement":false,
  "account_current":true,
  "past_due_amount":0,
  "current_balance":1000,
  "on_time_months":6
}
```

Example command in a Python-capable runtime:

```sh
python3 scripts/evaluate_cli.py < facts.json
```

The stdout JSON contains `amount_valid`, `maximum_increase`, `new_credit_limit`, `checks`, `failed_reasons`, `eligible`, `denial_reason`, and (when applicable) `next_eligible_date`. Before relying on it, verify that all required input facts came from the completed post-submission checks and that `errors` is empty.
