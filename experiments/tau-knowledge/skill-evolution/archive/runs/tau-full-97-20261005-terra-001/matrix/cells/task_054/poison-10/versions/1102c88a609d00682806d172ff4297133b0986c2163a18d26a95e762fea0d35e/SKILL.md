---
name: credit-card-cli-fraud-dispute-and-replacement
description: Process a customer's requested credit-limit increase before a fraud dispute and replacement-card request. Use when the customer has a card transaction to dispute, needs a replacement, and/or requests a CLI; enforces CLI submission/eligibility order, provisional-credit evaluation, replacement prerequisites, and documented banking-tool calls.
---

# Credit Card CLI, Fraud Dispute, and Replacement

Use this Skill for a multi-part credit-card request. Preserve the customer's requested ordering when feasible. In particular, if the customer asks for the CLI before filing a dispute or ordering a replacement, finish the CLI workflow first: an active dispute or pending replacement can make the CLI ineligible.

## Safety and data rules

- Read account, user, transaction, and history data at execution time. Do not reuse identifiers, amounts, dates, contact details, or results from another case.
- Confirm that the requester is the account owner or authorized account manager before submitting a CLI.
- A replacement order requires standard identity verification. Have the customer affirm **two of** date of birth, email, phone number, or address; compare against the user record without disclosing unprompted values. Call `log_verification` with the complete record and current timestamp only after two fields match.
- If required information, a required tool, a tool result, or replacement eligibility is unavailable or ambiguous, do not guess or submit the affected action. Explain what is needed or escalate through the normal process.
- Agent actions use normal banking tools. Where a source specifies a discoverable agent tool, first call `unlock_discoverable_agent_tool`, then invoke it with `call_discoverable_agent_tool`. An unlock or call is not assumed successful unless its response confirms success.

## 1. Collect and normalize facts

Obtain the current time, customer record, account record, and the disputed transaction. Confirm that the transaction belongs to the selected account. Collect the customer's dispute reason, whether they contacted the merchant, resolution requested, issue-noticed date, replacement reason, requested shipping speed, and CLI increase amount.

Use `scripts/evaluate_credit_card_request.py` to calculate deterministic thresholds and produce a review checklist after converting tool responses into its normalized JSON input. Its output is a recommendation, not a substitute for required banking-tool calls.

Classify Gold and Business Gold as premium-tier for the documented CLI and provisional-credit limits. For a fraud transaction where replacement is requested, the dispute `card_action` is `cancel_and_reissue`.

## 2. Execute the CLI first when the customer requests that order

### 2.1 Validate amount before any CLI submission

Determine the tier and current credit limit. Per-request CLI caps are:

| Tier | Maximum increase | On-time months | Minimum age | Cooldown | Utilization must be below |
|---|---:|---:|---:|---:|---:|
| Entry | 25% of current limit | 6 | 120 days | 120 days | 70% |
| Mid | 50% | 3 | 90 days | 90 days | 80% |
| Premium | 50% | 3 | 60 days | 60 days | 90% |

If the requested increase is greater than the cap, do **not** submit it. State the maximum dollar increase and obtain a new explicit amount. A zero, negative, non-numeric, or otherwise unsupported amount also requires clarification. Only continue after a valid amount is confirmed.

### 2.2 Submit first, then perform every eligibility check

For a valid confirmed amount, unlock and call `submit_credit_limit_increase_request_7392` with:

```json
{"credit_card_account_id":"<account id>","user_id":"<user id>","requested_increase_amount":<whole dollar increase>}
```

Do this **before** internal eligibility review. The formal submission is required even if a later eligibility check will result in denial. Do not expose internal eligibility details beyond the customer-facing decision explanation.

After a successful submission, complete **all** of the following checks and retain each result in the case record; do not stop at the first failure:

1. Calculate account age from the account-open date and current time.
2. Unlock and call `get_credit_limit_increase_history_4829` with `credit_card_account_id`. Only a most recent **approved** request starts the tier cooldown; denied requests do not. The cooldown has elapsed only after the required full number of days.
3. Unlock and call `get_user_dispute_history_7291` with `user_id`. Treat an open, active, or under-review dispute as a pending dispute. If response status wording is unclear, treat it as ambiguous and do not approve.
4. Unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id`. An empty collection, or only delivered/cancelled records, passes. Any non-final status such as pending or shipped fails.
5. Verify the account is current: it must be active/current and have no past-due balance.
6. Compute utilization as `current_balance / credit_limit * 100`. It must be strictly below the tier threshold; equality fails.
7. Unlock and call `get_payment_history_6183` with `credit_card_account_id` and tier-required `months`. Confirm every required consecutive month is on time.

If all checks pass, unlock and call `approve_credit_limit_increase_5847`:

```json
{"credit_card_account_id":"<account id>","user_id":"<user id>","new_credit_limit":<current limit + confirmed increase>}
```

If any check fails, unlock and call `deny_credit_limit_increase_5848` with one permitted reason. Map failures as follows: age → `insufficient_account_age`; cooldown → `cooldown_period_active`; active dispute → `pending_disputes`; non-final replacement → `pending_replacement_card`; past due/not current → `past_due_balance`; utilization threshold → `high_utilization`; required on-time payments absent → `insufficient_payment_history`; pre-submission amount excess → `requested_amount_exceeds_limit`; otherwise → `other`. If multiple checks fail after submission, record a deterministic primary reason in this order: age, cooldown, disputes, replacement, standing, utilization, payment history, other; retain all failures in notes.

For approval, communicate the new total limit. For denial, state the customer-appropriate reason and, where calculable, the next date or condition for reapplying.

## 3. File the dispute after the CLI decision

Gather all required dispute fields. Normalize dates to `MM/DD/YYYY`. Before filing, unlock and call `get_user_dispute_history_7291` if a current result is not already available, then evaluate provisional credit:

- account open at least 60 days;
- reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received` where purchase was more than 30 days ago;
- transaction amount is at least $25 and no more than the card-tier limit (entry $2,500; mid $5,000; premium $10,000; elite $15,000; invitation $25,000);
- no more than two disputes were filed in the preceding 12 months; and
- for every non-fraud reason, customer contacted the merchant.

Set `eligible_for_provisional_credit` true only when every applicable condition is true. This evaluation does not change whether a valid dispute is filed.

Unlock `file_credit_card_transaction_dispute_4829`, then call it with a JSON string containing every required field:

```json
{
  "transaction_id":"<transaction id>",
  "card_action":"keep_active or cancel_and_reissue",
  "card_last_4_digits":"<last four>",
  "full_name":"<customer name>",
  "user_id":"<user id>",
  "phone":"<registered phone>",
  "email":"<registered email>",
  "address":"<registered address>",
  "contacted_merchant":false,
  "purchase_date":"MM/DD/YYYY",
  "issue_noticed_date":"MM/DD/YYYY",
  "dispute_reason":"<allowed reason>",
  "resolution_requested":"full_refund or partial_refund or reversal_of_charge",
  "eligible_for_provisional_credit":true
}
```

Include `partial_refund_amount` only for `partial_refund`. Allowed reason values are exactly: `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, and `refund_never_processed`. Allowed resolutions are exactly `full_refund`, `partial_refund`, and `reversal_of_charge`.

## 4. Order the replacement card

Before ordering, complete the identity verification described above. Also unlock and call `get_pending_replacement_orders_5765` immediately before the order. Do not order if any prior replacement is still pending or shipped; wait for delivery or cancellation. Confirm the selected address, exactly one allowed reason (`fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, `other`), shipping choice, and replacement eligibility including the tier's 60-day replacement cap (entry 2, mid 3, premium-and-above 4). Do not claim eligibility if the necessary replacement-history evidence cannot be confirmed.

For fraud suspected or stolen, recommend expedited delivery. Standard is 7–10 business days and free. Expedited is 2–3 business days; it is complimentary for premium-tier and above, $10 for mid-tier, and $15 for entry-tier. Where a fee applies, obtain and record consent.

Unlock `order_replacement_credit_card_7291`, then call it using the documented fields (use the unlocked schema's account-key spelling if it differs):

```json
{
  "account_id":"<credit-card account id>",
  "reason":"fraud_suspected",
  "shipping_address":"<confirmed address>",
  "shipping_speed":"standard or expedited",
  "expedited_fee_acknowledgement":true,
  "notes":"<relevant fraud, delivery, or customer context>"
}
```

For complimentary expedited shipping, record that no fee applies; if the tool requires its acknowledgement boolean, use the schema-supported value that represents no paid-fee consent rather than fabricating consent.

After successful order, tell the customer their old card is cancelled for new purchases, a new number/CVV will be issued while the account number remains unchanged, expected delivery timing, and that order and shipping emails will arrive. Encourage review of recent transactions for other unauthorized activity.

## 5. Completion record

Document each request, tool response/reference, all CLI checks and calculation inputs, identity-verification timestamp, dispute provisional-credit determination, replacement eligibility, order status, and customer communication. Never report an approval, filed dispute, or ordered replacement unless the associated tool call succeeded.

## Script interface and validation

Run:

```bash
python3 scripts/evaluate_credit_card_request.py <<'JSON'
{"now":"2025-01-01T00:00:00-05:00","account":{"tier":"premium","opened_on":"2023-01-01","credit_limit":5000,"current_balance":100,"past_due_amount":0,"status":"ACTIVE"},"cli":{"requested_increase":2500,"approved_request_dates":[],"has_active_dispute":false,"has_pending_replacement":false,"on_time_months":3},"dispute":{"amount":100,"reason":"unauthorized_fraudulent_charge","purchase_date":"2024-12-01","contacted_merchant":false,"disputes_last_12_months":0}}
JSON
```

The script reads one JSON object from stdin and emits one JSON object to stdout. It accepts ISO dates or `MM/DD/YYYY` dates. Validate that `cli.max_increase` is nonnegative, the amount-valid flag is true before submission, every `cli.checks` value is true before approval, and all `dispute.provisional_credit_checks` values are true before passing `eligible_for_provisional_credit: true` to the dispute tool. The illustrative command is schema-only; replace every value with current case data.
