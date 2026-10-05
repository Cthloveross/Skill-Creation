---
name: credit-card-fraud-replacement-and-cli
version: 1.0.0
description: Process a verified credit-card customer's unauthorized-transaction dispute, fraud-related replacement-card request, and credit-limit-increase request. Use when the interaction needs coordinated dispute, replacement, and CLI eligibility decisions, especially where a pending fraud dispute may affect CLI eligibility.
---

# Credit Card Fraud, Replacement, and CLI Workflow

## Scope and assumptions

Use this Skill for a customer requesting one or more of:

1. A credit-card transaction dispute;
2. A replacement card, including a fraud-related replacement; and/or
3. A credit limit increase (CLI).

The executor performs banking actions using normal runtime tools. The included script only evaluates normalized runtime facts and proposes arguments; it never performs an account action. Do not treat a missing fact, an ambiguous tool response, or a script result as authorization to proceed.

The workflow requires successful identity verification before filing a dispute, ordering a replacement, submitting a CLI request, approving a CLI, or denying a submitted CLI request.

## Required runtime information

Obtain and normalize the following as applicable:

- Current timestamp and customer profile: full name, user ID, registered email, phone, address, and date of birth.
- Card account: account ID, card type, opened date, current balance, credit limit, past-due amount, and card last four digits.
- Disputed transaction: transaction ID, amount, transaction date, and merchant.
- Customer dispute answers: issue-noticed date, merchant-contact answer, allowed dispute reason, requested resolution, and any partial-refund amount.
- User dispute history, including dispute dates, for provisional-credit evaluation.
- Replacement request: exact confirmed shipping address, exact reason, selected speed, pending-order results, and replacement count in the prior 60 days if available.
- CLI request: requested increase amount; CLI request history including status and dates; payment-history result; and current results for disputes, replacement orders, standing, and utilization.

For date comparisons, use the current date from the runtime rather than the local machine clock.

## Identity and account discovery

1. Locate the user and the relevant card account using normal read-only tools.
2. Compare at least two customer-provided identity fields with the registered profile. Valid fields are date of birth, email, phone number, and address. Do not count a value that the customer did not actually provide.
3. Once two fields match, call `get_current_time`, then call `log_verification` with **all** required registered profile fields and that timestamp. Do not log a verification when comparison fails.
4. Confirm that the selected transaction belongs to the selected account and that the customer has confirmed the dispute facts.

If identity cannot be verified, stop all account-changing workflows and ask for another permitted verification field or transfer according to local policy.

## Dispute workflow

Complete the dispute before making a CLI decision because an open/pending dispute is a CLI eligibility condition.

1. Gather every required dispute argument:
   - `transaction_id`
   - `card_action`: `keep_active` or `cancel_and_reissue`
   - `card_last_4_digits`
   - `full_name`, `user_id`, `phone`, `email`, `address`
   - `contacted_merchant` boolean
   - `purchase_date` and `issue_noticed_date` in `MM/DD/YYYY`
   - one allowed `dispute_reason`
   - one allowed `resolution_requested`
   - `partial_refund_amount` only for `partial_refund`
   - `eligible_for_provisional_credit` boolean
2. Retrieve `get_user_dispute_history_7291` and calculate provisional-credit eligibility using the documented criteria. A fraud reason does not require merchant contact, but the other criteria still apply.
3. Unlock `file_credit_card_transaction_dispute_4829`, then call it through `call_discoverable_agent_tool` with a JSON string containing the complete argument set.
4. Inspect the result. Communicate that the dispute was filed only after a successful result.

For a customer who wants their compromised card replaced, use `cancel_and_reissue` for the dispute's `card_action`. This represents the requested cancellation/reissue. Before separately submitting a replacement order, check whether the dispute result has already created a replacement order; do not create a duplicate order.

## Replacement workflow

For a separate replacement order that is still needed:

1. Confirm the verified identity, account, exact shipping address, one reason from `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`, and `standard` or `expedited` shipping.
2. Obtain and inspect `get_pending_replacement_orders_5765`. Any order not clearly `delivered` or `cancelled` blocks a new order.
3. Confirm the tier's replacement-count rule for the last 60 days. Premium tier and above permit up to four replacements in that period. If history/count is unavailable, do not claim eligibility; obtain it or let the replacement tool's documented eligibility result govern.
4. For Gold/Premium tier, expedited replacement is complimentary and has a 2–3-business-day window. Standard delivery is free and takes 7–10 business days. For `fraud_suspected` or `stolen`, strongly recommend expedited shipping.
5. Unlock `order_replacement_credit_card_7291`, then call it through `call_discoverable_agent_tool`. Provide the account identifier, reason, confirmed `shipping_address`, `shipping_speed`, `expedited_fee_acknowledgement` (record consent when a fee applies), and relevant notes.
6. On success, explain that the old card is cancelled, give the selected delivery window, and advise the customer about shipment notifications and review of unauthorized activity.

Never order a second replacement while an earlier order is pending or shipped.

## CLI workflow

### Strict ordering

1. Determine the tier and calculate the maximum permitted increase **before submitting** a CLI request.
   - Entry tier: 25% of current limit.
   - Mid tier: 50%.
   - Premium tier: 50%.
2. If the requested increase is greater than the maximum, do **not** call the CLI submission tool. Tell the customer the maximum permitted increase and ask whether they want that lower amount. This is not a formal denial because no request was submitted.
3. Only after the customer confirms a valid positive amount, unlock and call `submit_credit_limit_increase_request_7392` with `credit_card_account_id`, `user_id`, and integer `requested_increase_amount`.
4. After successful submission, retrieve all required evidence even if an early criterion fails:
   - account age;
   - `get_credit_limit_increase_history_4829` for cooldown;
   - active/pending disputes;
   - `get_pending_replacement_orders_5765`;
   - good standing/no past-due balance;
   - utilization; and
   - `get_payment_history_6183` using the correct tier's required month count.
5. Requirements:
   - Entry: 120 days, 120-day cooldown, utilization below 70%, six consecutive on-time months.
   - Mid: 90 days, 90-day cooldown, utilization below 80%, three consecutive on-time months.
   - Premium: 60 days, 60-day cooldown, utilization below 90%, three consecutive on-time months.
   - Apply cooldown based on the latest **approved** prior request; denied requests do not trigger the tier cooldown.
6. If every requirement passes, unlock and call `approve_credit_limit_increase_5847` with the account ID, user ID, and `new_credit_limit = current_credit_limit + requested_increase_amount`.
7. If any post-submission requirement fails, unlock and call `deny_credit_limit_increase_5848` with the account ID, user ID, and the matching allowed reason:
   - account age → `insufficient_account_age`
   - cooldown → `cooldown_period_active`
   - active dispute → `pending_disputes`
   - pending replacement → `pending_replacement_card`
   - past due → `past_due_balance`
   - utilization → `high_utilization`
   - payment history → `insufficient_payment_history`
   - unsupported/unclassifiable condition → `other`

A CLI submitted after the fraud dispute is filed will normally fail the pending-disputes requirement while that dispute is active. Still complete every required post-submission check and record the applicable denial. Do not approve based solely on the evaluator output.

## Deterministic evaluator

`scripts/assess_credit_card_case.py` accepts one normalized JSON object on stdin and emits one JSON assessment on stdout. It validates the supplied values, calculates tier limits, dates, utilization, provisional-credit eligibility, replacement blocking, and a CLI recommendation.

Example invocation by the execution runtime:

```json
{
  "now": "2025-11-14 03:40:00 EST",
  "account": {
    "card_type": "Gold Rewards Card",
    "opened_date": "03/20/2023",
    "current_balance": 100.0,
    "credit_limit": 5000.0,
    "past_due_amount": 0
  },
  "dispute": {
    "amount": 100.0,
    "reason": "unauthorized_fraudulent_charge",
    "purchase_date": "11/01/2025",
    "contacted_merchant": false,
    "prior_dispute_dates": []
  },
  "replacement": {"pending_orders": [], "replacements_last_60_days": 0},
  "cli": {
    "requested_increase_amount": 1000,
    "approved_request_dates": [],
    "consecutive_on_time_months": 3,
    "has_pending_disputes": false
  }
}
```

Use only the assessment fields whose `missing` array is empty. Before an action, validate that IDs and customer-confirmed values are present and that each generated tool argument has the exact documented type and enum value. In particular, `requested_increase_amount` must be an integer, money must be positive where required, and dates passed to the dispute tool must be `MM/DD/YYYY`.

## Failure handling and communication

- If a required tool fails or returns ambiguous data, do not infer a passing condition. Retry or escalate under the applicable operating procedure.
- If a specialized tool is not directly present in the runtime, unlock the exact named tool first and call it through `call_discoverable_agent_tool` with a JSON-string `arguments` payload.
- Do not disclose internal eligibility logic beyond customer-appropriate next steps.
- Confirm completed actions only from successful tool results. State separate outcomes for the dispute, replacement, and CLI request.
