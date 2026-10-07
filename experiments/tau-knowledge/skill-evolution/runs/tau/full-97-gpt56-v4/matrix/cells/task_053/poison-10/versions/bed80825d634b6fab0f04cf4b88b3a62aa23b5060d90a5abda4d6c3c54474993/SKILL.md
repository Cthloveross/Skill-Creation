---
name: credit-card-dispute-and-cli-workflow
description: Process a credit-card transaction dispute and a credit-limit-increase (CLI) request for the same customer, including identity verification, discovered-tool use, provisional-credit determination, and the required CLI submission and decision sequence.
---

# Credit-card dispute and CLI workflow

Use this Skill when a customer asks to dispute a card transaction, request a CLI, or requests both. Treat live tool results and the customer's confirmed statements as the source of case data; never infer missing identifiers, dates, contact status, or requested resolution.

## Preconditions and customer verification

1. Identify the customer with a read-only lookup (name, email, or user ID), then retrieve their card accounts and transaction history.
2. Before any state-changing action, obtain confirmation of **two of** the following account identity fields: date of birth, email, registered phone number, or registered address. A name does not count as one of these fields.
3. Get the current time and call `log_verification` only after two fields are confirmed. Supply every field required by that tool from the verified user record and the current timestamp.
4. Match the described transaction to the correct account, merchant, amount, and transaction date. If matching is ambiguous, ask the customer before proceeding.

Do not expose full card numbers. Last four digits may be retrieved internally as described below.

## Dispute procedure

### Gather and normalize the required case data

Obtain all required dispute inputs:

- `transaction_id`, account ID, card type, amount, and purchase date from the matched transaction;
- customer `full_name`, `user_id`, registered `phone`, `email`, and `address` from the verified record;
- whether the customer contacted the merchant (`contacted_merchant`);
- `issue_noticed_date` in `MM/DD/YYYY` format;
- one permitted `dispute_reason`:
  `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, or `refund_never_processed`;
- one permitted `resolution_requested`: `full_refund`, `partial_refund`, or `reversal_of_charge`; and a positive numeric `partial_refund_amount` only when partial refund is selected;
- card last four digits.

If the customer cannot access card details, unlock `get_card_last_4_digits`, then call it through `call_discoverable_agent_tool` with the matched `credit_card_account_id`. Use its result only for the selected account. Do not ask the customer to sign in when this available internal lookup can supply the required last four digits.

### Determine provisional credit

Before filing, unlock and call `get_user_dispute_history_7291` with the verified `user_id`. Count disputes filed during the 12 months before the current time. A customer is eligible only when **all** are true:

1. the account has been open at least 60 days;
2. the reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`;
3. for goods/services not received, the purchase was more than 30 days before the current date;
4. amount is at least $25 and no more than the tier cap;
5. no more than two disputes were filed during the preceding 12 months; and
6. for every non-fraud reason, the customer contacted the merchant first.

Tier caps are: Entry $2,500; Mid $5,000; Premium $10,000; Elite $15,000; Invitation $25,000. Silver Rewards is Mid tier. Set `eligible_for_provisional_credit` to the resulting boolean; do not promise a permanent outcome.

Use `scripts/evaluate_case.py` to validate dates, reason/resolution combinations, tier mapping, and the deterministic provisional-credit result when data has been assembled.

### File the dispute

Unlock `file_credit_card_transaction_dispute_4829`, then call it with a JSON string containing every required field:

```json
{
  "transaction_id": "<matched transaction ID>",
  "card_action": "keep_active",
  "card_last_4_digits": "<four digits from lookup>",
  "full_name": "<verified full name>",
  "user_id": "<verified user ID>",
  "phone": "<registered phone>",
  "email": "<registered email>",
  "address": "<registered address>",
  "contacted_merchant": true,
  "purchase_date": "MM/DD/YYYY",
  "issue_noticed_date": "MM/DD/YYYY",
  "dispute_reason": "<permitted value>",
  "resolution_requested": "full_refund",
  "eligible_for_provisional_credit": false
}
```

Use `card_action: keep_active` unless the customer wants the card replaced or cancellation/reissue is part of the dispute; then use `cancel_and_reissue`. Include `partial_refund_amount` only for `partial_refund`. Report that the dispute was filed and whether temporary provisional credit is eligible; explain that eligibility is temporary pending investigation.

## CLI procedure

Process a CLI only after verification. If both requests are being handled, finish filing the dispute first; the freshly filed dispute must be considered in the CLI active-dispute check.

1. Determine tier from the card type and calculate the increase as requested new total limit minus the current limit. Reject nonpositive increases.
2. **Before submission**, verify the requested increase does not exceed the per-request cap: Entry 25% of current limit; Mid and Premium 50%. If it exceeds the cap, tell the customer the maximum increase and obtain a revised amount. Do not submit an excessive request.
3. Once the amount is valid and confirmed, unlock and call `submit_credit_limit_increase_request_7392` with `credit_card_account_id`, `user_id`, and integer `requested_increase_amount`. Submission is required before internal eligibility checks.
4. Perform and record every check after submission:
   - account age (Entry 120 days, Mid 90, Premium 60);
   - unlock/call `get_credit_limit_increase_history_4829` for the account; an approved prior request within the tier cooldown blocks the request (Entry 120, Mid 90, Premium 60 days);
   - active disputes, including the just-filed dispute, using the dispute-history lookup;
   - unlock/call `get_pending_replacement_orders_5765`; any pending or shipped order blocks processing;
   - account standing: past-due balance must be zero/current;
   - utilization strictly below tier threshold (Entry 70%, Mid 80%, Premium 90%);
   - unlock/call `get_payment_history_6183` with account ID and required months (Entry 6, Mid 3, Premium 3); require consecutive on-time history.
5. If every criterion passes, unlock/call `approve_credit_limit_increase_5847` using the account ID, user ID, and requested **new total** credit limit.
6. Otherwise unlock/call `deny_credit_limit_increase_5848` using the account ID, user ID, and the first applicable documented reason: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, `insufficient_payment_history`, `requested_amount_exceeds_limit`, or `other`.

Do not approve based only on an initial account lookup. Communicate the actual approval/denial only after the corresponding decision tool reports success.

## Runtime helper

`scripts/evaluate_case.py` accepts JSON on stdin and emits JSON on stdout. It performs no bank actions. It validates a normalized dispute and/or CLI calculation and returns errors plus eligibility/check results. Example:

```bash
python3 scripts/evaluate_case.py <<'JSON'
{"current_date":"2025-01-31","dispute":{"account_open_date":"2024-01-01","card_type":"Silver Rewards Card","amount":125,"purchase_date":"2024-12-01","reason":"goods_services_not_received","contacted_merchant":true,"prior_disputes_12m":0},"cli":{"card_type":"Silver Rewards Card","current_limit":1000,"requested_new_limit":1500}}
JSON
```

A usable result has `errors: []`. `dispute.provisional_credit_eligible` is a deterministic guideline result; it is not a substitute for the required live history and account checks. `cli.request_within_cap` must be true before submitting a CLI request.

## Failure handling

If a required value remains unconfirmed, an account/transaction cannot be uniquely matched, a discovered tool fails, or a required eligibility lookup is ambiguous, do not fabricate a value or repeat an action with unknown outcome. Explain what is missing and request it, or use the appropriate available human-transfer route when the case cannot be safely completed.
