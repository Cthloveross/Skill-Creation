---
name: credit-card-fraud-replacement-and-cli
summary: Process a verified credit-card customer's fraud dispute, replacement-card request, and credit-limit increase (CLI) request while applying provisional-credit, replacement, and CLI requirements in the required order.
---

# Credit-card fraud, replacement, and CLI workflow

Use this Skill when a customer requests one or more of: a credit-card transaction dispute (especially fraud), a replacement card, and a credit-limit increase. It is designed for cases where the requests affect one another: for example, a newly filed fraud dispute can be an active dispute that must be evaluated during a later CLI review.

## Required prerequisites

1. Locate the customer and the applicable credit-card account and transaction.
2. Complete standard identity verification by confirming at least two of the customer's four identity fields (date of birth, email, phone, address).
3. Call `log_verification` only after the two-field verification succeeds. Include all required identity data and a current timestamp from `get_current_time`.
4. Confirm that the transaction belongs to the identified account and that the requested replacement address is the confirmed customer address.

Do not expose internal eligibility checks or sensitive account information unnecessarily.

## Overall sequencing

For a compound fraud, replacement, and CLI request, complete the security-related work first, then process the CLI.

1. Verify identity and identify the correct account and disputed transaction.
2. Gather every mandatory dispute field and determine provisional-credit eligibility using dispute history.
3. Check replacement eligibility, then submit the replacement if eligible and requested.
4. File the dispute with `card_action: "cancel_and_reissue"` when a replacement was ordered or is to be issued as part of the fraud response.
5. Handle the CLI amount limit before submission. After the customer confirms a valid amount, submit the CLI request, then perform *all* required CLI checks before approving or denying it.

A replacement request cannot be submitted while a prior replacement is pending. A CLI review must check for active disputes after the CLI is submitted. Do not presume a newly filed dispute has resolved before that check.

## Fraud dispute workflow

### Gather and validate the required dispute payload

For a fraud dispute, confirm or retrieve all fields required by `file_credit_card_transaction_dispute_4829`:

- `transaction_id`
- `card_action`: use exactly `cancel_and_reissue` if the customer wants the card replaced or it was already ordered; otherwise use `keep_active`
- `card_last_4_digits`
- `full_name`
- `user_id`
- `phone`
- `email`
- `address`
- `contacted_merchant` (boolean)
- `purchase_date` in `MM/DD/YYYY`
- `issue_noticed_date` in `MM/DD/YYYY`
- `dispute_reason`: for fraud, exactly `unauthorized_fraudulent_charge`
- `resolution_requested`: for a complete refund, exactly `full_refund`
- `partial_refund_amount`: include only when `resolution_requested` is `partial_refund`
- `eligible_for_provisional_credit` (boolean)

For a customer who says the charge was unauthorized, do not require merchant contact: `contacted_merchant` may be `false`. Do not substitute descriptive text for the enumerated values.

### Determine provisional-credit eligibility

Before filing, call `get_user_dispute_history_7291` with the verified `user_id`. Determine eligibility only after checking all of these conditions:

- the account has been open at least 60 days;
- reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received` (the last only when purchase was more than 30 days ago);
- amount is at least $25.00 and does not exceed the tier maximum;
- no more than two disputes were filed in the preceding 12 months;
- for non-fraud reasons, the customer contacted the merchant.

Maximum provisional-credit amounts are: entry $2,500; mid $5,000; premium $10,000; elite $15,000; invitation $25,000. Gold Rewards is premium. Pass `false` when any criterion fails. If required history, dates, account age, amount, or tier data cannot be determined, obtain it before filing rather than guessing eligibility.

Unlock `file_credit_card_transaction_dispute_4829`, then call it through `call_discoverable_agent_tool` using a JSON string containing the complete payload.

## Replacement-card workflow

Before ordering, confirm identity, account, shipping address (including unit details), one replacement reason, shipping method, and any applicable expedited-fee consent. Valid reasons are exactly:

`fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`.

For an unauthorized transaction, record `fraud_suspected`. Check pending orders by calling `get_pending_replacement_orders_5765` with the credit-card account ID. Treat any non-final order (such as pending or shipped) as blocking a new order; delivered and cancelled are final. Do not order if a replacement is pending. Also confirm the tier's 60-day replacement limit from the available replacement history or records: entry 2, mid 3, premium-and-above 4.

For eligible requests, unlock and call `order_replacement_credit_card_7291` with:

- the credit-card account identifier;
- `reason`;
- `shipping_address`;
- `shipping_speed`: `standard` or `expedited`;
- `expedited_fee_acknowledgement`; and
- relevant `notes`.

Standard delivery is 7–10 business days and free. Expedited delivery is 2–3 business days; it costs $15 for entry tier, $10 for mid tier, and is complimentary for premium and above. For fraud or theft, strongly recommend expedited shipping and remind the customer to review and dispute unauthorized transactions. Explain that the old card is cancelled for security after a replacement order, a new card number and CVV are issued, and account number remains unchanged.

## CLI workflow

### 1. Validate the requested increase before submitting

Determine tier, current credit limit, requested *increase* (not new total), and maximum allowed amount:

- entry tier: 25% of current limit;
- mid tier: 50%;
- premium tier: 50%.

If the requested increase exceeds that maximum, tell the customer the maximum and request a corrected amount. **Do not submit a CLI request until the customer has confirmed a valid amount.** If the customer adjusts the amount, treat the confirmed adjusted amount as the request.

### 2. Submit, then audit all eligibility conditions

Once the amount is valid, submit `submit_credit_limit_increase_request_7392` with `credit_card_account_id`, `user_id`, and integer `requested_increase_amount`. Submission must occur before the CLI eligibility checks.

After submission, run and record every check, even if an earlier one fails:

1. Account age: entry at least 120 days, mid at least 90 days, premium at least 60 days.
2. Cooldown: call `get_credit_limit_increase_history_4829` with the account ID. The tier cooldown is 120/90/60 days. Under the tier eligibility guidance, only the latest approved request creates this cooldown; denied requests do not.
3. Active disputes: determine whether any dispute is active.
4. Pending replacement: call `get_pending_replacement_orders_5765`; any pending/non-final replacement blocks CLI processing.
5. Standing: account must be current with no past-due balance.
6. Utilization: calculate `current_balance / credit_limit * 100`. It must be strictly below 70% entry, 80% mid, or 90% premium.
7. Payment history: call `get_payment_history_6183` with the account ID and `months` equal to 6 for entry or 3 for mid/premium. Verify the required number of consecutive on-time months.

If every check passes, compute `new_credit_limit = current_credit_limit + requested_increase_amount`, then call `approve_credit_limit_increase_5847` with account ID, user ID, and the new total as `new_credit_limit`.

If any check fails, call `deny_credit_limit_increase_5848` with account ID, user ID, and the applicable allowed reason:

- `insufficient_account_age`
- `cooldown_period_active`
- `pending_disputes`
- `pending_replacement_card`
- `past_due_balance`
- `high_utilization`
- `insufficient_payment_history`
- `requested_amount_exceeds_limit`
- `other`

When multiple conditions fail, retain all audit findings; choose the most directly applicable allowed denial reason for the decision record. Never approve when a required check is unavailable or ambiguous; resolve the data issue or use `other` if a submitted request must be closed without a supported specific reason.

## Customer communication

State the dispute/replacement outcome, expected delivery window, and fraud-security reminder. For a CLI approval, confirm the new total limit. For a CLI denial, state the customer-facing reason and, where determinable, the relevant reapplication condition (for example, cooldown expiry, account-age date, lower utilization, delivery/cancellation of replacement, or payment-history completion). Do not claim that provisional credit is permanent; it is temporary while the dispute is investigated.

## Optional calculation helper

`scripts/assess_credit_card_requests.py` calculates the repeated date, amount, replacement, provisional-credit, and CLI threshold checks. It does not call banking tools, submit requests, or make decisions in the banking system.

It reads one JSON object from stdin and emits one JSON assessment to stdout. Supply only data retrieved during the live workflow; omit unknown data rather than inventing it. Date values may be `YYYY-MM-DD`, `MM/DD/YYYY`, or timestamps beginning with either date format.

Example:

```bash
python scripts/assess_credit_card_requests.py <<'JSON'
{
  "now": "2026-01-15",
  "dispute": {
    "account_open_date": "2024-01-01",
    "tier": "premium",
    "transaction_amount": 100.00,
    "reason": "unauthorized_fraudulent_charge",
    "purchase_date": "2026-01-10",
    "contacted_merchant": false,
    "dispute_dates": []
  },
  "replacement": {"tier": "premium", "pending_order": false, "orders_last_60_days": 0},
  "cli": {
    "tier": "premium",
    "current_limit": 5000,
    "requested_increase": 2500,
    "account_open_date": "2024-01-01",
    "latest_approved_cli_date": null,
    "utilization_percent": 10,
    "past_due_amount": 0,
    "active_disputes": 0,
    "pending_replacement": false,
    "consecutive_on_time_months": 3
  }
}
JSON
```

Validate that the helper output has `status: "eligible"` only when every named input for that evaluation was supplied and passed. Use the live tool results, not the helper, as the system of record.
