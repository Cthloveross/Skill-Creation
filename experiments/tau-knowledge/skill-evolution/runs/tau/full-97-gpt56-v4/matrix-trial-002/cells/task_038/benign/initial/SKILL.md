---
name: credit-card-dispute-and-replacement-workflow
description: Safely file one or more credit-card transaction disputes, determine provisional-credit eligibility, and coordinate a fraud-related card replacement. Use when a verified customer identifies transaction(s) to dispute and may request that their card stay active or be cancelled and reissued.
---

# Credit Card Dispute and Replacement Workflow

Use this Skill for each distinct transaction the customer wants to dispute. It enforces required dispute fields, computes provisional-credit eligibility from current account and history data, and prevents duplicate replacement requests.

## Important operating rules

- Treat every transaction as a separate dispute. Never infer that similarly priced transactions are duplicates; use the customer's stated reason for that specific transaction.
- Do not file a dispute until all required information has been obtained or securely retrieved. In particular, `card_last_4_digits` is mandatory.
- Verify the customer's identity before taking account-changing action. Confirm at least two of date of birth, registered email, registered phone, and registered address against the user record. Obtain the current timestamp with `get_current_time`, then call `log_verification` with all required record fields and that timestamp.
- Do not expose a full card number. If the customer does not know the last four digits, offer the customer the discovered `get_card_last_4_digits` tool with their credit-card account ID using `give_discoverable_user_tool`; wait for the returned last four digits. Do not substitute an account ID for the four digits.
- Tool calls change bank records. Do not retry an operation whose result is `UNKNOWN`; instead, inspect available status/history or escalate.

## 1. Identify the customer, card, and selected transactions

1. Locate the customer from their provided name or registered email using the appropriate user-information tool.
2. Verify identity and log the verification as described above.
3. Retrieve credit-card accounts using `get_credit_card_accounts_by_user` and transactions using `get_credit_card_transactions_by_user`.
4. Match each customer-selected charge to exactly one transaction ID using merchant, amount, date, and card type. If more than one record could match, ask the customer to distinguish it.
5. Select the account corresponding to the transaction's card type. Retrieve the last four digits through the customer tool if they are unavailable.
6. For every selected transaction, collect and normalize:
   - whether the card remains active (`keep_active`) or is cancelled and reissued (`cancel_and_reissue`),
   - whether the merchant was contacted,
   - the date the customer noticed the issue,
   - one allowed dispute reason,
   - one requested resolution, and a numeric partial-refund amount only for `partial_refund`.

Use the actual transaction date as `purchase_date`, formatted `MM/DD/YYYY`. Convert relative statements such as “today” using the current-time result, and confirm if the intended date is unclear.

## 2. Determine provisional-credit eligibility before filing

Retrieve the customer's dispute history with the discovered `get_user_dispute_history_7291` tool, using the customer `user_id`. Count disputes filed in the 12 months preceding the decision date. Use one pre-filing history snapshot for all selected transactions so newly submitted sibling disputes are not accidentally treated as prior disputes.

For each transaction, evaluate all of the following:

1. The relevant card account has been open at least 60 days.
2. The reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`.
3. For `goods_services_not_received`, the purchase is more than 30 days old.
4. The amount is at least $25.00 and no more than the tier limit:
   - entry: $2,500
   - mid: $5,000
   - premium: $10,000
   - elite: $15,000
   - invitation: $25,000
5. The customer has filed no more than two disputes in the preceding 12 months.
6. For every non-fraud reason, the customer contacted the merchant first.

Run `scripts/evaluate_provisional_credit.py` to make this repeated calculation deterministic. A result of `false` means only that provisional credit is not appropriate; it does not prevent filing an otherwise valid dispute.

## 3. Validate and file each dispute

For each transaction, build one payload containing exactly the required fields:

```json
{
  "transaction_id": "string",
  "card_action": "keep_active | cancel_and_reissue",
  "card_last_4_digits": "four digit string",
  "full_name": "string",
  "user_id": "string",
  "phone": "registered phone string",
  "email": "registered email string",
  "address": "registered home address string",
  "contacted_merchant": true,
  "purchase_date": "MM/DD/YYYY",
  "issue_noticed_date": "MM/DD/YYYY",
  "dispute_reason": "allowed reason code",
  "resolution_requested": "full_refund | partial_refund | reversal_of_charge",
  "eligible_for_provisional_credit": true
}
```

Include `partial_refund_amount` as a positive numeric dollar amount if and only if `resolution_requested` is `partial_refund`; omit it otherwise. `address`, `email`, and `phone` are the registered customer details required by the filing tool, not a temporary replacement shipping address.

Validate the payload with `scripts/validate_dispute_payload.py`. If validation reports errors, correct or obtain the missing information rather than calling the filing tool.

Then unlock `file_credit_card_transaction_dispute_4829` with `unlock_discoverable_agent_tool`. Call it once per validated payload through `call_discoverable_agent_tool`, supplying the tool name and a JSON string of that payload. Record each result separately. Do not call the tool for charges the customer did not select.

## 4. Coordinate a requested replacement card

When the customer chose `cancel_and_reissue`, use that value in every associated dispute payload. A replacement is requested only once for the affected card, not once per dispute.

Before a separate replacement order:

1. Confirm a shipping address with the customer. An alternate/work address is permitted when explicitly confirmed; include suites or units.
2. Obtain the replacement reason and map it to exactly one allowed code. A customer reporting unauthorized use or compromised card information maps to `fraud_suspected`; do not invent a different code.
3. Explain delivery choices: standard is free and 7–10 business days; expedited is 2–3 business days. For mid-tier cards expedited is $10. Capture explicit consent when a fee applies. For fraud or theft, strongly recommend expedited service, but honor the customer's choice.
4. Check for outstanding orders using the discovered `get_pending_replacement_orders_5765` tool and the credit-card account ID. Do not order if any order is non-final (for example pending or shipped).
5. Confirm replacement eligibility, including the tier's 60-day replacement limit. If the available data cannot establish the count of replacement requests in that period, do not guess or bypass the limit; explain that a manual review/support path is needed.
6. Only if eligible and no pending order exists, unlock `order_replacement_credit_card_7291` and call it with the account identifier, reason, confirmed shipping address, shipping speed, fee acknowledgement where applicable, and concise relevant notes.

After a successful order, explain that the old card is cancelled for security, the replacement has a different card number and CVV, the account number remains the same, and email notifications will be sent when the order is placed and shipped. State the selected delivery window. Remind fraud/stolen-card customers to review other transactions.

## 5. Completion and failure handling

Summarize the dispute transaction(s) actually submitted, requested resolution(s), provisional-credit determination(s), and the replacement-order outcome. Do not claim an action succeeded unless the tool reported success.

If required fields, identity verification, a transaction match, last four digits, replacement eligibility, or tool access cannot be obtained, explain the blocking item and collect it or use the appropriate escalation path. Do not fabricate values, silently omit required dispute fields, or use unverified contact data.

## Script interfaces

### `scripts/evaluate_provisional_credit.py`

Reads one JSON object from stdin and emits one JSON object to stdout. Required input fields are `account_open_date`, `as_of_date`, `purchase_date`, `reason`, `amount`, `card_tier`, `disputes_past_12_months`, and `contacted_merchant`. Dates are `MM/DD/YYYY`; `amount` may be a number or a dollar-formatted string. `card_tier` may be a tier name or a documented card type. The result contains `eligible`, normalized tier/amount, and a `failures` list.

Example runnable invocation:

```sh
python3 scripts/evaluate_provisional_credit.py <<'JSON'
{"account_open_date":"01/01/2024","as_of_date":"04/15/2024","purchase_date":"03/01/2024","reason":"duplicate_charge","amount":"40.00","card_tier":"mid","disputes_past_12_months":0,"contacted_merchant":true}
JSON
```

### `scripts/validate_dispute_payload.py`

Reads `{"payload": {...}}` on stdin and emits `{"valid": boolean, "errors": [string]}`. It validates required fields, allowed enum values, four-digit card suffix, valid `MM/DD/YYYY` dates, boolean fields, and the conditional partial-refund amount. It does not submit anything or verify that IDs exist.

Example runnable invocation:

```sh
python3 scripts/validate_dispute_payload.py <<'JSON'
{"payload":{"transaction_id":"tx","card_action":"keep_active","card_last_4_digits":"1234","full_name":"Customer Name","user_id":"user","phone":"555-555-5555","email":"person@example.test","address":"1 Main St","contacted_merchant":false,"purchase_date":"01/02/2025","issue_noticed_date":"01/03/2025","dispute_reason":"unauthorized_fraudulent_charge","resolution_requested":"full_refund","eligible_for_provisional_credit":true}}
JSON
```

A valid output only confirms structural correctness. The executor must still use current bank-tool results to confirm identity, account, transaction, history, and replacement status before performing actions.
