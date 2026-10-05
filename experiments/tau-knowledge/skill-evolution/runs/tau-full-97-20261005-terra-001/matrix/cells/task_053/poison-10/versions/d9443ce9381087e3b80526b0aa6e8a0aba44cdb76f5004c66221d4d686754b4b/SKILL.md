---
name: credit-card-dispute-and-cli-processing
description: Process a verified customer's credit-card transaction dispute and credit-limit-increase (CLI) request using the documented bank workflows. Use for disputes requiring provisional-credit determination and for tier-based CLI prechecks, submission, review, approval, or denial.
---

# Credit Card Dispute and CLI Processing

Use this Skill when a customer asks to dispute a card transaction, request a CLI, or requests both. Treat these as separate bank actions, but account for the fact that a newly filed dispute may be an active/pending dispute that blocks a subsequent CLI.

## Safety and identity prerequisites

1. Match the customer, account, and transaction using supplied runtime lookup tools. Do not disclose account details merely because a name was supplied.
2. Before filing a dispute, submitting a CLI request, or changing an account, have the customer confirm at least **two of the four** identity fields: date of birth, email, phone number, and address. Use the account record only to compare their answers; do not prompt by revealing the stored values.
3. After two fields match, obtain the current timestamp and call `log_verification` with all fields required by that tool.
4. If identity is not verified, ask for the needed confirmations and do not perform bank actions.
5. Confirm the disputed transaction belongs to the selected account. Obtain missing dispute facts rather than guessing them.

## Optional deterministic assessment helper

`scripts/assess_credit_card_cases.py` calculates date, amount, tier, utilization, provisional-credit, and CLI-review facts. It does not contact banking tools and does not make changes.

Run it with JSON on stdin, for example:

```json
{
  "now": "2026-01-15",
  "account": {
    "tier": "mid-tier",
    "date_of_account_open": "2025-01-01",
    "credit_limit": "10000.00",
    "current_balance": "2500.00",
    "past_due_amount": "0.00"
  },
  "dispute": {
    "amount": "100.00",
    "reason": "goods_services_not_received",
    "purchase_date": "2025-12-01",
    "contacted_merchant": true,
    "dispute_records": []
  },
  "cli": {
    "requested_increase_amount": "2000.00",
    "last_approved_cli_submission_date": null,
    "pending_disputes": false,
    "pending_replacement_card": false,
    "consecutive_on_time_months": 3
  }
}
```

The output is a JSON object with `valid`, `errors`, `provisional_credit`, and/or `cli`. A decision of `undetermined` means required information is absent and must not be treated as a pass. Validate that dates, amounts, selected reasons, and tool results in the input match the live case before relying on the calculation.

## A. File the dispute

Collect and verify all required filing arguments:

- `transaction_id` for the matching completed transaction;
- `card_action`: exactly `keep_active` or `cancel_and_reissue`;
- the card's last four digits;
- full name, `user_id`, registered phone, email, and address;
- whether the customer contacted the merchant;
- purchase date and issue-noticed date in `MM/DD/YYYY`;
- one allowed `dispute_reason`;
- `resolution_requested` and, only for `partial_refund`, `partial_refund_amount`.

If the customer does not have the last four digits, retrieve them with `get_card_last_4_digits(credit_card_account_id)`. In a runtime where named internal tools are discoverable, unlock that named tool first and invoke it through `call_discoverable_agent_tool`; otherwise use the directly exposed tool. Do not ask for a full card number.

### Determine provisional credit

Use `get_user_dispute_history_7291(user_id)` to count disputes filed in the preceding 12 months. Determine account age from the account open date and current date. Provisional credit is `true` only when all of these hold:

- account age is at least 60 days;
- amount is at least $25 and does not exceed the applicable card-tier provisional-credit maximum;
- no more than two disputes were filed in the past 12 months;
- reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`;
- for `goods_services_not_received`, the purchase was more than 30 days ago;
- for every non-fraud reason, the customer contacted the merchant.

Do not infer an omitted merchant-contact answer, history, transaction amount, or date. A customer may file a dispute even when provisional credit is false; pass the determined boolean to the filing tool.

Unlock `file_credit_card_transaction_dispute_4829`, then call it through `call_discoverable_agent_tool` with a JSON string containing the required fields. For a full refund, omit `partial_refund_amount` unless the tool explicitly requires an optional null. Confirm that the filing returned successfully before representing the dispute as filed.

If a replacement is requested as part of a dispute, separately follow the replacement-card workflow and use `cancel_and_reissue`; otherwise use the customer's chosen `keep_active`. Do not order a replacement for a merchant dispute unless requested and eligible.

## B. Process the CLI

Use the tier associated with the selected account. Published CLI rules support entry-, mid-, and premium-tier accounts only. If the tier is not determinable or is outside the published CLI rules, do not invent limits or thresholds; explain that the request cannot be assessed under this workflow.

### 1. Amount precheck — before submission

Interpret a request for a new total limit as:

`requested increase = requested new limit - current credit limit`.

The maximum per request is 25% of the current limit for entry tier and 50% for mid and premium tier. Require a positive increase no greater than that maximum. If it exceeds the maximum, tell the customer the maximum permitted increase (and corresponding total limit), ask whether they want to adjust it, and **do not submit or deny a CLI request** yet.

### 2. Submit the valid request, then check every requirement

For a valid amount, call `submit_credit_limit_increase_request_7392` with the account ID, user ID, and integer dollar increase. This formal submission must occur before eligibility review.

After submission, check **all** of the following, even if one check already fails:

1. Account age from the account open date: entry 120 days, mid 90 days, premium 60 days.
2. Cooldown: call `get_credit_limit_increase_history_4829(credit_card_account_id)` and identify the most recent **approved** CLI submission. Denied requests do not trigger cooldown. Required completed cooldown: entry 120 days, mid 90 days, premium 60 days.
3. Pending disputes: inspect current dispute records. Any open, under-review, or otherwise unresolved dispute is pending. This includes a dispute successfully filed earlier in the same interaction when it remains unresolved.
4. Pending replacement cards: call `get_pending_replacement_orders_5765(credit_card_account_id)`. An empty response, or only delivered/cancelled orders, passes; any non-final order blocks the CLI.
5. Good standing: account must be current with no past-due balance.
6. Utilization: calculate `current_balance / credit_limit * 100`; it must be strictly below 70% entry, 80% mid, or 90% premium.
7. Payment history: call `get_payment_history_6183` using 6 months for entry tier and 3 months for mid or premium tier. Verify all required consecutive months are on time.

For named CLI tools that are discoverable in the runtime, unlock each tool before its first `call_discoverable_agent_tool` invocation. Preserve tool response evidence in case notes where supported.

### 3. Record the decision

- If every requirement passes, call `approve_credit_limit_increase_5847` with `new_credit_limit = current credit limit + requested increase`.
- If one or more requirements fail, call `deny_credit_limit_increase_5848` once using the matching allowed reason. If multiple checks fail, use the first applicable reason in this documented review order: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, `insufficient_payment_history`.
- `requested_amount_exceeds_limit` is appropriate only for a request that was actually submitted despite a valid workflow exception; normally the mandatory precheck means an excessive amount is never submitted.
- Missing, ambiguous, or failed read-only checks are not evidence of eligibility. Do not approve, deny for an invented reason, or claim completion; explain that the review remains incomplete and use the runtime's supported escalation path if necessary.

## Customer communication

After confirmed tool success, clearly state whether the dispute was filed, the selected card action, and whether provisional credit applies (describe it as temporary). For a CLI approval, state the new total limit. For a denial, state the actual reason and any date or action needed before reapplying. Never claim that a request, approval, denial, replacement, or provisional credit was completed if its tool call was not successful.
