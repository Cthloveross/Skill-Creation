---
name: credit-card-dispute-and-cli-processing
description: Process one or both requested credit-card transaction disputes and credit-limit increases (CLIs). Use this Skill to collect dispute filing fields and provisional-credit eligibility, and to submit, review, approve, or deny a tier-based CLI through the required banking tools.
---

# Credit Card Dispute and CLI Processing

Treat a dispute and a CLI as independent requested actions. An incomplete dispute does **not** prevent processing a separately requested valid CLI. A dispute that was successfully filed and remains unresolved does count as an active dispute for the CLI review.

Use supplied runtime account, transaction, customer, and current-time records. Confirm that the selected transaction belongs to the selected account and customer. Do not invent facts missing from the records or customer responses.

## Tool invocation convention

The named banking tools in this Skill may be directly exposed or discoverable depending on the runtime.

- If directly exposed, call the named tool with its documented arguments.
- If it is discoverable, call `unlock_discoverable_agent_tool` using the exact named tool, then call `call_discoverable_agent_tool` with that name and an `arguments` JSON string.
- Do not claim any action succeeded until its banking-tool response succeeds.
- Do not combine a formal CLI submission, its post-submission checks, and its final decision in one tool-call stage. Wait for the submission result, perform the review calls in a later stage, then make the approval/denial call only after those results are available. This preserves the required audit sequence.

## A. Dispute workflow

### 1. Collect all mandatory filing data

Before filing, obtain and validate every required field:

- `transaction_id` for the matching transaction;
- `card_action`: `keep_active` or `cancel_and_reissue`;
- `card_last_4_digits`, exactly the last four digits for the card used;
- `full_name`, `user_id`, registered `phone`, `email`, and `address`;
- `contacted_merchant` as a boolean;
- `purchase_date` and `issue_noticed_date`, formatted `MM/DD/YYYY`;
- `dispute_reason`, one of:
  `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`,
  `goods_services_not_received`, `goods_services_not_as_described`,
  `canceled_subscription_still_charging`, or `refund_never_processed`;
- `resolution_requested`, one of `full_refund`, `partial_refund`, or
  `reversal_of_charge`; and `partial_refund_amount` only for `partial_refund`.

Never infer a required customer answer. In particular, do not file a dispute without `card_last_4_digits`.

If the customer does not know the last four digits, attempt the documented
`get_card_last_4_digits(credit_card_account_id)` retrieval using the tool convention above. If unavailable or unsuccessful, explain that the lookup is unavailable and leave the dispute pending until the customer supplies **only the last four digits**. Explicitly say: **do not send the full card number**. The customer may use the bank app/website card-details view or the documented self-service tool where the runtime supports it. Do not use a full card number as a substitute.

Respect the customer's selected card action. Do not order a replacement card merely because there is a merchant dispute. If the customer requests replacement, handle that as its separate workflow and use `cancel_and_reissue` for the dispute.

### 2. Determine provisional-credit eligibility

Call `get_user_dispute_history_7291(user_id)` and use the current date and account opening date to evaluate eligibility. Set `eligible_for_provisional_credit` to `true` only if all conditions hold:

1. account age is at least 60 days;
2. the reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`;
3. the amount is at least $25.00 and no more than the applicable tier maximum: entry $2,500, mid $5,000, premium $10,000, elite $15,000, invitation $25,000;
4. no more than two disputes were filed in the preceding 12 months;
5. for every non-fraud reason, the customer contacted the merchant; and
6. for `goods_services_not_received`, the purchase was more than 30 days ago.

A dispute may still be filed when provisional credit is false. If needed information or history is unavailable, do not guess eligibility; complete the missing verification before filing.

### 3. File only when complete

Unlock and call `file_credit_card_transaction_dispute_4829` with all required arguments. For `full_refund` or `reversal_of_charge`, omit `partial_refund_amount` unless the runtime explicitly requires optional fields to be null. Clearly state whether the dispute was filed only after successful tool output. If it remains incomplete, state the one or more missing fields and that it was not filed.

## B. CLI workflow

### 1. Determine tier and precheck the amount before submission

Classify the account under the published CLI tiers:

| Tier | Minimum age | Cooldown | Utilization must be below | On-time months | Maximum increase |
| --- | ---: | ---: | ---: | ---: | ---: |
| Entry | 120 days | 120 days | 70% | 6 | 25% of current limit |
| Mid | 90 days | 90 days | 80% | 3 | 50% of current limit |
| Premium | 60 days | 60 days | 90% | 3 | 50% of current limit |

For a request expressed as a desired new total limit, calculate:

`requested_increase_amount = requested_total_limit - current_credit_limit`

The amount must be positive and no greater than the tier maximum. The formal submission accepts the **increase amount**, not the new total limit. If the amount exceeds the maximum, tell the customer the maximum increase and corresponding total and ask whether they want to proceed with an adjusted amount. Do not submit an excessive request. If the tier is outside published CLI rules or cannot be determined, do not invent a rule.

### 2. Submit the valid request first

For a valid amount, call `submit_credit_limit_increase_request_7392` with:

```text
credit_card_account_id: selected account ID
user_id: selected customer ID
requested_increase_amount: integer dollar increase
```

This submission is mandatory and must occur before eligibility review. A separate incomplete dispute must not cause the CLI request to be skipped.

### 3. Perform every post-submission review check

After confirmed submission, perform and retain the results of **all** checks below, even if an earlier one fails:

1. **Cooldown:** call `get_credit_limit_increase_history_4829(credit_card_account_id)`. Only a prior approved request triggers the tier cooldown; denied requests do not. Use the most recent approved submission date.
2. **Active disputes:** call `get_user_dispute_history_7291(user_id)`. Treat open, under-review, or other unresolved disputes as pending. A dispute that was not filed because a required field is missing is not an active dispute.
3. **Replacement orders:** call `get_pending_replacement_orders_5765(credit_card_account_id)`. Any order not clearly delivered or cancelled blocks the CLI.
4. **Account age:** calculate days from account opening date to the current date and apply the tier threshold.
5. **Account standing:** verify the account is current and has no past-due balance.
6. **Utilization:** calculate `current_balance / credit_limit * 100`; it must be strictly below the tier threshold.
7. **Payment history:** call `get_payment_history_6183` with `months=6` for entry tier or `months=3` for mid/premium tier. Verify every required consecutive month is on time.

Do not treat a missing, ambiguous, or failed read-only result as a passing check. If a required check cannot be obtained, keep the review incomplete, explain the limitation, and use a supported escalation path rather than approving or creating an unsupported denial reason.

### 4. Record the decision after all checks

After the review results are available:

- If every requirement passes, call `approve_credit_limit_increase_5847` with the account ID, user ID, and `new_credit_limit = current_credit_limit + requested_increase_amount`.
- If any requirement fails, call `deny_credit_limit_increase_5848` once. Select the first applicable allowed reason in this review order:
  1. `insufficient_account_age`
  2. `cooldown_period_active`
  3. `pending_disputes`
  4. `pending_replacement_card`
  5. `past_due_balance`
  6. `high_utilization`
  7. `insufficient_payment_history`

Use `requested_amount_exceeds_limit` only where an over-limit request was actually submitted under an exceptional supported workflow; normally it is rejected before submission. Do not use `other` merely to avoid completing required checks.

## Customer communication

Report each request separately. For an incomplete dispute, say it was not filed and identify the exact missing item; when the missing item is card digits, ask for only the last four and warn not to send a full card number. For a filed dispute, state the selected card action and whether provisional credit applies, describing it as temporary. For a CLI, confirm successful submission and then communicate the recorded approval with the new total limit, or the recorded denial reason and the practical next step. Never represent a tool action as complete before a successful result.

## Optional deterministic helper

`scripts/assess_credit_card_case.py` evaluates published tier thresholds and produces an auditable precheck from JSON without calling banking tools or changing accounts.

Input is one JSON object on stdin:

- `now`: current date (`YYYY-MM-DD` or `MM/DD/YYYY`)
- `account`: object with `tier` (entry, mid, premium, elite, or invitation), `date_of_account_open`, `credit_limit`, `current_balance`, and `past_due_amount`
- optional `dispute`: object with `amount`, `reason`, `purchase_date`, `contacted_merchant`, and either `disputes_last_12_months` or dated `dispute_records`
- optional `cli`: object with `requested_increase_amount`, `last_approved_cli_submission_date` (`null` if none), `pending_disputes`, `pending_replacement_card`, and `consecutive_on_time_months`

It emits one JSON object containing `valid`, `errors`, and one or both of `provisional_credit` and `cli`. `unknown` or `undetermined` is not a pass and requires live tool verification. Check the helper input against the runtime records before using its result.
