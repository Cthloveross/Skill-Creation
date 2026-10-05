---
name: credit-card-dispute-and-cli
version: 1.1.0
description: Process a verified cardholder's credit-card transaction dispute and/or tier-based credit-limit-increase (CLI) request. Use when either request, including both requests in one interaction, needs internal-tool actions and an auditable decision.
---

# Credit Card Dispute and CLI Processing

Use this Skill for a card dispute, a credit-limit increase (CLI), or both. Treat each as an independent workflow. A failure, unavailable dependency, or human escalation for a dispute **does not stop a separately actionable CLI workflow**. Complete and record every requested workflow that can proceed safely before transferring the customer.

Never hardcode a customer, account, transaction, date, card digits, or outcome. Obtain live values from the supplied account and customer records.

## Identity and record selection

1. Locate the customer and relevant card account using supplied lookup tools. Match the card product and, for a dispute, the merchant, amount, date, and transaction status.
2. Before disclosing protected card/account information or submitting either banking request, have the customer confirm at least two profile fields from date of birth, email, phone, and address. Retrieved values alone are not confirmations.
3. Retrieve the current timestamp and call `log_verification` only after successful confirmation, with the complete profile and timestamp.
4. If verification fails, do not retrieve card digits, file a dispute, submit a CLI, or approve/deny one. Ask for the needed confirmations.
5. If a required record is missing, ambiguous, malformed, or a required tool is unavailable, do not invent data or an outcome. Handle the unaffected workflow independently and escalate only the blocked work with a precise summary.

## Calling specialized agent tools

For every specialized tool documented below, first invoke `unlock_discoverable_agent_tool` with `agent_tool_name` set to the exact tool name. Then invoke `call_discoverable_agent_tool` with that same `agent_tool_name` and `arguments` as a JSON-encoded object. Perform the actual banking action through the normal execution tools; this Skill's helper does not perform banking actions.

## A. Transaction-dispute workflow

### Gather the filing record

After verification:

1. Select the matching completed transaction and retain its `transaction_id`.
2. Unlock and call `get_card_last_4_digits` with `{"credit_card_account_id": "..."}`. This is the internal alternate retrieval method when the authenticated customer cannot access the app or website. Never ask for or expose a full card number.
3. Use the verified profile for full name, user ID, phone, email, and address.
4. Obtain and validate all filing values:
   - `card_action`: `keep_active` or `cancel_and_reissue`.
   - `contacted_merchant`: true only if the customer says they tried the merchant or plainly reports doing so.
   - purchase and issue-noticed dates in `MM/DD/YYYY` form.
   - `dispute_reason`: one of `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, or `refund_never_processed`.
   - `resolution_requested`: `full_refund`, `partial_refund`, or `reversal_of_charge`.
   - `partial_refund_amount` only for `partial_refund`.

Do not relabel a merchant fulfillment problem as fraud.

### Determine provisional-credit eligibility

Unlock and call `get_user_dispute_history_7291` with `{"user_id": "..."}`. Count disputes in the preceding 12 months and assess eligibility from live records. Provisional credit requires all of the following:

- account open at least 60 days;
- an eligible reason (`unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`); goods-not-received also requires purchase more than 30 days ago;
- amount at least $25 and no higher than the tier maximum: entry $2,500, mid $5,000, premium $10,000, elite $15,000, invitation $25,000;
- no more than two disputes in the past 12 months; and
- merchant contact for every non-fraud dispute.

Use `scripts/evaluate_eligibility.py` with `operation: "provisional"` for repeatable date and threshold calculations. Resolve invalid or missing values before filing.

### File or escalate the dispute

When all required values are available, unlock and call `file_credit_card_transaction_dispute_4829` with:

- `transaction_id`, `card_action`, `card_last_4_digits`, `full_name`, `user_id`, `phone`, `email`, `address`;
- `contacted_merchant`, `purchase_date`, `issue_noticed_date`, `dispute_reason`, `resolution_requested`, `eligible_for_provisional_credit`; and
- `partial_refund_amount` only where applicable.

Tell the customer the filing status and whether provisional credit applies. If `cancel_and_reissue` is selected, follow the separate replacement-card procedure; filing a dispute alone does not order a replacement.

If the required last-four retrieval tool or other indispensable dispute dependency is genuinely unavailable, do not fabricate the digit or file an incomplete dispute. Escalate the dispute as a technical/system issue, but first continue with any independently valid CLI request below.

## B. Credit-limit-increase workflow

### Establish a valid request before submitting it

Determine the current limit and convert a requested target total into an increase:

`requested_increase = requested_target_limit - current_credit_limit`

An unclear approximate total, non-positive increase, or fractional-dollar increase must be clarified. Classify the actual card tier and apply these rules:

| Tier | Minimum age | Cooldown | Utilization must be below | On-time months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | 70% | 6 | 25% of current limit |
| Mid-tier | 90 days | 90 days | 80% | 3 | 50% of current limit |
| Premium-tier | 60 days | 60 days | 90% | 3 | 50% of current limit |

If the requested increase exceeds the tier maximum, do not submit it. Explain the maximum and obtain explicit confirmation of a revised valid increase. A request at exactly the documented maximum is valid.

### Mandatory submission, then complete review

For a confirmed valid amount, follow this exact order:

1. Unlock and call `submit_credit_limit_increase_request_7392` with `credit_card_account_id`, `user_id`, and integer `requested_increase_amount`. This submission must occur **before** internal eligibility checks.
2. After submission, complete every check below, even if an earlier one fails:
   - Calculate account age from its open date.
   - Unlock and call `get_credit_limit_increase_history_4829` with the account ID. Only an approved prior request activates the applicable cooldown; calculate elapsed full days and the next eligible date if blocked.
   - Unlock and call `get_user_dispute_history_7291` with the user ID and verify no active or pending dispute exists for the account.
   - Unlock and call `get_pending_replacement_orders_5765` with the account ID. Any order not clearly delivered or cancelled is pending and blocks the CLI.
   - Verify good standing: current account status and no past-due balance.
   - Calculate utilization as `current_balance / current_credit_limit * 100`; equality with the threshold fails.
   - Unlock and call `get_payment_history_6183` with the account ID and the required number of months for the tier. Verify all required consecutive months are on time.
3. Run `scripts/evaluate_eligibility.py` with `operation: "cli"`, the live account facts, approved-request dates, and results of all external checks. The helper makes calculations reproducible but does not replace the required tool checks.
4. If every check passes, unlock and call `approve_credit_limit_increase_5847` with `credit_card_account_id`, `user_id`, and numeric `new_credit_limit` equal to current limit plus requested increase.
5. If a checked requirement fails, unlock and call `deny_credit_limit_increase_5848` with the account ID, user ID, and the matching documented reason: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, `insufficient_payment_history`, `requested_amount_exceeds_limit`, or `other`.

If a post-submission requirement cannot be checked because a required supported tool or data is unavailable, do not approve and do not invent a denial reason. State that the review is incomplete and escalate that unresolved internal review. This is distinct from a denial based on an actual failed requirement.

Communicate the recorded decision: an approval must state the new total limit; a denial must give the customer-appropriate reason and, where calculable, when or how to reapply. If a dispute transfer is necessary, include the completed CLI result in the handoff summary.

## Eligibility helper

The packaged helper reads one JSON object from stdin and emits one JSON object to stdout. It accepts only supplied runtime data and has no banking side effects.

### CLI input

```json
{
  "operation": "cli",
  "tier": "mid-tier",
  "current_limit": "15000.00",
  "current_balance": "4500.00",
  "requested_increase": 7500,
  "account_open_date": "YYYY-MM-DD",
  "now": "YYYY-MM-DD",
  "approved_request_times": ["YYYY-MM-DD"],
  "external_checks": {
    "pending_disputes_clear": true,
    "no_pending_replacement": true,
    "good_standing": true,
    "payment_history_sufficient": true
  }
}
```

The response includes calculated maximum increase, total proposed limit, age, utilization, individual check states, a decision (`approve`, `deny`, `await_required_check`, or `do_not_submit`), and any policy-coded denial reason. External checks can be `true`, `false`, or `null`; null means unverified and cannot support approval.

### Provisional-credit input

```json
{
  "operation": "provisional",
  "tier": "mid",
  "account_open_date": "YYYY-MM-DD",
  "now": "YYYY-MM-DD",
  "purchase_date": "MM/DD/YYYY",
  "amount": "1247.99",
  "dispute_reason": "goods_services_not_received",
  "contacted_merchant": true,
  "disputes_last_12_months": 0
}
```

The result provides `eligible`, individual criteria, computed ages, and validation errors. Do not treat validation errors as an eligibility decision.
