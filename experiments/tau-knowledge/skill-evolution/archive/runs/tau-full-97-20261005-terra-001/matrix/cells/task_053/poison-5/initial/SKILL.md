---
name: credit-card-dispute-and-cli
version: 1.0.0
description: Process a verified customer's credit-card transaction dispute and credit-limit-increase (CLI) request using the required Rho-Bank discovery tools, eligibility checks, and approval or denial workflow. Use when a request includes either or both services.
---

# Credit-card dispute and CLI processing

Use this Skill for Rho-Bank credit-card disputes, CLI requests, or a combined request. The executor performs all banking actions with the normal tools; the packaged script only calculates and validates policy results.

## Preconditions and data handling

1. Identify the customer and account. When identity verification is required, ask the customer to confirm **two of** date of birth, email, phone number, and address against the profile. Do not treat data merely retrieved from the profile as customer confirmation.
2. After two fields match, obtain the current time and call `log_verification` with the complete profile values and timestamp. Reuse already supplied, current read-only observations when they are unambiguous; do not request duplicate facts.
3. Obtain the user's card accounts and transactions using the regular account/transaction lookup tools. Select the account and transaction that match the customer's card, merchant, date, and amount. If more than one candidate remains, ask the customer to disambiguate.
4. Never invent an ID, last four digits, payment result, dispute status, or other missing fact. Explain what is needed or retry/escalate on a system error.

For a combined request, complete the dispute workflow first when the customer has asked to file it now. Before the CLI decision, perform a fresh active-dispute check because a newly filed dispute can be an active/pending dispute that blocks a CLI.

## Dispute workflow

### Gather and validate the required facts

Obtain all of the following before filing:

- `transaction_id` for the matched transaction;
- the customer's intent for the card: use `keep_active` unless they request cancellation/replacement, in which case use `cancel_and_reissue`;
- card last four digits;
- verified full name, user ID, registered phone, email, and address;
- whether the customer contacted the merchant;
- purchase date and issue-noticed date, both formatted `MM/DD/YYYY`;
- one supported reason: `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, or `refund_never_processed`;
- one resolution: `full_refund`, `partial_refund`, or `reversal_of_charge`; a numeric `partial_refund_amount` is required only for `partial_refund`.

If the customer does not have the card, unlock `get_card_last_4_digits`, then call it through `call_discoverable_agent_tool` with `{"credit_card_account_id":"..."}`. Do not ask the customer to reveal the full card number.

### Determine provisional-credit eligibility

Unlock and call `get_user_dispute_history_7291` with the user ID. Determine provisional-credit eligibility, rather than promising it to the customer, using all conditions below:

- account open at least 60 days;
- reason is fraud, duplicate charge, or goods/services not received; for goods/services not received, purchase is more than 30 days old;
- amount is at least $25 and no more than the tier cap (mid-tier: $5,000);
- no more than two disputes filed in the prior 12 months;
- for every non-fraud reason, the customer attempted merchant resolution.

For Silver Rewards Card, use mid-tier for the $5,000 cap. The `scripts/evaluate_credit_card_request.py` helper can calculate the date/count/amount result from normalized tool data. If dispute history or another required fact cannot be obtained, do not guess the required boolean.

### File the dispute

Unlock `file_credit_card_transaction_dispute_4829`, then call it with a JSON string containing every required field and the calculated `eligible_for_provisional_credit` boolean. Include `partial_refund_amount` only when the requested resolution is `partial_refund`. Report that a dispute was filed and explain that a provisional credit, if eligible, is temporary while the dispute is investigated; do not represent it as a final refund.

## CLI workflow

### 1. Amount precheck — before CLI submission

Translate a requested total limit into an increase by subtracting the current limit. Confirm an imprecise requested total if it prevents identifying an exact increase. The increase submitted must be an integer number of dollars.

Use the account's tier and current limit to calculate the maximum increase:

| Tier | Maximum increase | Minimum age | Cooldown | Utilization requirement | On-time payment months |
|---|---:|---:|---:|---:|---:|
| entry | 25% | 120 days | 120 days | below 70% | 6 |
| mid | 50% | 90 days | 90 days | below 80% | 3 |
| premium | 50% | 60 days | 60 days | below 90% | 3 |

If the amount exceeds the maximum, tell the customer the maximum and ask whether they want that amount instead. **Do not submit or deny a CLI request that fails this precheck**, because no request has been created. If the requested amount is valid and confirmed, continue.

### 2. Submit, then collect every required eligibility result

Unlock and call `submit_credit_limit_increase_request_7392` first with the account ID, user ID, and requested integer increase. The formal request must exist before eligibility processing.

After submission, check **all** of the following even if an earlier criterion fails:

1. Calculate account age against the tier minimum from the account opening date.
2. Unlock and call `get_credit_limit_increase_history_4829` for the account. The tier cooldown applies when the most recent CLI request was approved; denied requests do not trigger it. Count full days from that submission date.
3. Check that no dispute is active/pending. Use a fresh `get_user_dispute_history_7291` lookup and treat open/under-review or other nonfinal dispute statuses as active unless the tool explicitly identifies them as final.
4. Unlock and call `get_pending_replacement_orders_5765`. Any order not clearly `delivered` or `cancelled` blocks the CLI.
5. Check good standing from the account: no past-due balance and current/active standing.
6. Calculate utilization as `current_balance / credit_limit * 100`; it must be strictly below the tier threshold.
7. Unlock and call `get_payment_history_6183` with the tier's required number of months. Verify the required number of consecutive on-time payments.

Use the calculator after normalizing these tool results. It returns all failed checks, a deterministic supported denial reason, and cooldown reapplication date where available.

### 3. Decide and communicate

- If every check passes, unlock and call `approve_credit_limit_increase_5847` with `new_credit_limit = current_limit + requested_increase`. Confirm the new total limit.
- If any post-submission check fails, unlock and call `deny_credit_limit_increase_5848` with the account ID, user ID, and one allowed reason. The supported reasons are `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, `insufficient_payment_history`, `requested_amount_exceeds_limit`, and `other`.
- Clearly state the decision and the practical next step. For cooldown denials, provide the calculated earliest date when available. For a dispute/replacement block, explain that the account must have no active dispute or pending replacement order before a later request can be approved.

## Calculator script

`scripts/evaluate_credit_card_request.py` reads one JSON object from stdin and emits one JSON object to stdout. It makes no banking calls and has no side effects.

Input schema (all monetary values may be JSON numbers or numeric strings):

```json
{
  "now": "YYYY-MM-DD",
  "account": {
    "tier": "entry|mid|premium",
    "opened_on": "YYYY-MM-DD",
    "current_limit": 0,
    "current_balance": 0,
    "past_due_amount": 0,
    "is_current": true
  },
  "cli": {
    "requested_increase_amount": 0,
    "submitted": false,
    "history": [{"submitted_at": "YYYY-MM-DD", "status": "approved|denied"}],
    "active_disputes": 0,
    "replacement_orders": [{"status": "delivered|cancelled|pending|shipped"}],
    "consecutive_on_time_months": 0
  },
  "dispute": {
    "reason": "goods_services_not_received",
    "amount": 0,
    "purchase_date": "YYYY-MM-DD",
    "contacted_merchant": true,
    "prior_dispute_dates": ["YYYY-MM-DD"],
    "tier": "mid"
  }
}
```

`cli` and `dispute` are optional. The CLI output distinguishes a rejected precheck from a valid-but-not-yet-submitted request and a post-submission approval/denial. The dispute output includes `eligible_for_provisional_credit`, criteria failures, and a 12-month dispute count. It does not replace required tool calls or identity verification.

Example invocation with runtime-supplied JSON:

```sh
python3 scripts/evaluate_credit_card_request.py <<'JSON'
{ "now": "<current-date>", "account": {"tier": "mid", "opened_on": "<open-date>", "current_limit": "<limit>", "current_balance": "<balance>", "past_due_amount": "<past-due>", "is_current": true}, "cli": {"requested_increase_amount": "<increase>", "submitted": true, "history": [], "active_disputes": 0, "replacement_orders": [], "consecutive_on_time_months": 3} }
JSON
```

Validate the output before acting: `cli.decision` can be `precheck_rejected`, `submit_required`, `approve`, `deny`, or `insufficient_data`; only `approve` or `deny` maps to a post-submission decision tool. Review every member of `cli.failures`; the script's `denial_reason` is a deterministic choice from those failures, not a substitute for the required full audit checks.
