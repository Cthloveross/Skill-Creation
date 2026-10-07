---
name: credit-limit-increase-processing
description: Process a verified cardholder's credit-limit-increase (CLI) request end to end. Use for tier-based amount validation, mandatory post-submission eligibility checks, recorded approval or denial, and customer communication.
---

# Credit Limit Increase Processing

Use this Skill to process a CLI request in the required operational order. Read customer, account, time, and tool results at runtime. Do not hardcode a customer's identifiers, account details, or an expected decision.

## Verification and account selection

1. Identify the intended credit-card account and confirm that the caller is the account owner or authorized account manager. If more than one account plausibly matches, ask the caller to select one.
2. Before a write action, follow the runtime's identity-verification process: have the caller confirm two profile fields from date of birth, email, phone number, or address; retrieve the corresponding profile using an approved lookup; then call `log_verification` with the complete returned profile and the current timestamp. A name alone is not an identity field.
3. Retrieve the selected account and current time. Obtain a precise requested increase.
4. A percentage request is an amount request: calculate it from the retrieved current limit. If the result is a positive whole number of dollars, it is a valid candidate amount and does not require an unnecessary second confirmation. If it produces fractional dollars, ask the customer for a whole-dollar amount.

## Tier mapping and policy

Use the documented mapping; do not treat a known card type as unknown:

| Card type | Tier |
|---|---|
| Bronze Rewards Card, EcoCard, Business Bronze Rewards Card | entry |
| Silver Rewards Card, Business Silver Rewards Card, Green Rewards Card, Silver Zoom Card | mid |
| Gold Rewards Card, Business Gold Rewards Card, Platinum Rewards Card, Business Platinum Rewards Card, Diamond Elite Card | premium |

| Tier | Minimum account age | Cooldown | Utilization must be below | Consecutive on-time payments | Maximum increase |
|---|---:|---:|---:|---:|---:|
| entry | 120 days | 120 days | 70% | 6 months | 25% of current limit |
| mid | 90 days | 90 days | 80% | 3 months | 50% of current limit |
| premium | 60 days | 60 days | 90% | 3 months | 50% of current limit |

If the card type has no documented mapping, do not guess its tier; obtain authoritative guidance. If the requested increase exceeds the tier cap, tell the customer the maximum allowed and ask whether they want to request that amount instead. Do **not** submit an excessive request.

## Calculation helper

`scripts/cli_math.py` uses Decimal arithmetic to validate amount math and calculate the prospective limit, account age, and utilization.

It reads one JSON object from stdin and writes one JSON object to stdout.

Input schema:

```json
{
  "tier": "entry|mid|premium",
  "current_limit": "numeric amount",
  "current_balance": "numeric amount",
  "account_open_date": "YYYY-MM-DD or MM/DD/YYYY",
  "current_time": "timestamp containing a date",
  "requested_increase_amount": "optional whole-dollar amount",
  "requested_percent": "optional percent, for example 10"
}
```

Supply exactly one of `requested_increase_amount` or `requested_percent`.

Example runnable call:

```sh
printf '%s\n' "$CLI_MATH_INPUT" | python3 scripts/cli_math.py
```

On success, inspect `errors`, `requested_increase_amount`, `maximum_whole_dollar_increase`, and `prospective_new_credit_limit`. Submit only if `valid` is true, the request is a positive integer, and it does not exceed the maximum. The helper floors a non-whole-dollar percentage cap because the submission API accepts whole dollars.

## Required workflow

### 1. Validate amount, then submit

Before submission, determine the documented tier and validate the requested amount with the live account data. Once identity verification and a valid amount are complete, unlock and call `submit_credit_limit_increase_request_7392`:

```json
{
  "credit_card_account_id": "selected account ID",
  "user_id": "verified user ID",
  "requested_increase_amount": "validated integer dollar amount"
}
```

The formal submission is required **before** eligibility checks. Do not defer a valid request merely to re-determine a documented tier or to perform eligibility checks first.

### 2. Perform every eligibility check after submission

Unlock each discoverable tool before calling it. Complete every listed review even if an earlier criterion fails, so the audit record is complete.

1. **Account age:** compare the helper's `account_age_days` with the tier minimum. The minimum day qualifies.
2. **Cooldown:** call `get_credit_limit_increase_history_4829` with `credit_card_account_id`. Review the newest prior approved CLI request. Denied requests do not trigger cooldown. A prior approved request blocks the new request until the full tier cooldown has elapsed. If the history lacks a clear status or relevant date, do not infer a pass.
3. **Disputes:** call `get_user_dispute_history_7291` with `user_id`. Any open, under-review, or other non-final dispute is an active dispute. Closed disputes do not fail this check.
4. **Replacement cards:** call `get_pending_replacement_orders_5765` with `credit_card_account_id`. An empty collection passes. Any order not clearly delivered or cancelled fails this check.
5. **Good standing:** use the retrieved account data to verify the account is current and the past-due balance is zero. A past-due amount or non-current status fails.
6. **Utilization:** use the helper output. Utilization must be strictly below the tier threshold; equality fails.
7. **Payment history:** call `get_payment_history_6183` with `credit_card_account_id` and the tier's required `months`. Verify every required consecutive month is on time. Missing, incomplete, or delinquent history fails.

For an ambiguous, malformed, unavailable, or mismatched tool result, retry only where the documented procedure calls for it (including partial dispute/replacement results). Do not approve without clear passing evidence and do not invent a denial reason merely because evidence is unavailable; follow the normal supported escalation path after preserving the completed checks.

### 3. Record exactly one decision after all checks

Only if every check clearly passes, unlock and call `approve_credit_limit_increase_5847`:

```json
{
  "credit_card_account_id": "selected account ID",
  "user_id": "verified user ID",
  "new_credit_limit": "current limit plus validated increase"
}
```

If a checked condition fails, unlock and call `deny_credit_limit_increase_5848` with the account ID, user ID, and the applicable exact reason:

| Failed requirement | `denial_reason` |
|---|---|
| Minimum account age | `insufficient_account_age` |
| Approved-request cooldown | `cooldown_period_active` |
| Active dispute | `pending_disputes` |
| Pending replacement order | `pending_replacement_card` |
| Past due or not current | `past_due_balance` |
| Utilization at or above threshold | `high_utilization` |
| Required payment history not on time or incomplete | `insufficient_payment_history` |

Use `other` only for a definite post-submission failure with no listed reason. `requested_amount_exceeds_limit` is only for a request that was already recorded despite the mandatory pre-submission cap check. If several conditions fail, record the first applicable reason in the review order while retaining all review results in the case record.

### 4. Communicate the recorded outcome

After the approval or denial tool call, clearly inform the customer:

- **Approval:** confirm approval and the new total credit limit returned or applied by the approval process.
- **Denial:** explain the customer-facing reason and next step without exposing internal-only data. Give a reapplication date for account age or cooldown only when it can be calculated from returned dates. For utilization or payment history, describe the condition to satisfy; for a replacement card, explain it must be delivered or cancelled.
- **Pre-submission excessive amount:** state the maximum and invite the customer to choose a compliant amount.
