---
name: credit-card-dispute-and-cli-processing
description: Process credit-card transaction disputes and credit-limit increase (CLI) requests through required banking workflows. Use for either or both requests, including when a dispute is incomplete but a CLI can proceed independently.
---

# Credit Card Dispute and CLI Processing

Treat a dispute and a CLI as independent workflows. An incomplete, unfiled dispute does not prevent processing a valid CLI request. Do not invent facts, claim a bank action occurred before its tool succeeds, or treat unavailable verification as a passing result.

Use the selected customer's runtime account, transaction, contact, and current-time records. Confirm that the selected transaction belongs to the selected account and user.

## Banking-tool convention

A named banking tool may be directly exposed or discoverable.

- Call directly exposed tools with their documented arguments.
- For a discoverable agent tool, first call `unlock_discoverable_agent_tool` with `agent_tool_name` set to the exact tool name. Then call `call_discoverable_agent_tool` with that same name and an `arguments` value that is a valid JSON object encoded as a string.
- For every state-changing action, wait for and inspect the tool result. Continue the post-submission CLI review immediately after a successful submission.

## A. Dispute workflow

### Required filing data

File a transaction dispute only after collecting and validating all required values:

- matching `transaction_id`;
- `card_action`: exactly `keep_active` or `cancel_and_reissue`;
- `card_last_4_digits` for the card used in the transaction;
- `full_name`, `user_id`, registered `phone`, `email`, and `address`;
- boolean `contacted_merchant`;
- `purchase_date` and `issue_noticed_date` in `MM/DD/YYYY` format;
- a supported `dispute_reason`: `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, or `refund_never_processed`;
- `resolution_requested`: `full_refund`, `partial_refund`, or `reversal_of_charge`; and `partial_refund_amount` only when the resolution is `partial_refund`;
- a verified `eligible_for_provisional_credit` boolean.

Do not infer a required customer response. In particular, never file without `card_last_4_digits`.

If the customer does not know the digits, attempt `get_card_last_4_digits(credit_card_account_id)` under the banking-tool convention. If it is unavailable or fails, explain the lookup limitation, leave the dispute unfiled, ask for **only the last four digits**, and explicitly say: **do not send the full card number**. The customer may obtain the digits through a secure card-details view in the app or website. A full card number is never a substitute.

Respect `card_action`. A merchant dispute alone does not justify a replacement card. If replacement is selected, process its separate prerequisites and use `cancel_and_reissue` in the dispute filing.

### Provisional credit

Before filing, retrieve dispute history with `get_user_dispute_history_7291(user_id)`. Set `eligible_for_provisional_credit` true only if every applicable condition passes:

1. account age is at least 60 days;
2. the reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`;
3. amount is at least $25 and does not exceed the tier maximum: entry $2,500, mid $5,000, premium $10,000, elite $15,000, invitation $25,000;
4. no more than two disputes were filed in the preceding 12 months;
5. for a non-fraud reason, the customer contacted the merchant; and
6. for `goods_services_not_received`, the purchase was more than 30 days ago.

Missing or ambiguous history is not a pass. A complete dispute may be filed with provisional credit false if eligibility actually fails, but do not guess the value when required verification is unavailable.

### Filing

Unlock and call `file_credit_card_transaction_dispute_4829` with all required fields. Omit `partial_refund_amount` for a full refund or charge reversal unless the runtime explicitly requires null. If a required field is missing, clearly state that the dispute was not filed and name the missing field.

## B. CLI workflow

### 1. Determine tier and validate the requested amount before submission

Classify the tier using the account's card product, even when no separate tier field exists:

- **Entry:** Bronze Rewards Card, EcoCard, Business Bronze Rewards Card, Crypto-Cash Back Card.
- **Mid:** Silver Rewards Card, Business Silver Rewards Card, Green Rewards Card, Silver Zoom Card.
- **Premium:** Gold Rewards Card, Business Gold Rewards Card.

If no published CLI tier applies to the product, explain that the tier cannot be determined and use a supported escalation path; do not silently abandon the request.

| Tier | Minimum age | Approved-request cooldown | Utilization must be below | Consecutive on-time months | Maximum increase |
| --- | ---: | ---: | ---: | ---: | ---: |
| Entry | 120 days | 120 days | 70% | 6 | 25% of current limit |
| Mid | 90 days | 90 days | 80% | 3 | 50% of current limit |
| Premium | 60 days | 60 days | 90% | 3 | 50% of current limit |

For a request expressed as a target limit, calculate:

`requested_increase_amount = requested_total_limit - current_credit_limit`

The increase must be positive and no more than the tier maximum. The customer's explicit requested total or increase is sufficient confirmation. Submit the **increase amount**, not the desired total. If the request exceeds the limit, communicate the maximum increase and corresponding total, request an adjusted amount, and do not submit the excessive request.

### 2. Submit the valid CLI request

Before eligibility review, unlock and call `submit_credit_limit_increase_request_7392` with:

```json
{
  "credit_card_account_id": "<selected account ID>",
  "user_id": "<selected user ID>",
  "requested_increase_amount": 0
}
```

Replace the placeholder with the validated positive integer increase. A pending dispute branch caused by unavailable last four digits does not prevent this submission.

### 3. Complete every required post-submission check

After a successful submission, perform every check below, retaining results even if an earlier criterion fails:

1. **Cooldown:** call `get_credit_limit_increase_history_4829(credit_card_account_id)`. Only the most recent approved request triggers cooldown; denied requests do not.
2. **Active disputes:** call `get_user_dispute_history_7291(user_id)`. Any unresolved filed dispute blocks the CLI. An unfiled dispute missing required information is not active.
3. **Replacement orders:** call `get_pending_replacement_orders_5765(credit_card_account_id)`. An order not clearly delivered or cancelled blocks the CLI.
4. **Account age:** calculate from opening date through the runtime business date.
5. **Good standing:** verify active/current status and no past-due amount.
6. **Utilization:** calculate `current_balance / credit_limit * 100`; it must be strictly below the tier threshold.
7. **Payment history:** call `get_payment_history_6183` with `months=6` for entry tier or `months=3` for mid/premium tier.

For payment history, assess eligibility **as of the CLI submission/business date**. Each required payment must be on time, dated on or before that date, and form the required consecutive payment-month sequence. A record dated after submission or after the current business date is future-dated evidence and cannot count, even if the returned status says `ON_TIME`. Therefore, if fewer than the required eligible on-time months existed by the decision date, the criterion fails as `insufficient_payment_history`.

Do not treat failed, missing, malformed, ambiguous, or future-only retrieval evidence as passing. If a required check cannot be obtained at all, leave the review incomplete and use a supported escalation path rather than approving or inventing a denial reason.

### 4. Record the decision

Only after all available required checks are complete:

- If all criteria pass, unlock and call `approve_credit_limit_increase_5847` with the account, user, and `new_credit_limit` equal to current limit plus the submitted increase.
- If a criterion fails, unlock and call `deny_credit_limit_increase_5848` once with the account, user, and the first applicable reason in this order:
  1. `insufficient_account_age`
  2. `cooldown_period_active`
  3. `pending_disputes`
  4. `pending_replacement_card`
  5. `past_due_balance`
  6. `high_utilization`
  7. `insufficient_payment_history`

An excessive request is normally stopped before submission. Use `requested_amount_exceeds_limit` only when an excessive request was actually submitted through a supported exceptional workflow. Do not use `other` merely to avoid required checks.

## Customer communication

Report the workflows separately.

- For a pending dispute, say it was not filed, identify the exact missing field, request only the last four digits when relevant, and warn not to provide a full card number.
- For a filed dispute, state the requested card action and whether provisional credit applies; describe provisional credit as temporary.
- For a CLI, confirm submission only after success. Then report the recorded approval and new limit, or the recorded denial reason and a practical reapplication condition. For insufficient payment history, explain that the required consecutive on-time payments were not all established by the review date (including that future-dated records cannot qualify) and that the customer may reapply once the required history exists. Do not invent an exact reapplication date unless supported by the retrieved records.

## Deterministic assessment helper

`scripts/assess_credit_card_case.py` evaluates published dispute provisional-credit rules and CLI prechecks without banking side effects. It does not replace the required live submission, history, replacement, or payment-history calls.

Run it by sending one JSON object on stdin; it emits one JSON object on stdout. It accepts:

- `now`: `YYYY-MM-DD` or `MM/DD/YYYY` business date;
- `account`: object containing `card_type` or `tier`, `date_of_account_open`, `credit_limit`, `current_balance`, and `past_due_amount`;
- optional `cli`: object containing `requested_increase_amount`, `last_approved_cli_submission_date` (date or null), `pending_disputes`, `pending_replacement_card`, and either `consecutive_on_time_months` or `payment_records`;
- a `payment_records` item is an object with `payment_date` and `status`; records after `now` do not count;
- optional `dispute`: object with `amount`, `reason`, `purchase_date`, `contacted_merchant`, and `disputes_last_12_months`.

Output contains `valid`, `errors`, and requested assessment sections. `unknown` or `undetermined` never means a live workflow criterion passed.
