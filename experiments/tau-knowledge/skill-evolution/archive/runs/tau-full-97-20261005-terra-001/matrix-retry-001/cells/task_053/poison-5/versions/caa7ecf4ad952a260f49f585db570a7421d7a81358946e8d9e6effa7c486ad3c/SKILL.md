---
name: credit-card-dispute-and-cli
version: 1.2.0
description: Process credit-card transaction disputes and credit-limit increase (CLI) requests, including simultaneous requests. Use when an authorized cardholder requests either or both workflows and the executor has access to account, transaction, verification, transfer, and discoverable banking tools.
---

# Credit-card dispute and CLI processing

Treat a dispute and a credit-limit increase as independent workflows. A failed dispute lookup, a dispute escalation, or a human transfer does **not** withdraw, defer, or replace a separate confirmed CLI request.

## Safety, verification, and tool conventions

1. Before an account-changing action, verify the customer. Unless the runtime explicitly marks the session as verified, obtain confirmation of at least two registered identity fields from date of birth, email, phone, and address. A database lookup is not customer confirmation.
2. Obtain the current time and call `log_verification` with all fields required by its schema, including the verified values and timestamp.
3. Locate the requested card account and, for a dispute, match the reported merchant, amount, date, and card account to a completed transaction. Never guess identifiers, card digits, dates, contact information, or monetary values.
4. For each named discoverable agent tool, call `unlock_discoverable_agent_tool` with its exact name, then call `call_discoverable_agent_tool` with that name and a JSON-string `arguments` object. An unlock alone is not a banking action.
5. Preserve actual tool results. Do not say an action completed unless its tool call succeeded.

## Mandatory scheduling for simultaneous requests

When both a dispute and a CLI are requested, use this order:

1. Verify identity and collect/match data for both requests.
2. Attempt the mandatory dispute card-last-four lookup and gather other dispute inputs.
3. If that lookup is unavailable and the dispute must be escalated, **pause only the dispute workflow**.
4. Complete the independent CLI workflow through its terminal decision before transferring: submit, perform every required post-submission review, then approve or deny.
5. Only then call `transfer_to_human_agents` for the unresolved dispute.

Do **not** call `transfer_to_human_agents` while a valid, confirmed CLI request remains unsubmitted, unchecked, or undecided. A transfer can end the interaction, so a transfer summary is never a substitute for the CLI submission or decision tool calls.

## Workflow A: transaction dispute

### Collect required filing information

Before filing, identify or collect:

- `transaction_id` for the matched completed transaction;
- `card_action`: use `keep_active` unless the customer requested cancellation and reissue, then use `cancel_and_reissue`;
- full name, user ID, registered phone, email, and address;
- `purchase_date` and `issue_noticed_date` in `MM/DD/YYYY` format;
- whether the customer contacted the merchant;
- one valid dispute reason: `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, or `refund_never_processed`;
- one resolution: `full_refund`, `partial_refund`, or `reversal_of_charge`. Include a positive `partial_refund_amount` only for `partial_refund`.

### Required lookups and provisional credit

1. Unlock and call `get_card_last_4_digits` with `{"credit_card_account_id":"<account id>"}`. Use only the returned value as `card_last_4_digits`.
2. Unlock and call `get_user_dispute_history_7291` with the user ID.
3. Determine provisional-credit eligibility before filing. It is true only when all conditions hold:
   - the account is at least 60 days old;
   - the reason is fraud, duplicate charge, or goods/services not received;
   - a goods-not-received purchase is more than 30 days old;
   - amount is at least $25 and at most the tier cap (entry $2,500; mid $5,000; premium $10,000; elite $15,000; invitation $25,000);
   - no more than two disputes were filed in the prior 12 months; and
   - for non-fraud disputes, the merchant was contacted.

Use `scripts/evaluate_credit_card_case.py` for deterministic date, amount, age, utilization, cooldown, and dispute-count calculations. It has no banking side effects.

### File or escalate

If all required fields, including the retrieved last four digits, are available, unlock and call `file_credit_card_transaction_dispute_4829` with all required fields. For example, the argument object has this shape:

```json
{
  "transaction_id":"<transaction id>",
  "card_action":"keep_active",
  "card_last_4_digits":"<retrieved digits>",
  "full_name":"<full name>",
  "user_id":"<user id>",
  "phone":"<registered phone>",
  "email":"<registered email>",
  "address":"<registered address>",
  "contacted_merchant":true,
  "purchase_date":"MM/DD/YYYY",
  "issue_noticed_date":"MM/DD/YYYY",
  "dispute_reason":"<allowed reason>",
  "resolution_requested":"<allowed resolution>",
  "eligible_for_provisional_credit":false
}
```

Add `partial_refund_amount` only when applicable. State that the dispute was filed only after a successful filing response.

If the required last-four lookup explicitly reports that the tool is unavailable, do not guess digits, solicit a substitute value, or claim the dispute was filed. Complete any independent CLI to a recorded decision first, then transfer the dispute to a human specialist. The transfer summary must state:

- the transaction ID;
- the reason (structured reason code or equivalent plain language);
- requested resolution;
- issue-noticed date;
- that `get_card_last_4_digits` was unavailable; and
- that no dispute was filed.

Use the applicable transfer reason, normally `complex_billing_dispute` or `technical_system_error` when the unavailable required tool is the reason for escalation.

## Workflow B: credit-limit increase (CLI)

The following order is mandatory: validate the requested amount, **submit the formal request**, perform all eligibility checks, and record an approval or denial.

### 1. Establish an exact, in-range increase

Classify the card tier. The per-request maximum is 25% of the current limit for entry tier and 50% for mid and premium tiers. If the customer asks for a new total limit, compute the implied increase from the current limit.

If the customer used approximate wording, state the exact computed increase and obtain confirmation before submission. A customer who affirmatively confirms that exact increase has a confirmed request. If the amount exceeds the cap, do not submit; explain the maximum and ask for an adjusted confirmed amount. Continue only with a positive, exact, confirmed amount within the cap.

### 2. Submit before every eligibility check

Immediately after valid confirmation, unlock and call `submit_credit_limit_increase_request_7392`:

```json
{
  "credit_card_account_id":"<account id>",
  "user_id":"<user id>",
  "requested_increase_amount":123
}
```

This call creates the required formal record. It must occur before calling CLI history, dispute history for CLI review, replacement-order checks, or payment-history checks. Do not omit it because a separate dispute is unavailable or will be transferred.

### 3. Perform all post-submission checks

After a successful submission, complete and retain each check below, even if an earlier one fails:

1. **Account age:** at least 120 days entry, 90 days mid, or 60 days premium.
2. **Cooldown:** unlock and call `get_credit_limit_increase_history_4829` with the card account ID. Only a previous approved request triggers the tier cooldown of 120/90/60 days. Exclude the request just submitted from the prior-history calculation.
3. **Active disputes:** unlock and call `get_user_dispute_history_7291` with the user ID. An open, pending, or under-review dispute for the account blocks CLI. Do not invent an active dispute from an unfiled dispute attempt.
4. **Replacement orders:** unlock and call `get_pending_replacement_orders_5765` with the account ID. Any order not clearly `delivered` or `cancelled` blocks CLI.
5. **Good standing:** confirm the account is active/current and has no past-due balance.
6. **Utilization:** calculate `current_balance / credit_limit * 100`; it must be strictly below 70% entry, 80% mid, or 90% premium.
7. **Payment history:** unlock and call `get_payment_history_6183` with the account ID and `months: 6` for entry tier or `months: 3` for mid and premium tiers. The result must establish the required consecutive on-time payment months.

If a required lookup is unavailable or ambiguous, do not invent a favorable result. Retain the submitted request and follow the available operational escalation path; never falsely report approval.

### 4. Record a terminal decision

When all post-submission evidence is available, make a recorded decision before any transfer unrelated to the CLI:

- If all checks pass, unlock and call `approve_credit_limit_increase_5847` with account ID, user ID, and `new_credit_limit` equal to current limit plus the confirmed increase.
- If any check fails, unlock and call `deny_credit_limit_increase_5848` with account ID, user ID, and one allowed reason. Use the first observed failure in this order: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, `insufficient_payment_history`.

Never use `requested_amount_exceeds_limit` after a pre-submission cap rejection because no formal request should have been submitted in that situation.

### 5. Communicate accurately

For approval, confirm the new total limit. For denial, explain the reason and, if determinable, the next eligible date or corrective action. Distinguish a dispute that was escalated and unfiled from the independently submitted and decided CLI.

## Calculation helper

Run the helper with normalized runtime data:

```sh
python3 scripts/evaluate_credit_card_case.py < normalized_case.json
```

It reads one JSON object from stdin and emits one JSON object on stdout. Input schema:

- `now` (required): date or timestamp;
- `account` (required): `opened_on`, `current_balance`, `credit_limit`, `past_due_amount`, and optional `status`;
- `dispute` (optional): `tier`, `reason`, `amount`, `purchase_date`, `contacted_merchant`, and `prior_dispute_dates` array;
- `cli` (optional): `tier`, `requested_increase_amount`, `prior_approved_request_dates` excluding the newly submitted request, `has_active_disputes`, `has_pending_replacement`, and `consecutive_on_time_months`.

Correct source data if `input_errors` is nonempty. `cli.should_submit` evaluates only the pre-submission amount cap; it is not an approval decision. Interpret CLI eligibility only after the formal submission and all required lookup results.