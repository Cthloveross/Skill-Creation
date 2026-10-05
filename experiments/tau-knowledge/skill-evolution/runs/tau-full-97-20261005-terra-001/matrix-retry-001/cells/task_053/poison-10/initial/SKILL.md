---
name: credit-card-dispute-and-cli
version: 1.0.0
description: Process a verified cardholder's credit-card transaction dispute and credit-limit-increase (CLI) request in one interaction. Use for disputes requiring provisional-credit assessment and for tier-based CLI submission, eligibility review, approval, or denial.
---

# Credit Card Dispute and CLI Processing

Use this Skill when a customer asks to dispute a card transaction, request a CLI, or both. Treat the two workflows as separate operations sharing identity, account, and card context. Never hardcode account IDs, transaction IDs, card digits, customer details, dates, or decision outcomes from a prior case.

## Safety and identity gate

1. Identify the customer and select the relevant credit-card account only after matching the requested card product and transaction details to returned account/transaction data.
2. Before revealing account/card information or making either requested change, have the customer explicitly confirm **two of four** profile fields: date of birth, email, phone number, or address. A value merely retrieved from a system is not a customer confirmation.
3. Retrieve the current timestamp and call `log_verification` with the complete profile values and timestamp after two fields match. Do not call it before verification succeeds.
4. If identity cannot be verified, do not retrieve card digits, file a dispute, or submit/process a CLI. Explain that verification is required and ask for the needed confirmations.

Use the normal supplied account, customer, and transaction lookup tools to obtain the live data needed below. If a required record is ambiguous, missing, malformed, or a required internal tool is unavailable, do not guess or fabricate a result. Resolve the ambiguity or escalate through the available support procedure.

## Required discoverable-tool calling pattern

For each specialized internal tool named below, first call `unlock_discoverable_agent_tool` with the exact tool name, then call it through `call_discoverable_agent_tool` with `agent_tool_name` set to that exact name and `arguments` set to a JSON string. Use only documented arguments. Tool calls are actions only when the executor actually performs them.

## A. File the transaction dispute

### Gather and validate the filing record

After identity verification:

1. Match the disputed transaction to the selected account using the merchant, amount, date, and completed transaction status. Capture its `transaction_id`.
2. Retrieve the card's last four digits by unlocking and calling `get_card_last_4_digits` with `credit_card_account_id`. This is the alternate internal retrieval path when an authenticated customer cannot access their app or website; do not request a full card number.
3. Retrieve the cardholder's registered name, phone, email, and address from the verified profile.
4. Obtain/confirm all customer-supplied dispute fields:
   - `card_action`: exactly `keep_active` or `cancel_and_reissue`.
   - whether the customer contacted the merchant.
   - purchase date and issue-noticed date, formatted `MM/DD/YYYY`.
   - `dispute_reason`, exactly one of:
     `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, `refund_never_processed`.
   - `resolution_requested`, exactly one of `full_refund`, `partial_refund`, `reversal_of_charge`.
   - `partial_refund_amount` only when the resolution is `partial_refund`. Do not provide it for the other resolutions.
5. Do not reinterpret a merchant/service issue as fraud. For a non-fraud case, record `contacted_merchant` as true only when the customer says they attempted contact or plainly reports such an attempt.

### Determine provisional-credit eligibility

Unlock and call `get_user_dispute_history_7291` with the verified `user_id`. Determine the account age, card tier, transaction amount, dispute reason, merchant-contact result, purchase age, and count of disputes filed in the preceding 12 months. A customer is eligible only if **all** are true:

- Account age is at least 60 days.
- Reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`; the last category additionally requires the purchase to be more than 30 days old.
- Amount is at least $25 and no greater than the tier maximum: entry $2,500; mid $5,000; premium $10,000; elite $15,000; invitation $25,000.
- The customer has filed no more than two disputes in the past 12 months.
- For every non-fraud reason, the customer contacted the merchant.

Use `scripts/evaluate_eligibility.py` with `operation: "provisional"` to make the threshold and date comparisons reproducible. The script does not retrieve data and does not file a dispute.

### Submit and communicate

Unlock and call `file_credit_card_transaction_dispute_4829` with all required fields:

- `transaction_id`, `card_action`, `card_last_4_digits`, `full_name`, `user_id`, `phone`, `email`, `address`
- `contacted_merchant`, `purchase_date`, `issue_noticed_date`, `dispute_reason`, `resolution_requested`
- `eligible_for_provisional_credit`
- `partial_refund_amount` only if applicable

Then tell the customer that the dispute was filed, whether provisional credit applies, and that it is temporary pending investigation when applicable. If `cancel_and_reissue` was selected, separately follow the replacement-card workflow; do not claim a replacement was ordered merely because the dispute was filed.

## B. Process the credit-limit increase

### Establish the requested amount before submission

Determine the current credit limit and the customer’s requested **whole-dollar increase**. If the customer gives an unambiguous target total, calculate `requested_increase = target_total - current_limit`; otherwise request an exact target or increase. A decrease, zero increase, fractional-dollar request, or unclear “about” amount must be clarified before proceeding.

Classify the actual card tier. CLI tiers and limits are:

| Tier | Minimum account age | Cooldown | Utilization must be below | On-time months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | 70% | 6 | 25% of current limit |
| Mid-tier | 90 days | 90 days | 80% | 3 | 50% of current limit |
| Premium-tier | 60 days | 60 days | 90% | 3 | 50% of current limit |

Calculate the maximum increase from the live current limit. If the requested increase exceeds it, **do not submit a CLI request**. Tell the customer the maximum and obtain an explicit confirmation of a revised valid amount before continuing. The CLI evaluator script can calculate this maximum and validate strict utilization boundaries.

### Submission and complete review order

For a confirmed amount within the tier maximum:

1. Unlock and call `submit_credit_limit_increase_request_7392` with `credit_card_account_id`, `user_id`, and integer `requested_increase_amount`. Formal submission occurs before eligibility review.
2. Perform every check below even if an earlier check fails, so the record is complete:
   - Account age against the applicable threshold.
   - Unlock and call `get_credit_limit_increase_history_4829` with `credit_card_account_id`. Only a prior **approved** request triggers a cooldown; a denied request does not. Evaluate elapsed full days from the most recent approved request submission and calculate the next eligible date when blocked.
   - No active/pending disputes. Review returned dispute history/status data and any supplied account-dispute status source; open or under-review disputes are not clear.
   - Unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id`. Any order not clearly `delivered` or `cancelled` blocks the CLI.
   - Good standing: account is current and has no past-due balance.
   - Current utilization is strictly below the tier threshold: `current_balance / current_credit_limit * 100`. Equality to the threshold fails.
   - Unlock and call `get_payment_history_6183` with `credit_card_account_id` and the tier-required `months`. Verify every one of those consecutive months was on time.
3. Use `scripts/evaluate_eligibility.py` with `operation: "cli"` to calculate age, utilization, maximum amount, cooldown, and a transparent decision summary. Pass actual check results; do not turn missing evidence into a passing result.
4. If all checks pass, unlock and call `approve_credit_limit_increase_5847` with `credit_card_account_id`, `user_id`, and numeric `new_credit_limit = current_limit + requested_increase`.
5. If one or more checks fail, unlock and call `deny_credit_limit_increase_5848` with the account ID, user ID, and the applicable allowed reason: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, `insufficient_payment_history`, `requested_amount_exceeds_limit`, or `other`.

If a post-submission check cannot be completed because data or a required supported tool is unavailable, do not approve or make up a denial basis. Report that the eligibility review is incomplete and follow the supported escalation/process for unresolved internal checks.

Communicate the recorded result plainly: for approval, state the new total limit; for denial, state the actual reason and, where calculable, the action/date needed before another request. Do not expose internal-only eligibility logic beyond the customer-appropriate reason and next steps.

## Eligibility helper

Run the packaged helper through the supplied script runtime. It reads one JSON object from stdin and emits one JSON object to stdout.

### CLI input schema

```json
{
  "operation": "cli",
  "tier": "mid-tier",
  "current_limit": "<decimal currency>",
  "current_balance": "<decimal currency>",
  "requested_increase": "<whole dollar amount>",
  "account_open_date": "<YYYY-MM-DD or timestamp>",
  "now": "<YYYY-MM-DD or timestamp>",
  "approved_request_times": ["<date/timestamp>"] ,
  "external_checks": {
    "pending_disputes_clear": true,
    "no_pending_replacement": true,
    "good_standing": true,
    "payment_history_sufficient": true
  }
}
```

`approved_request_times` must contain only approved prior submissions. Each external check may be `true`, `false`, or `null` if not yet verified. The response includes `pre_submission_action`, computed amounts/percentages, individual check states, any selected denial reason, and a `decision` of `approve`, `deny`, `await_required_check`, or `do_not_submit`.

### Provisional-credit input schema

```json
{
  "operation": "provisional",
  "tier": "mid-tier",
  "account_open_date": "<YYYY-MM-DD or timestamp>",
  "now": "<YYYY-MM-DD or timestamp>",
  "purchase_date": "<YYYY-MM-DD or MM/DD/YYYY>",
  "amount": "<decimal currency>",
  "dispute_reason": "<allowed reason>",
  "contacted_merchant": true,
  "disputes_last_12_months": 0
}
```

The response contains `eligible`, `criteria`, and any validation errors. An input error or unknown merchant-contact value is not eligibility evidence and must be resolved before filing.
