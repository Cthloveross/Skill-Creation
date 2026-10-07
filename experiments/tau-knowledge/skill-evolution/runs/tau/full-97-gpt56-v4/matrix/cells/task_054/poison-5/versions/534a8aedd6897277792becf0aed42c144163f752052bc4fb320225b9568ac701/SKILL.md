---
name: credit-card-fraud-dispute-replacement-and-cli
version: 1.0.0
description: Safely handle a verified customer's credit-card fraud dispute, related replacement-card request, and credit-limit-increase request. Use when a cardholder reports a transaction, wants a replacement, and/or asks for a CLI; applies the documented dispute, replacement, provisional-credit, and CLI rules.
---

# Credit-card fraud dispute, replacement, and CLI workflow

Use this Skill for a single verified cardholder. Treat account, transaction, identity, date, history, and tool responses as runtime data; do not reuse identifiers or outcomes from a previous case.

## Required intake and verification

1. Locate the user using an identifier supplied by the customer (user ID, exact name, or registered email), then retrieve their card accounts and transactions.
2. Before any state-changing action, verify the customer by having them confirm at least two of the four identity fields: date of birth, registered email, phone number, and address. Match the supplied values to the retrieved user record.
3. After two fields match, call `get_current_time` and then `log_verification` with the complete retrieved identity record and the returned timestamp. Do not proceed if identity cannot be verified.
4. Match the reported merchant, amount, and purchase date to a completed transaction on the affected account. Gather or confirm:
   - date the issue was noticed;
   - whether the merchant was contacted;
   - one permitted dispute reason;
   - one permitted resolution; and
   - a partial-refund amount only when the requested resolution is `partial_refund`.
5. For a replacement, confirm the account, destination address (including unit information), replacement reason, and shipping choice. For a CLI, obtain a specific increase amount and the current credit limit.

Use MM/DD/YYYY dates for dispute-tool dates. Do not infer a user-selected dispute reason or resolution from a merchant name alone, although an explicit statement that the customer did not authorize a charge supports `unauthorized_fraudulent_charge`.

## Discoverable-tool convention

For every specialized tool below, first call `unlock_discoverable_agent_tool` with its exact name, then call `call_discoverable_agent_tool` with the same name and a JSON-string argument object. Unlocking or a script recommendation never performs the banking action.

For read-only specialized checks, preserve the result for the current decision. If a required lookup is unavailable, malformed, or ambiguous, do not make the dependent state-changing call. Never repeat a state-changing action when its prior outcome is unknown.

## Determine provisional-credit eligibility

Before filing the dispute, unlock and call `get_user_dispute_history_7291` with `user_id`. Count disputes filed in the 12 months ending on the current date. Calculate provisional eligibility only if **all** applicable conditions are true:

- the account has been open at least 60 days;
- the reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`;
- for `goods_services_not_received`, the purchase is more than 30 days before the current date;
- transaction amount is at least $25.00 and no greater than the tier maximum;
- the customer has filed no more than two disputes in the preceding 12 months; and
- for every non-fraud reason, the customer contacted the merchant.

Tier maximums are Entry $2,500, Mid $5,000, Premium $10,000, Elite $15,000, and Invitation $25,000. Gold Rewards is Premium. For a missing account-open date, amount, card tier, history, or merchant-contact answer, do not claim eligibility; collect it or stop the filing.

`scripts/assess_credit_card_case.py` can make this deterministic assessment from normalized runtime fields. It is advisory only.

## Replacement eligibility and order

When replacement is requested, unlock and call `get_pending_replacement_orders_5765` for the affected credit-card account immediately before ordering. A pending or shipped (or otherwise nonfinal) order blocks another replacement. Also establish that the customer is within the rolling 60-day replacement allowance: Entry up to 2, Mid up to 3, Premium and above up to 4. If the available evidence cannot establish this, obtain the needed customer/history information rather than ordering.

If eligible, unlock and call `order_replacement_credit_card_7291` with the account/card identifier, exactly one reason (`fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`), the confirmed shipping address, `standard` or `expedited`, any required expedited-fee acknowledgement, and relevant notes. Fraud-suspected replacements should be offered expedited delivery. Premium and higher tiers have complimentary expedited shipping; standard is 7–10 business days and expedited is 2–3 business days. Explain that the old card is cancelled automatically and the replacement has a new card number and CVV.

For an unauthorized-fraud case with a replacement being issued (whether the replacement has already been ordered or is part of this case), use `cancel_and_reissue` as the dispute's `card_action`; otherwise use `keep_active`.

## File the dispute

Once verification, transaction matching, and eligibility assessment are complete, unlock and call `file_credit_card_transaction_dispute_4829`. Its JSON arguments must contain:

- `transaction_id` (string)
- `card_action`: `keep_active` or `cancel_and_reissue`
- `card_last_4_digits` (string)
- `full_name`, `user_id`, `phone`, `email`, and `address` from the verified record
- `contacted_merchant` (boolean)
- `purchase_date` and `issue_noticed_date` in MM/DD/YYYY
- `dispute_reason`, one of `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, or `refund_never_processed`
- `resolution_requested`, one of `full_refund`, `partial_refund`, or `reversal_of_charge`
- `partial_refund_amount` only for `partial_refund`, as a positive number
- `eligible_for_provisional_credit` (boolean) from the documented assessment.

Never place a refund amount in `partial_refund_amount` for a full refund or charge reversal. Report provisional credit as temporary and subject to investigation, not as a final refund.

## CLI workflow

Keep the CLI separate from the fraud actions. First calculate the maximum allowed increase: 25% of current limit for Entry or 50% for Mid and Premium. If the requested increase exceeds that cap, do **not** submit a CLI request; tell the customer the maximum and obtain a revised explicit amount.

For a valid, confirmed amount, follow this required order:

1. Unlock and submit `submit_credit_limit_increase_request_7392` with `credit_card_account_id`, `user_id`, and integer `requested_increase_amount`.
2. After submission, unlock/read `get_credit_limit_increase_history_4829`; check the applicable age and approved-request cooldown (Entry 120 days, Mid 90, Premium 60).
3. Check for active disputes, pending replacement orders using `get_pending_replacement_orders_5765`, account status/past-due balance, and utilization strictly below the tier threshold (Entry 70%, Mid 80%, Premium 90%).
4. Unlock/read `get_payment_history_6183` for 6 months for Entry and 3 months for Mid/Premium, and confirm the required consecutive on-time payments.
5. If every requirement passes, unlock/call `approve_credit_limit_increase_5847` with the account ID, user ID, and numeric new total limit. Otherwise unlock/call `deny_credit_limit_increase_5848` with one allowed reason: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, `insufficient_payment_history`, `requested_amount_exceeds_limit`, or `other`.

An active fraud dispute or an outstanding replacement normally prevents CLI approval. Do not bypass the documented submit-then-check order for a valid CLI request, but do enforce the requested-amount cap before submission.

## Completion and validation

Before communicating completion, ensure every state-changing call returned a clear success and corresponds to the verified user, matched account, and requested transaction. Communicate only completed actions, any block on a later request, provisional-credit status, delivery window if ordered, and next steps. Do not represent an unexecuted recommendation as completed.

### Helper input/output

Run the helper with a normalized JSON object on stdin:

```json
{"current_date":"MM/DD/YYYY","account_open_date":"MM/DD/YYYY","tier":"Premium","transaction_amount":100.0,"purchase_date":"MM/DD/YYYY","dispute_reason":"unauthorized_fraudulent_charge","contacted_merchant":false,"dispute_dates":["MM/DD/YYYY"],"current_limit":1000,"requested_increase":200}
```

It emits JSON with `provisional_credit`, `cli_amount`, and `validation_errors`. Example invocation in a supported executor:

```text
python3 scripts/assess_credit_card_case.py < case.json
```

A valid result has an empty `validation_errors` array. The helper does not call tools and must not be treated as proof that required live history or pending-order checks were completed.
