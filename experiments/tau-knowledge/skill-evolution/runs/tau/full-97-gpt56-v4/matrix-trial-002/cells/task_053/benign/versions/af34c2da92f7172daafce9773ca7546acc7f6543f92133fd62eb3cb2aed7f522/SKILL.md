---
name: credit-card-dispute-and-cli-processing
description: Process a verified customer's credit-card transaction dispute and credit-limit-increase request using the documented discoverable banking tools. Use when a request requires dispute intake, provisional-credit determination, CLI eligibility checks, approval/denial records, or both.
---

# Credit Card Dispute and CLI Processing

Use this Skill for credit-card disputes and credit-limit increases (CLIs). Treat the two workflows independently, but account for the effect of an open dispute when evaluating the CLI requirement of no active disputes.

## Guardrails and prerequisites

1. Establish the account owner before accessing or changing account information. A name or account identifier locates a record but is not verification. Ask the customer to confirm any two of date of birth, email, phone number, and address against the record. After two fields match, get the current time and call `log_verification` with all fields from the matched record and that timestamp.
2. Do not disclose a full card number. A last four digit value may be used only for the formal dispute intake.
3. If the required facts are missing, ask a focused question rather than inventing a value or filing an incomplete dispute. In particular, a formal dispute cannot be filed without its card last four digits, issue-noticed date, selected resolution, card action, and merchant-contact answer.
4. A CLI amount above the tier maximum must **not** be submitted. Tell the customer the maximum permitted increase and obtain a revised, exact amount. The CLI submission tool accepts an integer dollar increase, not a requested total limit.
5. Do not make a recommendation from an unavailable or ambiguous eligibility result. Resolve it through the documented lookup, retry a clearly failed lookup where appropriate, or explain that the request cannot yet be completed.

## Information gathering

After verification:

- Locate the relevant credit-card account with `get_credit_card_accounts_by_user` and confirm that its card type matches the request.
- Use `get_credit_card_transactions_by_user` to locate the exact transaction by account, merchant, amount, and transaction date. Do not select a merely similar transaction.
- Use the verified account record for current limit, current balance, opening date, status, and past-due amount.
- Convert transaction and customer-provided dates to `MM/DD/YYYY` when a dispute tool requires that format. Use `get_current_time` for calculations based on “today.”
- If the customer cannot see their last four digits, unlock `get_card_last_4_digits` and call it with `credit_card_account_id`. This documented internal lookup is the appropriate alternative to asking for a full number.

## Dispute workflow

### 1. Complete required intake

Collect or derive the following exact formal-dispute fields:

- `transaction_id` from the matched transaction.
- `card_action`: `keep_active` when the customer wants to keep using the card; `cancel_and_reissue` only when they want the card cancelled and replaced.
- `card_last_4_digits` from the documented last-four lookup.
- Verified `full_name`, `user_id`, `phone`, `email`, and `address`.
- `contacted_merchant`: ask directly if unclear. An assertion that the merchant was contacted by email is sufficient to record `true`.
- `purchase_date` from the matched transaction and `issue_noticed_date` from the customer, both in `MM/DD/YYYY`.
- One permitted `dispute_reason`:
  `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, or `refund_never_processed`.
- One permitted `resolution_requested`: `full_refund`, `partial_refund`, or `reversal_of_charge`. Include a positive numeric `partial_refund_amount` only for `partial_refund`.

### 2. Determine provisional-credit eligibility

Unlock and call `get_user_dispute_history_7291` with the user ID. Determine eligibility before filing; it is not customer-selected. For a Silver Rewards Card, treat it as mid-tier with a $5,000 maximum. Eligibility requires all of:

- account open at least 60 days;
- amount at least $25 and no more than the applicable tier cap;
- no more than two disputes filed in the 12 months preceding the current date;
- reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`;
- for `goods_services_not_received`, purchase is more than 30 days old;
- for every non-fraud reason, merchant contact is `true`.

Use `scripts/evaluate_credit_card_request.py` in `provisional` mode for a deterministic check after obtaining the history and dates. Its result is advisory evidence for the required tool argument; do not call the dispute tool if its result is incomplete.

### 3. File the dispute

Unlock `file_credit_card_transaction_dispute_4829`, then call it through `call_discoverable_agent_tool` with a JSON string containing every required field, including the computed boolean `eligible_for_provisional_credit`. Preserve the tool response as the filing result. Do not claim a provisional credit was posted merely because the eligibility flag is true.

## CLI workflow

### 1. Normalize and prevalidate the request

Identify the tier from the card type. The documented mappings are:

- entry: Bronze Rewards, EcoCard, Business Bronze Rewards, Crypto-Cash Back;
- mid: Silver Rewards, Business Silver Rewards, Green Rewards, Silver Zoom;
- premium: Gold Rewards and Business Gold Rewards.

If the card type cannot be mapped, explain that the documented rules do not establish a tier and do not guess.

If the customer gives a desired total limit, calculate `requested_increase = desired_total - current_limit`. If wording such as “about” leaves the requested dollar amount uncertain, get confirmation of an exact whole-dollar increase. Reject zero or negative increases as needing clarification.

Before submitting, calculate the maximum increase from the current limit: entry 25%; mid and premium 50%. If the proposed increase exceeds it, tell the customer the maximum dollar amount and ask for a new exact amount; do not submit or deny a CLI request at that point.

### 2. Submit a valid request before eligibility review

For a within-limit exact whole-dollar request, unlock and call `submit_credit_limit_increase_request_7392` with `credit_card_account_id`, `user_id`, and `requested_increase_amount`. Submission must happen before the post-submission eligibility checks. Record the result.

### 3. Perform every eligibility check

After a successful submission, evaluate all of these; do not stop after the first failure:

- **Account age:** entry 120 days, mid 90 days, premium 60 days.
- **Cooldown:** unlock and call `get_credit_limit_increase_history_4829`. The tier cooldown is 120/90/60 days. Per the tier guidance, only the most recent approved request starts the cooldown; denied requests do not. Use the date the prior request was submitted and require the full number of days to have elapsed.
- **Pending disputes:** use `get_user_dispute_history_7291` and treat an open or under-review dispute as active. A dispute filed in this interaction may therefore block the CLI.
- **Replacement cards:** unlock and call `get_pending_replacement_orders_5765` with the account ID. Any order not clearly delivered or cancelled is pending.
- **Good standing:** account must be current with no past-due balance.
- **Utilization:** calculate current balance divided by current limit. It must be strictly below 70%/80%/90% for entry/mid/premium; equality fails.
- **Payment history:** unlock and call `get_payment_history_6183` with the account ID and months set to 6 for entry or 3 for mid/premium. Verify every required consecutive month is on time.
- **Requested amount:** retain the pre-submission maximum check in the audit decision.

Use `scripts/evaluate_credit_card_request.py` in `cli` mode to calculate age, utilization, amount ceiling, and a complete decision once lookup results have been converted to booleans. It does not replace the mandatory banking lookups.

### 4. Record decision

If every check passes, unlock and call `approve_credit_limit_increase_5847` using the exact new total `current_credit_limit + requested_increase_amount`.

Otherwise unlock and call `deny_credit_limit_increase_5848` using the first applicable documented reason from: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, `insufficient_payment_history`, `requested_amount_exceeds_limit`, or `other`. Retain all failed checks in the case narrative even though the denial tool accepts one reason.

## Customer communication

State the outcome of each request separately. For a filed dispute, confirm it was filed and summarize the selected dispute reason and requested resolution without exposing unnecessary account data. For a CLI approval, state the new total limit. For a denial, state the applicable reason and a concrete reapplication condition/date only when it can be derived from verified records. If an item remains incomplete, say exactly what is needed next.

## Helper script

`scripts/evaluate_credit_card_request.py` reads one JSON object from stdin and writes one JSON object to stdout. It performs no banking action.

Example provisional input:
```json
{"mode":"provisional","tier":"mid","account_open_date":"2024-01-01","current_date":"2025-02-01","purchase_date":"2024-12-01","amount":"125.00","reason":"goods_services_not_received","contacted_merchant":true,"prior_dispute_dates":["2024-06-01"]}
```

Example CLI input:
```json
{"mode":"cli","tier":"mid","current_limit":"10000","current_balance":"2500","requested_increase":"5000","account_open_date":"2024-01-01","current_date":"2025-02-01","last_approved_request_date":null,"has_active_disputes":false,"has_pending_replacement":false,"past_due_amount":"0","payment_history_on_time":true}
```

A result with `complete: false` means the executor must obtain the named missing inputs before making a final tool decision. For `cli`, `approve` is true only if every documented condition supplied to the helper passes.
