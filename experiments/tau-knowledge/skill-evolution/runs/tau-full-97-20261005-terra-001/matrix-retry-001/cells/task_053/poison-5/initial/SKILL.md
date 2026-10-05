---
name: credit-card-dispute-and-cli
version: 1.0.0
description: Process a credit-card transaction dispute and a requested credit-limit increase (CLI) for the same account. Use when the customer supplies a disputed transaction and/or a desired credit-limit change and the executor has access to the documented account, history, dispute, and CLI tools.
---

# Credit-card dispute and CLI processing

Use this Skill to complete both requested workflows without letting one workflow bypass the required checks for the other. All identifiers, dates, balances, contact details, and tool results must be obtained at runtime; do not reuse values from a prior case.

## Safety and prerequisites

1. Confirm the customer is authorized for the account. If the runtime requires identity verification, obtain confirmation of at least two of date of birth, email, phone number, and address. A database lookup is not customer confirmation. Then call `log_verification` with all required lookup fields and a current timestamp. Do not perform account-changing actions until this prerequisite is satisfied (unless the host explicitly indicates an already verified session).
2. Identify the requested card account and match the dispute to a completed transaction on that account. Do not guess a transaction, account, card number, customer contact field, requested increase amount, or dispute date.
3. A CLI request must state an exact dollar increase. If the customer gives an approximate desired total, calculate the implied increase from the current limit and ask the customer to confirm that exact amount before submitting.
4. Use account and transaction lookup tools available in the host to obtain the account, current balance, current limit, opening date, status, past-due amount, transaction ID, transaction date, and customer contact details.

## Required runtime tool convention

For every specialized tool named below, first call `unlock_discoverable_agent_tool` with that exact name, then call `call_discoverable_agent_tool` with that exact name and a JSON-string `arguments` object. Do not treat an unlock as a completed action. Preserve the tool response and stop/escalate rather than claiming success if a call fails.

## Workflow A — formal transaction dispute

Collect or validate all formal-dispute inputs before filing:

- the matched `transaction_id`;
- `card_action`: `keep_active` unless the customer asks to cancel/reissue the card; otherwise `cancel_and_reissue`;
- full name, user ID, registered phone, registered email, and registered address;
- the purchase date formatted `MM/DD/YYYY`;
- issue-noticed date formatted `MM/DD/YYYY`;
- whether the customer contacted the merchant;
- one allowed dispute reason;
- one allowed resolution, plus a positive partial amount only for `partial_refund`.

### Determine provisional credit before filing

1. Unlock and call `get_card_last_4_digits` with:
   ```json
   {"credit_card_account_id":"<account id>"}
   ```
   Use the returned value for `card_last_4_digits`; do not ask the customer to reveal it when it can be retrieved this way.
2. Unlock and call `get_user_dispute_history_7291` with:
   ```json
   {"user_id":"<user id>"}
   ```
   Count disputes filed in the 12 months immediately preceding the current date. Retain the dates and statuses for the case record.
3. Determine eligibility using all of these conditions:
   - account is at least 60 days old;
   - reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`;
   - for `goods_services_not_received`, the purchase is more than 30 days old;
   - amount is at least $25 and no greater than the provisional-credit cap: entry $2,500, mid $5,000, premium $10,000, elite $15,000, invitation $25,000;
   - no more than two disputes were filed in the prior 12 months;
   - for every non-fraud reason, merchant contact is true.

Use `scripts/evaluate_credit_card_case.py` to make the date, tier, amount, and count calculations reproducibly. Supply normalized tool data; the script does not call bank tools.

### File the dispute

Unlock and call `file_credit_card_transaction_dispute_4829` with exactly these required fields (and `partial_refund_amount` only when applicable):

```json
{
  "transaction_id":"<transaction id>",
  "card_action":"keep_active",
  "card_last_4_digits":"<retrieved last four>",
  "full_name":"<registered full name>",
  "user_id":"<user id>",
  "phone":"<registered phone>",
  "email":"<registered email>",
  "address":"<registered address>",
  "contacted_merchant":true,
  "purchase_date":"MM/DD/YYYY",
  "issue_noticed_date":"MM/DD/YYYY",
  "dispute_reason":"<allowed reason>",
  "resolution_requested":"<allowed resolution>",
  "eligible_for_provisional_credit":true
}
```

Use the computed boolean even when it is false. Tell the customer the dispute was filed only after a successful tool response. Describe provisional credit as temporary and conditional; do not promise it when ineligible.

## Workflow B — CLI

The CLI procedure has a mandatory order. Do not reorder it because a customer appears ineligible.

### 1. Pre-submit cap check

Classify the card as entry, mid, or premium. The maximum single increase is 25% of the current limit for entry and 50% for mid or premium. Calculate the requested increase, not the requested new total.

- If it exceeds the cap, do **not** submit or deny a CLI request. Tell the customer the maximum increase and obtain an adjusted, confirmed amount.
- If the amount is exact, positive, and within the cap, continue.

### 2. Submit first

Unlock and call `submit_credit_limit_increase_request_7392`:

```json
{
  "credit_card_account_id":"<account id>",
  "user_id":"<user id>",
  "requested_increase_amount":123
}
```

Record the submission response/ID. This submission occurs before all eligibility checks.

### 3. Run every eligibility check after submission

Check every item even if an earlier item fails, retaining each result for the audit record:

1. Account age: entry >=120 days, mid >=90, premium >=60.
2. Cooldown: unlock and call `get_credit_limit_increase_history_4829` with the account ID. Only a previous **approved** request starts the tier cooldown (120/90/60 days). Exclude the request just submitted, using its returned ID/time. A customer is eligible on or after the cooldown end date.
3. Pending disputes: use the previously retrieved dispute history plus the successful newly filed dispute. Any open, pending, or under-review dispute for the account blocks the CLI.
4. Replacement orders: unlock and call `get_pending_replacement_orders_5765` with the account ID. Any order not clearly `delivered` or `cancelled` is pending.
5. Good standing: validate that the account is current and has no past-due amount.
6. Utilization: calculate `current_balance / credit_limit * 100`. It must be strictly below 70% (entry), 80% (mid), or 90% (premium).
7. Payment history: unlock and call `get_payment_history_6183` using the account ID and `months` 6 for entry or 3 for mid/premium. The returned history must establish that every required consecutive month was on time.

If any required lookup is unavailable or ambiguous, do not approve or deny based on an assumption; resolve the lookup or report that processing cannot be completed.

### 4. Record the decision

If every check passes, unlock and call `approve_credit_limit_increase_5847` with the account ID, user ID, and `new_credit_limit` equal to current limit plus the confirmed increase.

If one or more checks fail, unlock and call `deny_credit_limit_increase_5848` with one allowed reason. Select the first applicable reason in this audit order: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, `insufficient_payment_history`. Do not use `requested_amount_exceeds_limit` after the pre-submit cap rejection because no formal request should have been submitted.

### 5. Customer communication

State the completed dispute outcome, whether provisional credit applies, and the requested resolution. For CLI approval, state the new total limit. For a denial, explain the observed reason and, where determinable, the reapplication date (for example, cooldown end date). Never expose internal-only eligibility details beyond the customer-facing reason needed to explain the result.

## Calculation helper

`scripts/evaluate_credit_card_case.py` consumes one normalized JSON object on stdin and emits one JSON assessment on stdout. It does not make side effects or bank calls.

Input schema:

- `now` (required): current date or timestamp.
- `account` (required): `opened_on`, `current_balance`, `credit_limit`, `past_due_amount`, and optional `status`.
- `dispute` (optional): `tier`, `reason`, `amount`, `purchase_date`, `contacted_merchant`, and `prior_dispute_dates` (array of filing dates).
- `cli` (optional): `tier`, `requested_increase_amount`, `prior_approved_request_dates` (array, excluding the just-submitted request), `has_active_disputes`, `has_pending_replacement`, and `consecutive_on_time_months`.

A runnable invocation using runtime-normalized data is:

```sh
python3 scripts/evaluate_credit_card_case.py < normalized_case.json
```

Interpret `input_errors` or an `unavailable` check as a stop condition requiring corrected data. `cli.should_submit` only answers the pre-submit cap check; it is not approval. After a dispute is successfully filed, set `cli.has_active_disputes` from the refreshed/combined history before assessing the CLI.
