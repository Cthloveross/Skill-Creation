---
name: credit-limit-increase-processing
description: Process a verified cardholder's credit-limit-increase (CLI) request using the required submit-then-review workflow, tier eligibility rules, payment history, and documented approval or denial tools. Use for credit-card CLI requests, not for replacement-card requests or general limit information.
---

# Credit Limit Increase Processing

## Purpose and prerequisites

Use this Skill to safely process a customer-requested increase to an existing credit-card limit. Perform banking actions only after identity, authority, account ownership, the requested amount, and relevant account details are verified.

1. Identify the customer and locate their card account using the normal read-only customer and card-account tools.
2. Verify identity interactively: obtain confirmation of **two of four** identity fields (date of birth, email, phone number, or address) from the customer, compare them with the retrieved record, obtain the current timestamp, and call `log_verification` with the complete retrieved identity record and timestamp.
   - A supplied name, account lookup result, or a field merely displayed by a tool is not customer identity verification.
   - If two fields do not match, do not process the request. Follow the runtime's appropriate escalation procedure.
3. Confirm the customer is the account owner or an authorized account manager and that the selected account belongs to the verified `user_id`. Confirm the exact card/account to be changed.
4. Confirm the requested increase and that the customer understands it is an increase, not a requested total limit. If a customer gives a percentage, calculate the corresponding whole-dollar increase from the current credit limit and clearly confirm the resulting dollar amount before treating it as the request. Do not silently round a fractional-dollar result.

The account lookup should provide the current limit, balance, open date, account status, and past-due amount. Use the current timestamp for date-based checks.

## Tier rules

Map the card product to one of these tiers before continuing. Bronze Rewards is entry-tier.

| Tier | Minimum age | Cooldown after an **approved** request | Utilization must be below | Payment months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | 70% | 6 consecutive on-time months | 25% of current limit |
| Mid-tier | 90 days | 90 days | 80% | 3 consecutive on-time months | 50% of current limit |
| Premium-tier | 60 days | 60 days | 90% | 3 consecutive on-time months | 50% of current limit |

Use `scripts/cli_amount.py` to calculate and validate a percentage or dollar request deterministically. It does not call banking tools and does not make a decision.

Example:

```sh
printf '%s' '{"tier":"entry","current_credit_limit":"4000","requested_increase":"10%"}' | python3 scripts/cli_amount.py
```

The script accepts a JSON object on stdin:

- `tier`: `entry`, `mid`, or `premium` (case-insensitive; `entry-tier` etc. are accepted)
- `current_credit_limit`: positive decimal number or numeric string
- `requested_increase`: a positive whole-dollar number/string, or a percentage string such as `"10%"`

It emits JSON with `requested_increase_amount`, `maximum_increase_amount`, `new_credit_limit`, `within_maximum`, and any `errors`. A usable result has an empty `errors` list and an integer `requested_increase_amount`.

## Ordered processing workflow

### 1. Validate the amount before any CLI submission

Calculate the tier maximum against the **current** credit limit. If the requested increase exceeds that maximum:

- Do **not** submit a CLI request and do not call approval or denial tools.
- Tell the customer the maximum whole-dollar increase permitted and ask whether they want to make a new request at or below that amount.
- If they provide an adjusted amount, reconfirm it and restart this amount-validation step.

Do not submit a request with an invalid, zero, negative, non-integral, or over-limit increase.

### 2. Submit the valid request

Once the amount is valid and confirmed, unlock and call the documented CLI submission tool through the discoverable-agent-tool mechanism:

1. `unlock_discoverable_agent_tool` for `submit_credit_limit_increase_request_7392`.
2. `call_discoverable_agent_tool` with that name and JSON arguments:
   - `credit_card_account_id`
   - `user_id`
   - `requested_increase_amount` (integer dollars)

Record the returned request outcome. Do not submit it a second time if the action outcome is unknown or a timeout/technical error leaves its completion uncertain; escalate instead.

### 3. Complete every eligibility check after submission

Complete all checks below before deciding, even when an earlier check fails, so the review is complete. Unlock each documented specialized tool before calling it. If a required check is unavailable, malformed, or ambiguous, do not approve and do not invent a denial reason; explain that processing cannot be completed and escalate using the runtime's technical-system procedure.

1. **Account age:** Calculate calendar elapsed days from the account open date to the current timestamp. It passes on the tier minimum day.
2. **Cooldown:** Unlock and call `get_credit_limit_increase_history_4829` with `credit_card_account_id`. Find the most recent **approved** CLI request. It passes only if no approved request exists within the tier cooldown; denied requests do not create a cooldown. The next eligible date is the approved request submission date plus the tier cooldown in full days.
3. **Pending disputes:** Unlock and call `get_user_dispute_history_7291` with `user_id`. Treat any dispute with a non-final active status (such as `open` or `under_review`) as pending. Closed disputes do not block the request.
4. **Replacement orders:** Unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id`. An empty collection passes. If any order is not clearly `delivered` or `cancelled` (for example `pending` or `shipped`), it fails.
5. **Good standing:** Confirm the selected account is current/active and has no past-due balance. A positive past-due amount fails.
6. **Utilization:** Compute `current_balance / current_credit_limit * 100`. The result must be strictly below the tier threshold; equality fails.
7. **Payment history:** Unlock and call `get_payment_history_6183` with `credit_card_account_id` and the tier's required `months`. Verify every one of those most recent consecutive months is on time. Any missing, late, or insufficient required record fails.

### 4. Record the decision

If every check passes, unlock and call `approve_credit_limit_increase_5847` with:

- `credit_card_account_id`
- `user_id`
- `new_credit_limit` = current credit limit plus approved requested increase, as a numeric dollar amount

If one or more checks fail, unlock and call `deny_credit_limit_increase_5848` with the account ID, user ID, and one documented denial reason. Use the first applicable reason in this deterministic order:

1. `insufficient_account_age`
2. `cooldown_period_active`
3. `pending_disputes`
4. `pending_replacement_card`
5. `past_due_balance`
6. `high_utilization`
7. `insufficient_payment_history`

`requested_amount_exceeds_limit` is only applicable if an already-submitted request somehow requires a denial for that reason; ordinarily over-limit requests are stopped before submission. Use `other` only for a completed review failure not represented above. Never approve and deny the same request, and never retry an unknown approval or denial outcome.

### 5. Communicate clearly

For approval, confirm the increase amount and the resulting new total credit limit. For denial, give the customer the applicable reason and a useful next step: the minimum-age date, cooldown end date, resolution of a pending dispute/replacement, curing past due, lowering utilization, or building the required on-time payment history. Do not disclose internal-only details beyond what is needed to explain the outcome.

## Validation checklist

Before completing the interaction, ensure the audit trail has: a logged two-field identity verification; account ownership match; confirmed whole-dollar amount; max amount check before submission; exactly one known submission outcome; all seven post-submission checks; and exactly one known approval or denial outcome where the review was complete.
