---
name: secure-credit-card-fraud-replacement-and-cli
version: 1.0.0
description: Handle a credit-card fraud dispute that may require card reissue/replacement and a credit-limit-increase request. Use for authenticated customers when transaction, account, and requested-increase details must be verified and recorded through the available banking tools.
---

# Secure Credit Card Fraud, Replacement, and CLI Workflow

Use this Skill for a customer requesting one or more of: a transaction dispute, a replacement card, and a credit limit increase (CLI). Treat fraud/security work as the priority. Do not expose unnecessary account data in the customer-facing response.

## Inputs and prerequisite data

At runtime, obtain or confirm:

- The customer identity and canonical `user_id`.
- Two customer-confirmed identity fields from date of birth, email, phone number, and address.
- The affected account, including account ID, card type, open date, current balance, credit limit, status, past-due amount, and card last four digits.
- The specific transaction and its ID, amount, and purchase date.
- For a dispute: reason, date noticed, merchant-contact answer, and requested resolution.
- For a replacement: one permitted reason, confirmed shipping address, shipping speed, and required fee acknowledgement when applicable.
- For a CLI: the requested *increase amount* (not just desired total limit) and customer confirmation of the amount.

Use account and transaction lookup tools rather than assuming a transaction belongs to the selected account. If there are multiple matching cards or transactions, ask the customer to identify the intended one.

## 1. Authenticate before account-changing actions

1. Locate the user and account using the ordinary lookup tools.
2. Ask the customer to confirm two identity fields; do not treat a name alone, an unverified assertion, or data merely read from a lookup as identity verification.
3. Compare both answers to the retrieved customer record. If either does not match, stop and resolve identity before proceeding.
4. Obtain the current timestamp with `get_current_time` and call `log_verification` with all required record fields and that timestamp.

Do not unlock or invoke dispute, replacement, CLI, approval, or denial tools until identity verification is logged.

## 2. Prioritize and file the fraud dispute

Confirm the selected transaction’s merchant, date, amount, and card match the customer’s report. Collect all mandatory dispute fields before filing.

For each case, determine provisional-credit eligibility from the documented rules, not from customer preference. Run the packaged helper if useful:

```text
python scripts/assessments.py <<'JSON'
{"kind":"provisional_credit","tier":"premium","account_open_date":"YYYY-MM-DD","current_date":"YYYY-MM-DD","purchase_date":"YYYY-MM-DD","amount":"0.00","reason":"unauthorized_fraudulent_charge","prior_disputes_12m":0,"contacted_merchant":false}
JSON
```

For provisional credit, all of these must be true:

- Account age is at least 60 days.
- Reason is unauthorized/fraudulent, duplicate, or goods/services not received; the last category also requires a purchase more than 30 days ago.
- Amount is at least $25 and does not exceed the tier cap: entry $2,500; mid $5,000; premium $10,000; elite $15,000; invitation $25,000.
- The customer has not filed more than two disputes in the previous 12 months.
- For non-fraud reasons, the customer contacted the merchant first.

If dispute history is not available through a supported runtime tool, explicitly collect the prior-dispute count from the customer and label it as customer-provided. Do not invent a tool or claim an independently verified count.

Unlock `file_credit_card_transaction_dispute_4829`, then call it through `call_discoverable_agent_tool`. Its JSON arguments must include:

- `transaction_id`
- `card_action`: `keep_active` or `cancel_and_reissue`
- `card_last_4_digits`
- `full_name`, `user_id`, `phone`, `email`, and `address`
- `contacted_merchant`
- `purchase_date` and `issue_noticed_date` in `MM/DD/YYYY`
- one allowed `dispute_reason`
- one allowed `resolution_requested`
- `partial_refund_amount` only for `partial_refund`
- the calculated `eligible_for_provisional_credit` boolean

For an unauthorized charge where the customer wants the card replaced, use `cancel_and_reissue`; otherwise use `keep_active` only when the customer elects to retain the card. Do not substitute a chargeback for a requested full refund. Record and communicate the filing outcome returned by the tool.

## 3. Replacement-card handling

A fraud dispute with `cancel_and_reissue` records that the compromised card must be cancelled and reissued. If a separately shipped replacement order is needed, it must meet the replacement workflow as well.

Before an independent replacement order:

1. Confirm identity has been logged, the account is known, the address is confirmed, the reason is exactly one of `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`, and the customer selected standard or expedited shipping.
2. Confirm there is no pending replacement and that the 60-day tier limit has not been exceeded: entry two, mid three, premium-and-above four.
3. If a supported pending-order/history lookup is available in the runtime, use it. The supplied schemas may not expose `get_pending_replacement_orders_5765` or a replacement-history lookup; never fabricate a direct call or treat missing information as proof of eligibility.
4. If eligibility cannot be confirmed, do **not** unlock or submit a second replacement order. Explain that the dispute’s `cancel_and_reissue` action protects the card and that shipping cannot be separately arranged until replacement eligibility is confirmed.

When eligibility is confirmed, unlock `order_replacement_credit_card_7291` and call it with the account identifier, permitted reason, confirmed `shipping_address`, `shipping_speed`, `expedited_fee_acknowledgement`, and contextual `notes`.

Shipping policy:

- Standard: 7–10 business days, no fee.
- Expedited: 2–3 business days.
- Entry tier expedited fee: $15; mid tier: $10; premium and above: $0.

For a fee-bearing expedited order, capture affirmative fee consent before setting the acknowledgement. For suspected fraud or theft, recommend expedited shipping. Explain that the old card is cancelled, the account number remains, and the replacement has a new card number and CVV. Do not promise a shipping outcome until an order tool confirms it.

## 4. CLI: validate the amount before any submission

CLI is lower priority than fraud/reissue work. First convert the customer’s requested new total to an increase amount if needed, and verify that amount against the current limit.

Use `scripts/assessments.py` for the tier rules and arithmetic:

```text
python scripts/assessments.py <<'JSON'
{"kind":"cli","tier":"premium","current_credit_limit":"5000","requested_increase_amount":"1000","account_open_date":"YYYY-MM-DD","current_date":"YYYY-MM-DD","utilization_percent":"0","last_approved_request_date":null,"consecutive_on_time_months":3,"has_pending_disputes":false,"has_pending_replacement":false,"past_due_amount":"0"}
JSON
```

Maximum increase per request is 25% of current limit for entry tier and 50% for mid and premium tier. If the requested amount is greater than the maximum, tell the customer the maximum dollar increase and ask whether they want to proceed with that adjusted amount. **Do not submit a CLI request exceeding the limit and do not create a denial record for an unsubmitted amount.**

Only after the customer confirms an in-limit amount:

1. Unlock and call `submit_credit_limit_increase_request_7392` with account ID, user ID, and the confirmed increase amount.
2. Check every requirement before a decision:
   - Account age: entry 120 days, mid 90 days, premium 60 days.
   - Cooldown since the most recent **approved** CLI request: entry 120 days, mid 90 days, premium 60 days.
   - No active disputes.
   - No pending replacement cards.
   - Current account status and no past-due balance.
   - Utilization strictly below the threshold: entry 70%, mid 80%, premium 90%.
   - Consecutive on-time payments: entry six months; mid/premium three months.
3. Use documented supported retrieval tools where available (including payment history and CLI history). If a documented check is not exposed by the supplied runtime, do not invent a call or state that it passed. Preserve the submitted request and escalate/hold it for the unavailable required verification rather than approving it.
4. If all requirements pass, unlock and call `approve_credit_limit_increase_5847` with `new_credit_limit = current_credit_limit + confirmed_increase_amount`.
5. If any verified requirement fails, unlock and call `deny_credit_limit_increase_5848` with exactly one allowed denial reason. Choose the specific applicable code, such as `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, `cooldown_period_active`, `insufficient_account_age`, or `insufficient_payment_history`.

A dispute filed during this interaction is an active dispute for this CLI check. Still perform the other required checks for the audit record before recording a decision.

## 5. Customer communication and failure handling

End with a concise status for each requested service:

- Dispute: transaction, filing status, card-security action, and whether provisional credit is eligible (temporary, pending investigation).
- Replacement: whether an order was submitted; if submitted, delivery window and fees; otherwise the exact unmet or unverified prerequisite.
- CLI: whether the amount must be adjusted, whether a request was submitted, and the approved/denied/held result.

Never claim that an unavailable lookup was performed, that a request was approved, or that a replacement shipped unless the relevant tool returned that result. Do not repeat an operation after an `UNKNOWN` outcome. If a banking tool reports a technical failure, preserve the known request context and use the supported escalation/transfer path rather than retrying an uncertain mutation.

## Packaged helper interface

`scripts/assessments.py` reads exactly one JSON object from standard input and emits one JSON object to standard output. Set `kind` to `"provisional_credit"` or `"cli"`. Dates accept `YYYY-MM-DD` or `MM/DD/YYYY`; monetary inputs may be JSON numbers or decimal strings. The result includes criterion-level booleans, missing fields, calculated thresholds, and an `eligible` value of `true`, `false`, or `null` when required facts are missing.
