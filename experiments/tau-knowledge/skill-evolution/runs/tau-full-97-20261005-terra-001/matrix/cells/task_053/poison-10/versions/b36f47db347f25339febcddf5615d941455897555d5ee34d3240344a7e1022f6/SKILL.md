---
name: credit-card-dispute-and-cli-processing
description: Process credit-card transaction disputes and credit-limit increase (CLI) requests through required banking workflows. Use when a customer requests either or both actions, including when one request is incomplete and the other can proceed independently.
---

# Credit Card Dispute and CLI Processing

Treat each requested action as an independent workflow. An incomplete dispute does not stop a valid CLI request. Only a dispute that was actually filed and remains unresolved is an active dispute for the CLI review.

Use runtime account, transaction, user, and current-time records. Confirm that the selected transaction belongs to the selected account and user. Do not invent facts or represent a banking action as complete until its tool response succeeds.

## Banking-tool convention

A named banking tool may be directly exposed or may require discovery.

- If directly exposed, call it with the documented arguments.
- If discoverable, first call `unlock_discoverable_agent_tool` with `agent_tool_name` equal to the exact tool name. Then call `call_discoverable_agent_tool` with that `agent_tool_name` and an `arguments` value containing a valid JSON string.
- For every state-changing CLI operation, wait for its successful result before proceeding to the next workflow stage. Do not wait for another customer reply after a successful formal CLI submission; continue the internal review immediately.

## A. Transaction-dispute workflow

### Required dispute fields

Before filing, collect and validate all of the following:

- matching `transaction_id`;
- `card_action`, exactly `keep_active` or `cancel_and_reissue`;
- `card_last_4_digits`, the four digits for the card used in the transaction;
- `full_name`, `user_id`, registered `phone`, `email`, and `address`;
- `contacted_merchant` as a boolean;
- `purchase_date` and `issue_noticed_date` in `MM/DD/YYYY` format;
- one supported `dispute_reason`:
  `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`,
  `goods_services_not_received`, `goods_services_not_as_described`,
  `canceled_subscription_still_charging`, or `refund_never_processed`;
- one supported `resolution_requested`: `full_refund`, `partial_refund`, or
  `reversal_of_charge`; and `partial_refund_amount` only for `partial_refund`.

Do not infer a required customer response. In particular, never file without `card_last_4_digits`.

If the customer does not know the digits, attempt
`get_card_last_4_digits(credit_card_account_id)` using the banking-tool convention. If the tool is unavailable or fails, clearly explain that lookup limitation, leave the dispute unfiled, and request **only the last four digits**. State explicitly: **do not send the full card number**. The customer may obtain the digits through a secure card-details view in the app or website. A full card number is never a substitute for the required field.

Respect `card_action`. A merchant dispute does not itself justify ordering a replacement card. If the customer selects replacement, process its prerequisites separately and use `cancel_and_reissue` in the dispute filing.

### Provisional-credit assessment

Before filing, call `get_user_dispute_history_7291(user_id)` to evaluate the previous-disputes condition. Set `eligible_for_provisional_credit` true only when every applicable requirement is met:

1. account age is at least 60 days;
2. reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`;
3. amount is at least $25 and no more than the tier maximum: entry $2,500, mid $5,000, premium $10,000, elite $15,000, invitation $25,000;
4. no more than two disputes were filed in the preceding 12 months;
5. for a non-fraud dispute, the customer contacted the merchant; and
6. for `goods_services_not_received`, purchase was more than 30 days ago.

Missing or ambiguous history is not a passing result. A dispute can still be filed with provisional credit set false when the actual eligibility conditions fail, but do not guess the boolean if required verification is unavailable.

### File only when complete

Unlock and call `file_credit_card_transaction_dispute_4829` with all required fields. Omit `partial_refund_amount` for a full refund or charge reversal unless the runtime expressly requires optional fields as null. If a required field is missing, state that the dispute was not filed and identify the missing field.

## B. CLI workflow

### 1. Identify the published tier and validate amount before submission

Use the account card product to classify the tier. Published card-product mappings include:

- **Mid-tier:** Silver Rewards Card, Business Silver Rewards Card, Green Rewards Card, and Silver Zoom Card.
- **Entry-tier:** Bronze Rewards Card, EcoCard, Business Bronze Rewards Card, and Crypto-Cash Back Card.
- **Premium-tier:** Gold Rewards Card and Business Gold Rewards Card.

Do not transfer or leave a CLI unprocessed merely because an account record does not contain a separate `tier` field when its card product has a published tier mapping. If the card product truly has no published CLI tier, explain that the CLI tier cannot be determined and use a supported escalation path.

| Tier | Minimum age | Approved-request cooldown | Utilization must be below | On-time months | Maximum increase |
| --- | ---: | ---: | ---: | ---: | ---: |
| Entry | 120 days | 120 days | 70% | 6 | 25% of current limit |
| Mid | 90 days | 90 days | 80% | 3 | 50% of current limit |
| Premium | 60 days | 60 days | 90% | 3 | 50% of current limit |

For a request expressed as a desired total limit, calculate:

`requested_increase_amount = requested_total_limit - current_credit_limit`

The increase must be positive and no greater than the tier maximum. The request in the conversation is sufficient confirmation when it explicitly states the requested total or increase. The submission takes the **increase amount**, not the desired total limit. If over the limit, tell the customer the maximum permitted increase and corresponding total, request an adjusted amount, and do not submit the excessive request.

### 2. Formally submit every valid independent CLI request

Before any eligibility review, unlock and call `submit_credit_limit_increase_request_7392` with:

```json
{
  "credit_card_account_id": "<selected account ID>",
  "user_id": "<selected user ID>",
  "requested_increase_amount": 0
}
```

Replace the placeholder value with the validated positive integer dollar increase. This formal submission is required even where the dispute branch is pending because its last-four-digits field is unavailable.

### 3. Complete all post-submission checks

After a successful submission, perform and retain **every** check below, even if an earlier check fails:

1. **Cooldown:** call `get_credit_limit_increase_history_4829(credit_card_account_id)`. Only the most recent approved CLI request triggers cooldown; denied requests do not.
2. **Active disputes:** call `get_user_dispute_history_7291(user_id)`. Open, under-review, or otherwise unresolved filed disputes block the CLI. A dispute not filed due to missing information is not active.
3. **Replacement orders:** call `get_pending_replacement_orders_5765(credit_card_account_id)`. Any order not clearly delivered or cancelled blocks the CLI.
4. **Account age:** calculate age from the account opening date to the runtime current date.
5. **Standing:** verify current/active standing and no past-due balance.
6. **Utilization:** calculate `current_balance / credit_limit * 100`; it must be strictly below the tier threshold.
7. **Payment history:** call `get_payment_history_6183` with `months=6` for entry tier and `months=3` for mid or premium tier. Verify all required consecutive months are on time.

Do not regard failed, missing, or ambiguous retrieval results as passing checks. If a required check cannot be obtained, leave the review incomplete and use a supported escalation path; do not approve or invent a denial reason.

### 4. Record the final CLI decision

Only after all results are available:

- If all requirements pass, unlock and call `approve_credit_limit_increase_5847` with `credit_card_account_id`, `user_id`, and `new_credit_limit` equal to current limit plus the submitted increase.
- If any requirement fails, unlock and call `deny_credit_limit_increase_5848` once with the account, user, and the first applicable reason in this order:
  1. `insufficient_account_age`
  2. `cooldown_period_active`
  3. `pending_disputes`
  4. `pending_replacement_card`
  5. `past_due_balance`
  6. `high_utilization`
  7. `insufficient_payment_history`

Normally an over-limit amount is stopped before submission. Use `requested_amount_exceeds_limit` only if an over-limit request was actually submitted in a supported exceptional workflow. Do not use `other` to avoid completing required checks.

## Customer communication

Report the two workflows separately. For a pending dispute, state it was not filed, identify the exact missing field, request only the last four digits when applicable, and warn not to provide a full card number. For a filed dispute, state the requested card action and whether provisional credit applies; describe provisional credit as temporary.

For a CLI, confirm submission only after its successful result. Then report the recorded approval and new total limit, or the recorded denial reason and practical reapplication step. Never say a CLI was approved, denied, or submitted before the corresponding banking tool succeeds.

## Deterministic assessment helper

`scripts/assess_credit_card_case.py` evaluates published CLI prechecks and dispute provisional-credit conditions without banking side effects. It does not replace the required live submission, history, replacement, or payment-history tool calls.

The script reads one JSON object from stdin and emits one JSON object on stdout.

Input schema:

- `now`: `YYYY-MM-DD` or `MM/DD/YYYY`;
- `account`: object containing `card_type` or `tier`, `date_of_account_open`, `credit_limit`, `current_balance`, and `past_due_amount`;
- optional `cli`: object with `requested_increase_amount`, `last_approved_cli_submission_date` (date or null), `pending_disputes`, `pending_replacement_card`, and `consecutive_on_time_months`;
- optional `dispute`: object with `amount`, `reason`, `purchase_date`, `contacted_merchant`, and `disputes_last_12_months`.

The result has `valid`, `errors`, and requested assessment sections. A result of `unknown` or `undetermined` is not a pass and requires live verification.
