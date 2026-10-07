---
name: credit-card-dispute-and-cli
version: 1.0.0
description: Process a credit-card transaction dispute and a requested credit-limit increase (CLI) in the same customer interaction, including identity verification, discoverable banking-tool calls, provisional-credit analysis, and the required CLI submission, complete eligibility review, decision, and customer communication.
---

# Credit Card Dispute and Credit-Limit Increase

Use this Skill when a customer asks to dispute a credit-card transaction, request a CLI, or asks for both. It is designed for normal banking-tool execution. Never fabricate customer data, transaction details, card digits, eligibility results, or tool results.

## Required inputs and prerequisites

1. Identify the customer and the relevant credit-card account. Retrieve the profile, accounts, and transactions with the standard banking tools when needed.
2. Before account-specific action, confirm **two of four** profile fields with the customer: date of birth, email, phone number, and address. Retrieve the authoritative profile and compare the customer-provided values. Once two match, obtain the current time and call `log_verification` with all required profile fields and the timestamp. Do not treat fields merely read from a profile lookup as customer confirmation.
3. Match the disputed transaction to the specified card, merchant, amount, and date. If more than one transaction could match, ask the customer to identify it.
4. Obtain any missing dispute facts before filing: issue-noticed date, merchant-contact answer, one allowed reason code, one resolution, and partial-refund amount if applicable. The card action must be exactly `keep_active` or `cancel_and_reissue`.
5. A card’s last four digits are required to file a dispute. If they are not provided, unlock and call `get_card_last_4_digits` using the selected `credit_card_account_id`; do not guess digits or use a digit string from another card.

If identity confirmation or a mandatory fact cannot be obtained, explain what is needed and do not file a dispute or perform account-changing CLI actions. A customer who cannot access their app can still have the agent retrieve card last four digits through the discovered account-ID tool after the normal identity gate.

## Dispute workflow

### 1. Gather and normalize the filing fields

The filing tool requires the following values:

- `transaction_id`
- `card_action`
- `card_last_4_digits`
- `full_name`, `user_id`, `phone`, `email`, `address`
- `contacted_merchant` (boolean)
- `purchase_date` and `issue_noticed_date` in `MM/DD/YYYY`
- `dispute_reason`, exactly one of:
  `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`,
  `goods_services_not_received`, `goods_services_not_as_described`,
  `canceled_subscription_still_charging`, `refund_never_processed`
- `resolution_requested`, exactly one of `full_refund`, `partial_refund`, `reversal_of_charge`
- `partial_refund_amount` only when resolution is `partial_refund`
- `eligible_for_provisional_credit` (boolean)

Convert a transaction date returned as `YYYY-MM-DD` to `MM/DD/YYYY`. Do not supply `partial_refund_amount` for a full refund or charge reversal.

### 2. Determine provisional-credit eligibility before filing

Unlock and call `get_user_dispute_history_7291` with the user ID. Review disputes filed in the 12 months before this new filing; use dates rather than assuming an empty result means an unavailable history.

All of these must be true for `eligible_for_provisional_credit: true`:

- The account has been open at least 60 days.
- The reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`.
- For `goods_services_not_received`, the purchase is more than 30 days old (strictly more than 30, not 30 or fewer).
- The transaction amount is at least $25 and does not exceed the card tier cap.
- There are no more than two prior disputes in the preceding 12 months.
- For every non-fraud reason, the customer contacted the merchant first.

Tier caps are: entry $2,500; mid $5,000; premium $10,000; elite $15,000; invitation $25,000. Silver Rewards Card is mid tier. Set the flag false if any condition fails; this does not itself prevent filing the dispute.

Use `scripts/assess.py` with `mode: "dispute"` for date, amount, reason, merchant-contact, and history counting. The script is a deterministic aid only; compare unknown or ambiguous data with the underlying tool response and resolve it before filing.

### 3. File the dispute

Unlock `file_credit_card_transaction_dispute_4829`, then call it through `call_discoverable_agent_tool` with a JSON-string argument object containing every required field. Record the result. Do not substitute a CLI or replacement-card tool for this filing.

## CLI workflow

A separate CLI request must be evaluated under its mandated sequence. If the customer requested a dispute first and it is filed, that dispute may be an active/pending dispute when the CLI review occurs. Do not ignore an active dispute merely because it was filed during the same interaction.

### 1. Validate the requested increase before submitting

Derive the increase as `requested_new_total_limit - current_credit_limit` if the customer supplied a total limit. Confirm the increase is a positive whole-dollar amount, because the submission tool requires an integer increase amount.

Only entry, mid, and premium tiers have stated CLI limits in the available policy:

| Tier | Maximum increase | Minimum age | Cooldown after approved CLI | Utilization requirement | On-time payment months |
|---|---:|---:|---:|---:|---:|
| Entry | 25% of current limit | 120 days | 120 days | below 70% | 6 consecutive |
| Mid | 50% of current limit | 90 days | 90 days | below 80% | 3 consecutive |
| Premium | 50% of current limit | 60 days | 60 days | below 90% | 3 consecutive |

If the request exceeds its tier maximum, do **not** submit it. Tell the customer the maximum permitted increase and ask whether they want to request that valid amount instead. This is the only pre-submission rejection in the prescribed CLI flow.

For an in-scope amount, use `scripts/assess.py` with `mode: "cli"` to calculate the limit, age, strict utilization comparison, cooldown, payment-month requirement, and non-final replacement status. Do not use the script to skip the required banking checks.

### 2. Submit before eligibility checks

Once the amount is valid and the customer has requested it, unlock `submit_credit_limit_increase_request_7392` and call it with:

- `credit_card_account_id`
- `user_id`
- `requested_increase_amount` (integer dollar increase)

Submission creates the formal record and must occur before eligibility verification. Retain the submission result for the audit trail even if the request is later denied.

### 3. Check every CLI requirement after submission

Perform and document **all** checks, even after discovering one failure:

1. Account age from the account open date.
2. Cooldown: unlock and call `get_credit_limit_increase_history_4829` using the account ID. A denied request does not trigger cooldown; determine whether the most recent **approved** request is within the tier’s full cooldown period.
3. Pending disputes: use `get_user_dispute_history_7291` and treat open/under-review or otherwise non-final disputes as pending. A previously filed dispute in this interaction must be considered.
4. Pending replacement orders: unlock and call `get_pending_replacement_orders_5765` using the account ID. Any order not clearly `delivered` or `cancelled` is pending.
5. Good standing: verify the account is current and has no past-due balance.
6. Utilization: calculate current balance divided by current credit limit; it must be strictly below the tier threshold.
7. Payment history: unlock and call `get_payment_history_6183` with the account ID and the tier-required number of months. Confirm every required consecutive month is on time.

If a tool response is malformed, incomplete, or ambiguous, do not infer approval. Explain that the request cannot be completed until the required verification is available; use the permitted `other` denial reason only if a formal denial must be recorded and no more specific listed reason applies.

### 4. Record the decision

If every check passes, compute `new_credit_limit = current_credit_limit + requested_increase_amount`, unlock `approve_credit_limit_increase_5847`, and call it with the account ID, user ID, and numeric new total limit.

Otherwise unlock `deny_credit_limit_increase_5848` and call it with account ID, user ID, and the most directly applicable allowed reason:

- account age: `insufficient_account_age`
- approved-request cooldown: `cooldown_period_active`
- active dispute: `pending_disputes`
- non-final replacement order: `pending_replacement_card`
- not current or past-due balance: `past_due_balance`
- utilization at or above threshold: `high_utilization`
- missing required consecutive on-time history: `insufficient_payment_history`
- pre-submission excessive amount: `requested_amount_exceeds_limit` (normally no request is submitted in this case)
- unsupported/otherwise unclassifiable issue: `other`

The provided policy does not establish a single priority if several failures coexist. Preserve all check results in notes; select the denial reason that directly explains the blocking condition communicated to the customer.

## Customer communication

After tool results are known, give a concise separate status for each request. For a filed dispute, confirm it was filed and whether provisional credit was eligible; do not promise final dispute outcome. For an approved CLI, give the new total limit. For a denied CLI, state the specific reason and a policy-supported next step or reapplication timing when it can be calculated (for example, the cooldown end date). Never claim an action succeeded unless the corresponding banking tool returned success.

## Helper script

`scripts/assess.py` reads one JSON object from standard input and writes one JSON object to standard output. It performs no banking actions.

- Dispute schema: `{"mode":"dispute","card_type":str,"account_open_date":date,"as_of":date,"purchase_date":date,"transaction_amount":number,"reason":str,"contacted_merchant":bool,"prior_dispute_dates":[date,...]}`.
- CLI schema: `{"mode":"cli","tier":str,"current_limit":number,"current_balance":number,"account_open_date":date,"as_of":date,"requested_increase":number,"last_approved_cli_date":date|null,"consecutive_on_time_months":integer,"has_pending_dispute":bool,"replacement_statuses":[str,...]}`.
- Dates accept `YYYY-MM-DD` or `MM/DD/YYYY`. Output contains `ok`, `errors`, computed measurements, and individual pass/fail flags. Unsupported tiers produce an error rather than a policy guess.

Example runtime use: provide the schema object to `run_skill_script` with `relative_path` set to `scripts/assess.py`; inspect the returned JSON before making the corresponding discovered-tool calls.
