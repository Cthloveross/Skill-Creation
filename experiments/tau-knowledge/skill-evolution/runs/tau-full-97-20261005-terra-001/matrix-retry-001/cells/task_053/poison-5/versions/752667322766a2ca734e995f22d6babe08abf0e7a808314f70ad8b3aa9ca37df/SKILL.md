---
name: credit-card-dispute-and-cli
version: 1.1.0
description: Process one or both requests for a credit-card transaction dispute and a credit-limit increase (CLI). Use when a customer requests a dispute, a CLI, or both, and the executor can access the documented account, transaction, eligibility, and discoverable banking tools.
---

# Credit-card dispute and CLI processing

Complete each requested workflow independently. A failure or escalation in the dispute workflow does **not** cancel, defer, or replace a separately confirmed CLI request. Obtain all customer data, identifiers, dates, and balances from the current runtime; never reuse case-specific values from another interaction.

## Prerequisites and tool convention

1. Before any account-changing action, verify that the customer is authorized. If the runtime does not explicitly mark the session verified, have the customer confirm at least two of date of birth, registered email, phone, and address. A database lookup alone is not confirmation. Obtain the current time and call `log_verification` with every field required by its schema.
2. Locate the requested card account and match a dispute to a completed transaction on that account. Do not guess a transaction, card number, contact value, date, or requested amount.
3. For every specialized tool named in this Skill, call `unlock_discoverable_agent_tool` using the exact tool name, then call `call_discoverable_agent_tool` with that name and a valid JSON-string `arguments` object. An unlock is not a completed banking action.
4. Preserve tool responses. Do not claim an action succeeded unless its actual call succeeded. If a required lookup is unavailable, record the context and use the required escalation path for that workflow.

## Handling two simultaneous requests

When the same interaction contains both a dispute and a CLI:

- Collect the information needed for both requests after verification.
- Follow the formal-dispute requirements, including attempting the required card-last-four lookup.
- If the dispute cannot proceed because a required tool or input is unavailable, do not file it and prepare an accurate specialist-transfer summary.
- **Before initiating that transfer, complete any separate confirmed CLI workflow that can proceed.** In particular, submit a valid confirmed CLI request and perform all its required post-submission checks. A human transfer terminates or redirects the interaction in many runtimes, so it must not be used as a reason to leave the independent CLI request unsubmitted.
- Initiate the human transfer after independent executable requests are completed or appropriately recorded. State precisely which workflow was escalated and which actions, if any, were completed.

## Workflow A — credit-card transaction dispute

### Gather and validate filing inputs

Match the customer’s described merchant, amount, purchase date, and card account to a completed transaction. Collect or verify all of the following before filing:

- `transaction_id`;
- `card_action`: `keep_active` unless the customer requests cancellation and reissue, in which case use `cancel_and_reissue`;
- full name, user ID, registered phone, registered email, and registered address;
- `purchase_date` and `issue_noticed_date`, both in `MM/DD/YYYY` format;
- whether the customer contacted the merchant;
- exactly one reason: `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, or `refund_never_processed`;
- exactly one resolution: `full_refund`, `partial_refund`, or `reversal_of_charge`; include a positive `partial_refund_amount` only for `partial_refund`.

### Required lookup and provisional-credit decision

1. Unlock and call `get_card_last_4_digits` with:
   ```json
   {"credit_card_account_id":"<account id>"}
   ```
   Use its returned value as `card_last_4_digits`. Do not ask the customer to disclose it when this lookup is available.
2. Unlock and call `get_user_dispute_history_7291` with the user ID. Review prior dispute dates and statuses.
3. Determine provisional-credit eligibility before filing. All conditions must be true:
   - account age is at least 60 days;
   - reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`;
   - a goods-not-received purchase is more than 30 days old;
   - amount is at least $25 and no greater than the tier cap (entry $2,500; mid $5,000; premium $10,000; elite $15,000; invitation $25,000);
   - no more than two disputes were filed in the prior 12 months; and
   - for a non-fraud reason, the merchant was contacted.

Use `scripts/evaluate_credit_card_case.py` for normalized date, amount, tier, utilization, cooldown, and dispute-count calculations. The script has no banking side effects.

### File or escalate

If every required filing field and lookup is available, unlock and call `file_credit_card_transaction_dispute_4829` with all required fields:

```json
{
  "transaction_id":"<transaction id>",
  "card_action":"keep_active",
  "card_last_4_digits":"<retrieved last four>",
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

Add `partial_refund_amount` only for a partial-refund request. Use the calculated provisional-credit boolean, whether true or false. Say the dispute was filed only after a successful response.

If the required card-last-four lookup explicitly reports that the tool is unavailable, do not substitute a guessed value or claim the dispute was filed. After completing any independent CLI work, transfer to a human specialist with the applicable transfer reason. The summary must include the transaction ID, dispute reason, requested resolution, issue-noticed date, the unavailable lookup, and that no dispute was filed.

## Workflow B — credit-limit increase (CLI)

The order below is mandatory. Once an exact valid amount is confirmed, submission occurs before cooldown, dispute, replacement, payment-history, or other eligibility review.

### 1. Establish an exact, in-range increase

Classify the card tier. Maximum per-request increases are 25% of current limit for entry tier and 50% for mid and premium tiers.

If the customer states a desired total limit, calculate the implied dollar increase. If wording such as “about” makes the amount ambiguous, state the exact proposed increase and obtain confirmation. If the requested increase exceeds the tier cap, do not submit or deny a formal request; tell the customer the maximum and obtain an adjusted confirmed amount. Continue only with a positive, exact, confirmed amount within the cap.

### 2. Submit before eligibility checks

Unlock and call `submit_credit_limit_increase_request_7392`:

```json
{
  "credit_card_account_id":"<account id>",
  "user_id":"<user id>",
  "requested_increase_amount":123
}
```

Record the response. Do not let a pending dispute escalation, including a transfer that will occur later, prevent this formal submission.

### 3. Perform every post-submission eligibility check

After the successful submission, perform and retain every check below, even if one already fails:

1. **Account age:** entry at least 120 days, mid at least 90 days, premium at least 60 days.
2. **Cooldown:** unlock and call `get_credit_limit_increase_history_4829` with the account ID. Only a prior approved request starts the tier cooldown: 120/90/60 days for entry/mid/premium. Exclude the new request just submitted. Eligibility resumes on or after the cooldown-end date.
3. **Active disputes:** unlock and call `get_user_dispute_history_7291` with the user ID after submission. Treat an open, pending, or under-review dispute for the account as blocking. If a new dispute was successfully filed in this interaction, include it. If the dispute could not be filed, do not invent an active dispute from the unfiled request.
4. **Replacement cards:** unlock and call `get_pending_replacement_orders_5765` with the account ID. Any order not clearly `delivered` or `cancelled` blocks CLI processing.
5. **Good standing:** confirm the account is current and has no past-due balance.
6. **Utilization:** calculate current balance divided by current limit times 100. It must be strictly below 70%/80%/90% for entry/mid/premium.
7. **Payment history:** unlock and call `get_payment_history_6183` with the account ID and `months` equal to 6 for entry or 3 for mid/premium. The returned history must establish the required consecutive on-time months.

A missing or ambiguous required post-submission lookup prevents a supported approval or denial based on assumptions. Report that processing is incomplete and retain the submitted request according to the system result.

### 4. Record the decision

If all checks pass, unlock and call `approve_credit_limit_increase_5847` with account ID, user ID, and `new_credit_limit` equal to current limit plus the confirmed increase.

If one or more checks fail, unlock and call `deny_credit_limit_increase_5848` with one allowed reason. Use the first observed failure in this order: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, `insufficient_payment_history`.

Do not use `requested_amount_exceeds_limit` after a pre-submit cap rejection because no formal CLI request should exist in that case.

### 5. Communicate accurately

For an approval, state the new total limit. For a denial, state the customer-facing reason and, if determinable, when they may reapply. For a filed dispute, state the filing outcome and that provisional credit is temporary and conditional. Never say an unavailable-lookup dispute was filed. When transferring, distinguish the escalated dispute from the independently submitted and evaluated CLI.

## Calculation helper

Run the helper with normalized current runtime data:

```sh
python3 scripts/evaluate_credit_card_case.py < normalized_case.json
```

The script reads one JSON object on stdin and writes one JSON object on stdout. Its input schema is:

- `now` (required): date or timestamp;
- `account` (required): `opened_on`, `current_balance`, `credit_limit`, `past_due_amount`, and optional `status`;
- `dispute` (optional): `tier`, `reason`, `amount`, `purchase_date`, `contacted_merchant`, and `prior_dispute_dates` array;
- `cli` (optional): `tier`, `requested_increase_amount`, `prior_approved_request_dates` array excluding the new request, `has_active_disputes`, `has_pending_replacement`, and `consecutive_on_time_months`.

Treat any `input_errors` as a need to correct the normalized data. `cli.should_submit` only evaluates the pre-submission amount cap; it never authorizes approval. Only populate and interpret the CLI eligibility assessment after the required request has been submitted and all lookup results are available.
