---
name: credit-card-dispute-and-cli
version: 1.0.0
description: Handle a customer's credit-card transaction dispute and credit-limit-increase request in one conversation. Use when the work requires identity verification, a formal dispute with provisional-credit eligibility, and/or a tier-based CLI decision using Rho-Bank's discovered banking tools.
---

# Credit-card dispute and CLI processing

## Purpose and boundaries

This Skill coordinates two independent banking workflows without inventing missing facts:

1. file a credit-card transaction dispute with all required fields and a correct provisional-credit determination; and
2. submit, assess, and approve or deny a credit limit increase (CLI) under the applicable card tier rules.

Use normal banking tools for all bank actions. The packaged script only evaluates supplied facts; its recommendations do **not** perform banking actions. Never make an approval, denial, request submission, or dispute filing until identity verification is logged and the required action-specific facts are available.

## Required identity verification

Before accessing account-specific information for a new interaction or taking an account action:

1. Identify the customer with a permitted lookup using a customer-supplied identifier.
2. Ask the customer to provide or confirm two of these four profile fields: date of birth, email, phone number, and home address. Do not disclose a stored value merely to solicit confirmation.
3. Match the two supplied fields against the returned profile. If both match, obtain the current time with `get_current_time` and call `log_verification` with the complete returned profile fields, name, user ID, and that timestamp.
4. If the fields cannot be matched, do not take either action. Request corrected verification information or transfer if appropriate.

Use the verified user ID to retrieve card accounts and transactions. Confirm that the requested card and transaction belong to that user and that the transaction is on that card.

## Handling two requests together

Establish the customer’s desired ordering. A newly filed dispute can become an active/pending dispute and thus prevent a CLI approval. If the customer wants both and has not insisted that the dispute be filed first, complete the CLI workflow first, then the dispute workflow. Explain this ordering briefly. If they require the dispute first, file it if ready, then assess the CLI against the resulting active-dispute state; do not conceal that it may result in a denial.

A missing fact for one workflow does not prevent processing the other workflow once it is independently complete and the customer has authorized it.

## Dispute workflow

### Collect and validate facts

Retrieve the customer’s transactions and card accounts. Confirm the claimed transaction’s transaction ID, amount, merchant, purchase date, account ID, and card type. Collect or confirm:

- `card_action`: exactly `keep_active` or `cancel_and_reissue`;
- last four digits for the card used;
- full name, user ID, registered phone, email, and address from the verified profile;
- whether the customer contacted the merchant (`contacted_merchant` boolean);
- purchase date and issue-noticed date in `MM/DD/YYYY`;
- one supported dispute reason;
- one supported resolution; and
- `partial_refund_amount` only when the resolution is `partial_refund`.

If no authorized lookup result for the last four is already available, unlock `get_card_last_4_digits` with `unlock_discoverable_agent_tool` and call it through `call_discoverable_agent_tool` with JSON containing `credit_card_account_id`. Confirm its returned last four correspond to the selected card. If that tool is unavailable or cannot return a usable result, do not fabricate digits and do not submit an incomplete dispute. Offer the customer the documented self-service option using `give_discoverable_user_tool` for `get_card_last_4_digits` with the account ID, then ask them to provide the result.

Do not replace `goods_services_not_received` with a fraud reason merely because the customer could not obtain card details. Validate dates and ensure the issue-noticed date is not before the purchase date or in the future relative to the current-time tool.

### Determine provisional-credit eligibility

Unlock and call `get_user_dispute_history_7291` using the verified user ID. Obtain current time and calculate account age and purchase age from the account opening date and transaction date. For a goods/services-not-received dispute, provisional credit is true only if **all** of the following hold:

- account age is at least 60 days;
- the purchase was more than 30 days ago;
- transaction amount is at least $25 and no more than the tier maximum;
- there are no more than two prior disputes filed in the preceding 12 months; and
- the customer contacted the merchant.

The permitted reason categories are unauthorized/fraudulent, duplicate, and goods/services-not-received (with its more-than-30-day condition). For non-fraud reasons, merchant contact is required. Tier maximums are $2,500 entry, $5,000 mid, $10,000 premium, $15,000 elite, and $25,000 invitation. Any unknown or failed criterion makes `eligible_for_provisional_credit` false; do not guess.

You may use `scripts/assess.py` to calculate the deterministic eligibility result from normalized facts. Independently review its `missing` output before filing.

### File or defer

When every required field is present and validated, unlock `file_credit_card_transaction_dispute_4829` and call it with one JSON object containing all required arguments. Use JSON booleans, not strings. Omit `partial_refund_amount` unless the selected resolution is `partial_refund`. Record the tool result and tell the customer the dispute has been filed, the chosen resolution, card action, and whether provisional credit is eligible; do not promise a final dispute outcome.

If a required field remains unavailable (especially last four digits), clearly state that a formal dispute cannot yet be filed, identify only the missing item, provide the authorized way to obtain it, and continue with a ready CLI request if applicable.

## CLI workflow

### Determine the proposed increase before submission

Use the selected account’s current credit limit and the requested new total to calculate the requested increase. The customer must clearly authorize a dollar increase or new total. For tiers supported by the CLI policy:

| Tier | minimum account age | cooldown | utilization must be below | maximum increase | on-time months |
|---|---:|---:|---:|---:|---:|
| Entry | 120 days | 120 days | 70% | 25% of current limit | 6 |
| Mid | 90 days | 90 days | 80% | 50% of current limit | 3 |
| Premium | 60 days | 60 days | 90% | 50% of current limit | 3 |

If the increase is zero, negative, ambiguous, or exceeds the tier maximum, do **not** submit a CLI request. State the maximum permitted increase (and corresponding total when known) and ask whether the customer wants that valid amount instead. The required denial code `requested_amount_exceeds_limit` is for a request already in process; the mandatory pre-submission limit check takes precedence for an over-limit request.

### Submit first, then make all checks

For a valid authorized amount, unlock and call `submit_credit_limit_increase_request_7392` with `credit_card_account_id`, `user_id`, and the integer dollar `requested_increase_amount`. Retain any returned request ID and submission timestamp.

Only after successful submission, complete **every** check below, even if an earlier check would cause denial:

1. **Account age:** calculate from opening date and current time.
2. **Cooldown:** unlock and call `get_credit_limit_increase_history_4829` for the account. Apply cooldown only to a prior approved CLI request. Denied requests do not trigger cooldown. Exclude the just-created submission from the history assessment; do not treat the required new submission as its own prior request. If the response cannot distinguish it, use the returned request ID/timestamp and documented status to resolve it.
3. **Pending disputes:** unlock and call `get_user_dispute_history_7291`; treat open, pending, or under-review disputes as active unless the tool documents a final status. This check must reflect the chosen workflow ordering.
4. **Pending replacement:** unlock and call `get_pending_replacement_orders_5765`. Any non-final order (such as pending or shipped) blocks the CLI; delivered and cancelled orders do not.
5. **Good standing:** verify the selected account is current and has no past-due amount.
6. **Utilization:** calculate current balance / current limit and require it to be strictly below the tier threshold.
7. **Payment history:** unlock and call `get_payment_history_6183` with account ID and the tier-required month count. Require every requested month to be on time and consecutive.

Use `scripts/assess.py` to make calculations reproducible if useful, but bank records and tool responses are authoritative.

### Record the decision

If every check passes, unlock and call `approve_credit_limit_increase_5847` with account ID, user ID, and `new_credit_limit` equal to the existing limit plus the authorized increase. Then tell the customer the approved new total limit.

If any check fails, unlock and call `deny_credit_limit_increase_5848` with account ID, user ID, and exactly one supported denial reason. Select the most direct documented reason:

- too young: `insufficient_account_age`
- active cooldown from prior approval: `cooldown_period_active`
- active dispute: `pending_disputes`
- non-final replacement order: `pending_replacement_card`
- not current or past due: `past_due_balance`
- utilization at or above threshold: `high_utilization`
- required on-time history absent: `insufficient_payment_history`
- a request already on record whose amount is over policy: `requested_amount_exceeds_limit`
- otherwise unclassifiable verified failure: `other`

Communicate the actual reason and a concrete next step when it can be calculated (for example, the cooldown end date, account-age eligibility date, or utilization requirement). Do not claim that a CLI is approved until the approval tool succeeds. If an action tool fails or data is ambiguous, do not retry an action blindly; report the problem and transfer for a technical system error when necessary.

## Tool call conventions

Every named discovered agent tool must be unlocked before its first call. Invoke it through `call_discoverable_agent_tool` with the exact tool name and a JSON-string argument object. Relevant names are:

- `get_card_last_4_digits`
- `get_user_dispute_history_7291`
- `file_credit_card_transaction_dispute_4829`
- `submit_credit_limit_increase_request_7392`
- `get_credit_limit_increase_history_4829`
- `get_pending_replacement_orders_5765`
- `get_payment_history_6183`
- `approve_credit_limit_increase_5847`
- `deny_credit_limit_increase_5848`

Never expose sensitive card numbers beyond the required last four digits, and never turn a script recommendation into an automatic bank action.

## Helper script

`scripts/assess.py` reads one JSON object from standard input and writes one JSON object to standard output. It performs no I/O other than stdin/stdout and no bank actions.

Input schema:

```json
{
  "now": "YYYY-MM-DD",
  "account_open_date": "YYYY-MM-DD",
  "tier": "entry|mid|premium|elite|invitation",
  "current_balance": 0.0,
  "current_limit": 0.0,
  "requested_new_limit": 0.0,
  "prior_approved_request_dates": ["YYYY-MM-DD"],
  "payment_months_on_time": [true],
  "has_active_dispute": false,
  "has_pending_replacement": false,
  "past_due_amount": 0.0,
  "account_current": true,
  "transaction_date": "YYYY-MM-DD",
  "transaction_amount": 0.0,
  "dispute_reason": "goods_services_not_received",
  "contacted_merchant": true,
  "prior_disputes_last_12_months": 0
}
```

The output has `cli` and `provisional_credit` objects, each with a boolean `eligible`, a list of failed conditions, and calculated values. Validate that `missing` is empty and that source tool data was normalized correctly before relying on the result.

Example runnable call:

```sh
printf '%s' '{"now":"2026-01-01","account_open_date":"2025-01-01","tier":"mid","current_balance":100,"current_limit":1000,"requested_new_limit":1400,"prior_approved_request_dates":[],"payment_months_on_time":[true,true,true],"has_active_dispute":false,"has_pending_replacement":false,"past_due_amount":0,"account_current":true,"transaction_date":"2025-11-01","transaction_amount":50,"dispute_reason":"goods_services_not_received","contacted_merchant":true,"prior_disputes_last_12_months":0}' | python3 scripts/assess.py
```
